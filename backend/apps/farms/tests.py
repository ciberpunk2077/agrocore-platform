from unittest.mock import patch
from types import SimpleNamespace
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.catalogs.models import FarmType
from apps.farms.api.schemas import FarmCreateSchema
from apps.farms.models import Farm
from apps.farms.services import FarmService
from apps.farms.selectors import FarmSelector
from apps.farms.api.schemas import FarmUpdateSchema
from apps.common.context.context import RequestContext
from apps.common.exceptions import BusinessException
from django.utils import timezone
from apps.common.exceptions.farm import FarmValidationError
from apps.organizations.models import Organization


class FarmCharacterizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name="Farms characterization", code="FARMS_CHARACTERIZATION",
        )
        cls.user = User.objects.create_user(
            email="farms-characterization@example.com",
            first_name="Farms", last_name="Tester", is_active=True,
        )
        Membership.objects.create(
            user=cls.user, organization=cls.organization,
            role=Membership.Role.OWNER, is_default=True, is_active=True,
        )
        cls.farm_type = FarmType.objects.create(code="CHAR_RANCH", name="Ranch")

    def setUp(self):
        self.context = SimpleNamespace(organization=self.organization)
        self.client.defaults["HTTP_AUTHORIZATION"] = (
            f"Bearer {create_access_token(self.user)}"
        )
        self.payload = {
            "name": "Characterization farm",
            "code": "FARM-001",
            "farm_type_id": str(self.farm_type.pk),
        }

    def test_http_create_returns_400_for_schema_accepted_invalid_name(self):
        self.payload["name"] = "N" * 201
        schema = FarmCreateSchema(**self.payload)
        self.assertEqual(schema.name, self.payload["name"])

        # Observe the real validation and persistence methods without bypassing them.
        with patch.object(Farm, "full_clean", autospec=True, side_effect=Farm.full_clean) as clean:
            with patch.object(Farm, "save", autospec=True, side_effect=Farm.save) as save:
                response = self.client.post("/api/farms/", self.payload, content_type="application/json")

                clean.assert_called_once()
                save.assert_not_called()

        self.assertEqual(response.status_code, 400)
        self.assertIn("200", response.json()["detail"])
        self.assertIn("201", response.json()["detail"])
        self.assertIn("characters", response.json()["detail"])
        self.assertEqual(Farm._base_manager.filter(organization=self.organization).count(), 0)

    def test_http_create_returns_400_for_soft_deleted_farm_code(self):
        response = self.client.post("/api/farms/", self.payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        farm = Farm.objects.get(pk=response.json()["id"])
        self.assertEqual(farm.organization_id, self.organization.pk)

        response = self.client.delete(f"/api/farms/{farm.pk}")
        self.assertEqual(response.status_code, 200)
        farm.refresh_from_db()
        self.assertFalse(farm.is_active)
        self.assertIsNotNone(farm.deleted_at)
        self.assertFalse(Farm.objects.filter(pk=farm.pk).exists())
        original = self.snapshot(farm)

        with patch.object(Farm, "save", autospec=True, side_effect=Farm.save) as save:
            response = self.client.post("/api/farms/", self.payload, content_type="application/json")
            save.assert_not_called()
        self.assert_reserved_response(response)
        farms = Farm._base_manager.filter(organization=self.organization)
        self.assertEqual(farms.count(), 1)
        self.assertEqual(farms.get().pk, farm.pk)
        self.assertFalse(Farm.objects.filter(organization=self.organization).exists())
        self.assertEqual(self.snapshot(farms.get()), original)

    reserved_detail = "El código ya está reservado por una unidad productiva de esta organización."

    def assert_reserved_response(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": self.reserved_detail})

    def make_farm(self, code="FARM-001", organization=None):
        return Farm.objects.create(
            organization=organization or self.organization,
            name="Original farm", code=code, farm_type=self.farm_type,
        )

    def snapshot(self, farm):
        return {field.attname: getattr(farm, field.attname) for field in Farm._meta.concrete_fields}

    def post(self):
        return self.client.post("/api/farms/", self.payload, content_type="application/json")

    def put(self, farm):
        return self.client.put(f"/api/farms/{farm.pk}", self.payload, content_type="application/json")

    def test_http_create_rejects_active_reserved_code(self):
        farm = self.make_farm()
        original = self.snapshot(farm)
        self.assert_reserved_response(self.post())
        farm.refresh_from_db()
        self.assertEqual(self.snapshot(farm), original)
        self.assertEqual(Farm._base_manager.count(), 1)

    def test_http_create_allows_code_in_other_tenant(self):
        other = Organization.objects.create(code="FARMS_OTHER", name="Other tenant")
        farm = self.make_farm(organization=other)
        original = self.snapshot(farm)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(Farm._base_manager.count(), 2)
        self.assertTrue(Farm.objects.filter(organization=self.organization, code="FARM-001").exists())
        farm.refresh_from_db()
        self.assertEqual(self.snapshot(farm), original)

    def test_service_create_translates_validation_error_with_cause(self):
        self.payload["name"] = "N" * 201
        with self.assertRaises(FarmValidationError) as raised:
            FarmService.create(self.context, FarmCreateSchema(**self.payload))
        self.assertIsInstance(raised.exception.__cause__, ValidationError)
        self.assertEqual(raised.exception.__cause__.error_dict["name"][0].code, "max_length")
        self.assertEqual(str(raised.exception), " ".join(raised.exception.__cause__.messages))
        self.assertEqual(Farm._base_manager.count(), 0)

    def test_http_update_allows_own_code(self):
        farm = self.make_farm()
        self.assertEqual(self.put(farm).status_code, 200)
        farm.refresh_from_db()
        self.assertEqual(farm.code, "FARM-001")
        self.assertEqual(farm.name, self.payload["name"])
        self.assertEqual(Farm._base_manager.count(), 1)

    def test_http_update_rejects_other_active_code(self):
        self.assert_update_rejects_reserved_code(inactive=False)

    def test_http_update_rejects_other_inactive_code(self):
        self.assert_update_rejects_reserved_code(inactive=True)

    def assert_update_rejects_reserved_code(self, inactive):
        reserved = self.make_farm()
        if inactive:
            reserved.delete()
        farm = self.make_farm(code="FARM-002")
        originals = [self.snapshot(farm), self.snapshot(reserved)]
        self.assert_reserved_response(self.put(farm))
        farm.refresh_from_db()
        reserved.refresh_from_db()
        self.assertEqual([self.snapshot(farm), self.snapshot(reserved)], originals)
        self.assertEqual(Farm._base_manager.count(), 2)

    def test_http_update_allows_code_in_other_tenant(self):
        other = Organization.objects.create(code="FARMS_OTHER", name="Other tenant")
        reserved = self.make_farm(organization=other)
        original = self.snapshot(reserved)
        farm = self.make_farm(code="FARM-002")
        self.assertEqual(self.put(farm).status_code, 200)
        farm.refresh_from_db()
        reserved.refresh_from_db()
        self.assertEqual(farm.code, "FARM-001")
        self.assertEqual(self.snapshot(reserved), original)
        self.assertEqual(Farm._base_manager.count(), 2)

    def test_service_update_restores_instance_after_validation_error(self):
        farm = self.make_farm()
        original = self.snapshot(farm)
        self.payload["name"] = "N" * 201
        with self.assertRaises(FarmValidationError) as raised:
            FarmService.update(farm, self.context, FarmCreateSchema(**self.payload))
        self.assertIsInstance(raised.exception.__cause__, ValidationError)
        self.assertEqual(str(raised.exception), " ".join(raised.exception.__cause__.messages))
        self.assertEqual(self.snapshot(farm), original)
        farm.refresh_from_db()
        self.assertEqual(self.snapshot(farm), original)

    def test_http_update_returns_400_for_invalid_name_without_writes(self):
        farm = self.make_farm()
        original = self.snapshot(farm)
        self.payload["name"] = "N" * 201
        response = self.put(farm)
        self.assertEqual(response.status_code, 400)
        self.assertIn("200", response.json()["detail"])
        farm.refresh_from_db()
        self.assertEqual(self.snapshot(farm), original)

    def test_service_create_translates_real_db_reserved_code_collision(self):
        reserved = self.make_farm()
        reserved.delete()
        original = self.snapshot(reserved)
        # Only bypass the precheck. Real full_clean ignores the inactive row;
        # real save must hit the database UNIQUE constraint.
        with patch.object(FarmService, "_validate_reserved_code"):
            with self.assertRaises(FarmValidationError) as raised:
                FarmService.create(self.context, FarmCreateSchema(**self.payload))
        self.assertEqual(str(raised.exception), self.reserved_detail)
        self.assertIsInstance(raised.exception.__cause__, IntegrityError)
        self.assertIsNotNone(raised.exception.__cause__.__cause__)
        self.assertEqual(Farm._base_manager.count(), 1)
        reserved.refresh_from_db()
        self.assertEqual(self.snapshot(reserved), original)

    def test_service_update_translates_real_db_collision_and_restores_instance(self):
        reserved = self.make_farm()
        reserved.delete()
        farm = self.make_farm(code="FARM-002")
        originals = [self.snapshot(farm), self.snapshot(reserved)]
        with patch.object(FarmService, "_validate_reserved_code"):
            with self.assertRaises(FarmValidationError) as raised:
                FarmService.update(farm, self.context, FarmCreateSchema(**self.payload))
        self.assertEqual(str(raised.exception), self.reserved_detail)
        self.assertIsInstance(raised.exception.__cause__, IntegrityError)
        self.assertEqual(self.snapshot(farm), originals[0])
        self.assertEqual(Farm._base_manager.count(), 2)
        farm.refresh_from_db()
        reserved.refresh_from_db()
        self.assertEqual([self.snapshot(farm), self.snapshot(reserved)], originals)

    def test_unrelated_integrity_error_propagates_in_create_and_update(self):
        farm = self.make_farm(code="FARM-002")
        original = self.snapshot(farm)
        for operation in ("create", "update"):
            with self.subTest(operation=operation):
                # A real NOT NULL violation must not be labeled a code collision.
                real_save = Farm.save

                def invalid_save(instance, *args, **kwargs):
                    instance.name = None
                    return real_save(instance, *args, **kwargs)

                with patch.object(Farm, "save", autospec=True, side_effect=invalid_save):
                    with self.assertRaises(IntegrityError) as raised:
                        data = FarmCreateSchema(**self.payload)
                        if operation == "create":
                            FarmService.create(self.context, data)
                        else:
                            FarmService.update(farm, self.context, data)
                self.assertIn("NOT NULL", str(raised.exception))
                self.assertEqual(Farm._base_manager.count(), 1)
                farm.refresh_from_db()
                self.assertEqual(self.snapshot(farm), original)

    def test_named_constraint_recognition_is_specific(self):
        for name, expected in (
            ("unique_farm_code_per_organization", True),
            ("another_constraint", False),
        ):
            with self.subTest(constraint=name):
                cause = Exception("Backend constraint violation")
                cause.diag = SimpleNamespace(constraint_name=name)
                error = IntegrityError("Backend constraint violation")
                error.__cause__ = cause
                self.assertEqual(FarmService._is_reserved_code_error(error), expected)

    def test_model_defaults_uuid_and_timestamps(self):
        before = timezone.now()
        farm = self.make_farm()
        farm.refresh_from_db()
        self.assertIsInstance(farm.pk, UUID)
        self.assertTrue(farm.is_active)
        self.assertIsNone(farm.deleted_at)
        self.assertEqual(farm.country, "México")
        for field in ("description", "address", "city", "state"):
            self.assertEqual(getattr(farm, field), "")
        self.assertLessEqual(before, farm.created_at)
        self.assertLessEqual(farm.created_at, farm.updated_at)
        self.assertLessEqual(farm.updated_at, timezone.now())
        created_at, updated_at = farm.created_at, farm.updated_at
        farm.name = "Updated"
        farm.save()
        farm.refresh_from_db()
        self.assertEqual(farm.created_at, created_at)
        self.assertGreaterEqual(farm.updated_at, updated_at)

    def test_model_allows_duplicate_names(self):
        first = self.make_farm()
        second = self.make_farm(code="FARM-002")
        second.full_clean()
        self.assertEqual(first.name, second.name)
        self.assertEqual(Farm.objects.count(), 2)

    def test_model_rejects_blank_required_fields_and_overlong_text(self):
        # Name length is already covered by the regression tests.
        cases = [(field, "", "blank") for field in ("name", "code", "country")]
        cases += [(field, "X" * length, "max_length") for field, length in (
            ("code", 31), ("address", 256), ("city", 121),
            ("state", 121), ("country", 121),
        )]
        for field, value, expected_code in cases:
            with self.subTest(field=field, validation=expected_code):
                farm = Farm(organization=self.organization, farm_type=self.farm_type,
                            name="Valid", code="VALID")
                setattr(farm, field, value)
                with self.assertRaises(ValidationError) as raised:
                    farm.full_clean()
                self.assertEqual(raised.exception.error_dict[field][0].code, expected_code)
        self.assertEqual(Farm._base_manager.count(), 0)

    def test_selector_list_scopes_filters_orders_and_loads_farm_type(self):
        zulu = self.make_farm(code="Z")
        zulu.name = "Zulu"
        zulu.save()
        alpha = self.make_farm(code="A")
        alpha.name = "Alpha"
        alpha.save()
        self.make_farm(code="INACTIVE").delete()
        other = Organization.objects.create(code="OTHER", name="Other")
        self.make_farm(code="FOREIGN", organization=other)
        with self.assertNumQueries(1):
            farms = list(FarmSelector.list(self.context))
            self.assertEqual([farm.pk for farm in farms], [alpha.pk, zulu.pk])
            self.assertEqual([farm.farm_type.name for farm in farms], [self.farm_type.name] * 2)

    def test_selector_detail_scopes_filters_and_loads_farm_type(self):
        own = self.make_farm()
        inactive = self.make_farm(code="INACTIVE")
        inactive.delete()
        other = Organization.objects.create(code="OTHER", name="Other")
        foreign = self.make_farm(organization=other)
        with self.assertNumQueries(1):
            selected = FarmSelector.get_by_id(self.context, own.pk)
            self.assertEqual(selected.pk, own.pk)
            self.assertEqual(selected.farm_type.name, self.farm_type.name)
        for identifier in (inactive.pk, foreign.pk, uuid4()):
            with self.subTest(identifier=identifier):
                self.assertIsNone(FarmSelector.get_by_id(self.context, identifier))

    def full_payload(self):
        return dict(self.payload, description="Description", address="Road 10",
                    city="City", state="State", country="Canada")

    def assert_persisted_payload(self, farm, payload):
        self.assertEqual(farm.organization_id, self.organization.pk)
        for field, value in payload.items():
            expected = UUID(value) if field == "farm_type_id" else value
            self.assertEqual(getattr(farm, field), expected)

    def test_service_create_persists_all_fields_from_request_context(self):
        context = RequestContext(user=self.user, organization=self.organization)
        payload = self.full_payload()
        farm = FarmService.create(context, FarmCreateSchema(**payload))
        farm.refresh_from_db()
        self.assert_persisted_payload(farm, payload)
        defaults = FarmService.create(context, FarmCreateSchema(**dict(self.payload, code="DEFAULTS")))
        defaults.refresh_from_db()
        self.assertEqual(defaults.country, "México")
        for field in ("description", "address", "city", "state"):
            self.assertEqual(getattr(defaults, field), "")

    def test_service_update_persists_all_editable_fields_and_changes_type(self):
        farm = self.make_farm()
        created_at = farm.created_at
        new_type = FarmType.objects.create(code="NEW_TYPE", name="New type")
        payload = dict(self.full_payload(), name="Updated", code="UPDATED", farm_type_id=str(new_type.pk))
        FarmService.update(farm, self.context, FarmUpdateSchema(**payload))
        farm.refresh_from_db()
        self.assert_persisted_payload(farm, payload)
        self.assertEqual(farm.created_at, created_at)

    def test_service_create_and_update_reject_unavailable_farm_types(self):
        inactive = FarmType.objects.create(code="INACTIVE", name="Inactive", is_active=False)
        farm = self.make_farm(code="EXISTING")
        original = self.snapshot(farm)
        for identifier in (uuid4(), inactive.pk):
            for operation in ("create", "update"):
                with self.subTest(identifier=identifier, operation=operation):
                    data = FarmCreateSchema(**dict(self.payload, farm_type_id=str(identifier)))
                    with self.assertRaises(BusinessException) as raised:
                        if operation == "create":
                            FarmService.create(self.context, data)
                        else:
                            FarmService.update(farm, self.context, data)
                    self.assertIs(type(raised.exception), BusinessException)
                    self.assertEqual(str(raised.exception), "El tipo de unidad productiva no existe o no está activo.")
                    self.assertEqual(self.snapshot(farm), original)
                    farm.refresh_from_db()
                    self.assertEqual(self.snapshot(farm), original)
                    self.assertEqual(Farm._base_manager.count(), 1)

    def assert_response_fields(self, body, farm):
        expected = {field: getattr(farm, field) for field in (
            "name", "code", "description", "address", "city", "state", "country",
        )}
        expected.update(id=str(farm.pk), farm_type_id=str(farm.farm_type_id), farm_type=farm.farm_type.name)
        self.assertEqual(body, expected)

    def test_http_valid_crud_response_fields_and_soft_delete_visibility(self):
        self.payload = self.full_payload()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        farm = Farm.objects.get(pk=response.json()["id"])
        self.assert_response_fields(response.json(), farm)
        listing = self.client.get("/api/farms/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json(), [response.json()])
        detail = self.client.get(f"/api/farms/{farm.pk}")
        self.assertEqual(detail.status_code, 200)
        self.assert_response_fields(detail.json(), farm)
        self.payload.update(name="HTTP updated", description="New description")
        response = self.put(farm)
        self.assertEqual(response.status_code, 200)
        farm.refresh_from_db()
        self.assert_persisted_payload(farm, self.payload)
        self.assert_response_fields(response.json(), farm)
        response = self.client.delete(f"/api/farms/{farm.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        farm.refresh_from_db()
        self.assertFalse(farm.is_active)
        self.assertIsNotNone(farm.deleted_at)
        self.assertEqual(Farm._base_manager.count(), 1)
        deleted = self.snapshot(farm)
        self.assertEqual(self.client.get("/api/farms/").json(), [])
        for method in ("get", "put", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"/api/farms/{farm.pk}",
                    data=self.payload, content_type="application/json")
                self.assertEqual(response.status_code, 404)
                farm.refresh_from_db()
                self.assertEqual(self.snapshot(farm), deleted)

    def test_http_extra_fields_do_not_control_managed_values(self):
        other = Organization.objects.create(code="OTHER", name="Other")
        fake_id = uuid4()
        fake_time = "2000-01-01T00:00:00Z"
        self.payload.update(organization=str(other.pk), id=str(fake_id), is_active=False,
                            deleted_at=fake_time, created_at=fake_time, updated_at=fake_time)
        before = timezone.now()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        farm = Farm.objects.get(pk=response.json()["id"])
        self.assertNotEqual(farm.pk, fake_id)
        self.assertEqual(farm.organization_id, self.organization.pk)
        self.assertTrue(farm.is_active)
        self.assertIsNone(farm.deleted_at)
        self.assertGreaterEqual(farm.created_at, before)
        self.assertGreaterEqual(farm.updated_at, before)
        original_id, created_at = farm.pk, farm.created_at
        self.payload["name"] = "Updated with extras"
        self.assertEqual(self.put(farm).status_code, 200)
        farm.refresh_from_db()
        self.assertEqual(farm.pk, original_id)
        self.assertEqual(farm.organization_id, self.organization.pk)
        self.assertTrue(farm.is_active)
        self.assertIsNone(farm.deleted_at)
        self.assertEqual(farm.created_at, created_at)
        self.assertGreaterEqual(farm.updated_at, before)
        self.assertEqual(farm.name, self.payload["name"])

    def test_http_put_requires_name_code_and_farm_type(self):
        farm = self.make_farm()
        original = self.snapshot(farm)
        for field in ("name", "code", "farm_type_id"):
            with self.subTest(missing=field):
                payload = dict(self.payload)
                del payload[field]
                response = self.client.put(f"/api/farms/{farm.pk}", payload, content_type="application/json")
                self.assertEqual(response.status_code, 422)
                self.assertTrue(any(error["loc"][-1] == field for error in response.json()["detail"]))
                farm.refresh_from_db()
                self.assertEqual(self.snapshot(farm), original)

    def test_http_put_omitted_optional_fields_replace_previous_values_with_defaults(self):
        farm = FarmService.create(self.context, FarmCreateSchema(**self.full_payload()))
        self.assertEqual(self.put(farm).status_code, 200)
        farm.refresh_from_db()
        for field in ("description", "address", "city", "state"):
            self.assertEqual(getattr(farm, field), "")
        self.assertEqual(farm.country, "México")

    def test_http_foreign_farm_hidden_and_mutations_leave_it_intact(self):
        own = self.make_farm()
        other = Organization.objects.create(code="OTHER", name="Other")
        foreign = self.make_farm(organization=other)
        original = self.snapshot(foreign)
        listing = self.client.get("/api/farms/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([item["id"] for item in listing.json()], [str(own.pk)])
        for method in ("get", "put", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"/api/farms/{foreign.pk}",
                    data=self.payload, content_type="application/json")
                self.assertEqual(response.status_code, 404)
                foreign.refresh_from_db()
                self.assertEqual(self.snapshot(foreign), original)

    def test_http_existing_farm_remains_readable_after_type_becomes_inactive(self):
        farm = self.make_farm()
        self.farm_type.is_active = False
        self.farm_type.save(update_fields=["is_active"])
        original = self.snapshot(farm)
        detail = self.client.get(f"/api/farms/{farm.pk}")
        self.assertEqual(detail.status_code, 200)
        self.assert_response_fields(detail.json(), farm)
        self.assertEqual(self.client.get("/api/farms/").json(), [detail.json()])
        farm.refresh_from_db()
        self.assertEqual(self.snapshot(farm), original)

    def test_inherited_restore_reactivates_soft_deleted_farm(self):
        farm = self.make_farm()
        farm.delete()
        farm.restore()
        farm.refresh_from_db()
        self.assertTrue(farm.is_active)
        self.assertIsNone(farm.deleted_at)
        self.assertEqual(FarmSelector.get_by_id(self.context, farm.pk).pk, farm.pk)

    def test_openapi_registers_farm_collection_and_detail_methods(self):
        response = self.client.get("/api/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertEqual(set(paths["/api/farms/"]), {"get", "post"})
        self.assertEqual(set(paths["/api/farms/{farm_id}"]), {"get", "put", "delete"})
