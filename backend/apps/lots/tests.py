from unittest.mock import patch
from uuid import UUID, uuid4
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.animals.models import Animal
from apps.animal_movements.models import AnimalMovement
from apps.animal_movements.selectors import AnimalMovementSelector
from apps.catalogs.models import AnimalStatus, Breed, FarmType, Gender, MovementType, Species
from apps.common.context.context import RequestContext
from apps.common.exceptions.lot import LotValidationError
from apps.farms.models import Farm
from apps.lots.api.schemas import LotCreateSchema, LotUpdateSchema
from apps.lots.models import Lot
from apps.lots.services import LotService
from apps.lots.selectors import LotSelector
from apps.organizations.models import Organization


class LotHardeningTests(TestCase):
    """Regression coverage for the local Lots hardening patch."""

    @classmethod
    def setUpTestData(cls):
        cls.organization_a = Organization.objects.create(code="LOTS_A", name="Lots A")
        cls.organization_b = Organization.objects.create(code="LOTS_B", name="Lots B")
        farm_type = FarmType.objects.create(code="LOTS", name="Lots farm type")
        cls.farm_a = Farm.objects.create(
            organization=cls.organization_a, farm_type=farm_type, code="FARM-A", name="Farm A",
        )
        cls.farm_b = Farm.objects.create(
            organization=cls.organization_b, farm_type=farm_type, code="FARM-B", name="Farm B",
        )
        cls.user = User.objects.create_user(email="lots-characterization@example.com", is_active=True)
        Membership.objects.create(
            user=cls.user, organization=cls.organization_a,
            role=Membership.Role.OWNER, is_default=True, is_active=True,
        )

    def setUp(self):
        self.client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {create_access_token(self.user)}"
        self.payload = {"farm_id": str(self.farm_a.pk), "code": "LOT-001", "name": "Lot 1"}

    def post(self, payload=None):
        return self.client.post("/api/lots/", payload or self.payload, content_type="application/json")

    def snapshot(self, instance):
        return {field.attname: getattr(instance, field.attname) for field in instance._meta.concrete_fields}

    def test_http_create_returns_400_for_schema_accepted_invalid_name(self):
        self.payload["name"] = "N" * 201
        self.assertEqual(LotCreateSchema(**self.payload).name, self.payload["name"])
        with patch.object(Lot, "full_clean", autospec=True, side_effect=Lot.full_clean) as clean:
            with patch.object(Lot, "save", autospec=True, side_effect=Lot.save) as save:
                response = self.post()
                clean.assert_called_once()
                save.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertIn("200", response.json()["detail"])
        self.assertIn("201", response.json()["detail"])
        self.assertIn("characters", response.json()["detail"])
        self.assertEqual(Lot._base_manager.count(), 0)

    def test_http_create_returns_400_for_unavailable_farm(self):
        self.farm_a.delete()
        for label, farm_id in (
            ("missing", uuid4()), ("inactive", self.farm_a.pk), ("foreign", self.farm_b.pk),
        ):
            with self.subTest(farm=label):
                with patch.object(Lot, "save", autospec=True, side_effect=Lot.save) as save:
                    response = self.post(dict(self.payload, farm_id=str(farm_id)))
                    save.assert_not_called()
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail":
                    "La unidad productiva no existe o no pertenece a la organización actual."})
                self.assertEqual(Lot._base_manager.count(), 0)

    def test_http_create_returns_400_for_soft_deleted_code_without_save(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        lot = Lot.objects.get(pk=response.json()["id"])
        self.assertEqual(lot.organization_id, self.organization_a.pk)
        response = self.client.delete(f"/api/lots/{lot.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        lot.refresh_from_db()
        self.assertFalse(lot.is_active)
        self.assertIsNotNone(lot.deleted_at)
        original = self.snapshot(lot)
        with patch.object(Lot, "save", autospec=True, side_effect=Lot.save) as save:
            response = self.post()
            save.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": self.reserved_message})
        self.assertEqual(Lot._base_manager.count(), 1)
        self.assertEqual(Lot.objects.count(), 0)
        lot.refresh_from_db()
        self.assertEqual(self.snapshot(lot), original)

    def test_direct_update_rejects_foreign_instance_without_changes(self):
        lot = Lot.objects.create(
            organization=self.organization_a, farm=self.farm_a, code="LOT-001", name="Lot A",
        )
        data = LotUpdateSchema(farm_id=self.farm_b.pk, code="UPDATED", name="Updated by B")
        original = self.snapshot(lot)
        with self.assertRaisesMessage(LotValidationError, self.instance_message):
            LotService.update(lot, RequestContext(organization=self.organization_b), data)
        self.assertEqual(self.snapshot(lot), original)
        lot.refresh_from_db()
        self.assertEqual(lot.organization_id, self.organization_a.pk)
        self.assertEqual(self.snapshot(lot), original)
        self.assertEqual(lot.organization_id, lot.farm.organization_id)

    def test_http_update_rejects_farm_change_with_active_animal(self):
        destination = Farm.objects.create(
            organization=self.organization_a, farm_type=self.farm_a.farm_type,
            code="FARM-A2", name="Second farm in A",
        )
        lot = Lot.objects.create(
            organization=self.organization_a, farm=self.farm_a, code="LOT-001", name="Lot 1",
        )
        species = Species.objects.create(code="LOTS", name="Lots species")
        breed = Breed.objects.create(species=species, code="LOTS", name="Lots breed")
        gender = Gender.objects.create(code="LOT_HTTP_G", name="Lot HTTP fixture gender")
        status = AnimalStatus.objects.create(code="LOTS", name="Lots status")
        animal = Animal.objects.create(
            organization=self.organization_a, farm=self.farm_a, lot=lot,
            species=species, breed=breed, gender=gender, status=status, internal_id="LOTS-ANIMAL",
        )
        original_animal = self.snapshot(animal)
        original_lot = self.snapshot(lot)
        self.assertEqual(animal.farm_id, animal.lot.farm_id)
        response = self.client.put(
            f"/api/lots/{lot.pk}", dict(self.payload, farm_id=str(destination.pk)),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": self.farm_change_message})
        lot.refresh_from_db()
        animal.refresh_from_db()
        self.assertEqual(self.snapshot(lot), original_lot)
        self.assertEqual(animal.farm_id, self.farm_a.pk)
        self.assertEqual(animal.lot_id, lot.pk)
        self.assertEqual(animal.farm_id, animal.lot.farm_id)
        self.assertEqual(self.snapshot(animal), original_animal)

    reserved_message = "El código ya está reservado por un lote de esta organización."
    instance_message = "El lote no existe o no pertenece a la organización actual."
    farm_change_message = "No se puede cambiar la unidad productiva del lote mientras tenga animales activos asociados."

    def make_lot(self, code="EXISTING", organization=None, farm=None):
        return Lot.objects.create(organization=organization or self.organization_a,
                                  farm=farm or self.farm_a, code=code, name="Original")

    def context(self):
        return RequestContext(organization=self.organization_a)

    def update(self, lot, **changes):
        return LotService.update(lot, self.context(), LotUpdateSchema(**dict(self.payload, **changes)))

    def make_animal(self, lot):
        species = Species.objects.create(code="TEST", name="Test species")
        breed = Breed.objects.create(species=species, code="TEST", name="Test breed")
        gender = Gender.objects.get_or_create(code="LOT_HELP_G", defaults={"name": "Lot helper fixture gender"})[0]
        status = AnimalStatus.objects.create(code="TEST", name="Test status")
        return Animal.objects.create(organization=self.organization_a, farm=lot.farm, lot=lot,
            species=species, breed=breed, gender=gender, status=status, internal_id="TEST")

    def assert_http_soft_delete_preserves_relations(self, resource):
        destination = self.make_lot("DESTINATION")
        origin = self.make_lot("ORIGIN")
        animal = self.make_animal(destination)
        movement_type, _ = MovementType.objects.get_or_create(
            code="TRANSFER", defaults={"name": "Transfer"},
        )
        movement = AnimalMovement.objects.create(
            organization=self.organization_a, animal=animal, movement_type=movement_type,
            origin_status=animal.status, origin_farm=self.farm_a, origin_lot=origin,
            destination_farm=self.farm_a, destination_lot=destination,
            date=timezone.localdate(), reason="Historical transfer",
        )
        preserved = [animal, movement, origin]
        if resource == "farms":
            target = self.farm_a
            preserved.append(destination)
        else:
            target = destination
            preserved.append(self.farm_a)
        before = [self.snapshot(item) for item in preserved]
        counts = {model: model._base_manager.count() for model in (Farm, Lot, Animal, AnimalMovement)}
        response = self.client.delete(f"/api/{resource}/{target.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertIsNotNone(target.deleted_at)
        for item, snapshot in zip(preserved, before):
            item.refresh_from_db()
            self.assertEqual(self.snapshot(item), snapshot)
        for model, count in counts.items():
            self.assertEqual(model._base_manager.count(), count)
        self.assertEqual(list(AnimalMovementSelector.history(self.context(), animal.pk)), [movement])
        history = self.client.get(f"/api/animal-movements/animal/{animal.pk}/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual([item["id"] for item in history.json()], [str(movement.pk)])
        self.assertEqual(history.json()[0]["origin_lot_id"], str(origin.pk))
        self.assertEqual(history.json()[0]["destination_lot_id"], str(destination.pk))
        self.assertEqual(history.json()[0]["origin_farm_id"], str(self.farm_a.pk))
        self.assertEqual(history.json()[0]["destination_farm_id"], str(self.farm_a.pk))
        if resource == "farms":
            listing = self.client.get("/api/lots/")
            self.assertEqual(listing.status_code, 200)
            self.assertEqual({item["id"] for item in listing.json()}, {str(origin.pk), str(destination.pk)})
            for lot in (origin, destination):
                self.assertEqual(self.client.get(f"/api/lots/{lot.pk}").status_code, 200)

    def test_http_farm_soft_delete_preserves_lots_animals_and_historical_movements(self):
        self.assert_http_soft_delete_preserves_relations("farms")

    def test_http_lot_soft_delete_preserves_animals_and_historical_movements(self):
        self.assert_http_soft_delete_preserves_relations("lots")

    def test_create_and_update_allow_code_in_other_tenant(self):
        foreign = self.make_lot("LOT-001", self.organization_b, self.farm_b)
        original = self.snapshot(foreign)
        created = LotService.create(self.context(), LotCreateSchema(**self.payload))
        self.assertEqual(created.organization_id, self.organization_a.pk)
        # Remove the active tenant collision by using another code for that row.
        self.update(created, code="OTHER")
        self.update(created)
        created.refresh_from_db()
        self.assertEqual(created.code, "LOT-001")
        foreign.refresh_from_db()
        self.assertEqual(self.snapshot(foreign), original)
        self.assertEqual(Lot._base_manager.count(), 2)

    def test_update_allows_own_code(self):
        lot = self.make_lot("LOT-001")
        self.update(lot)
        lot.refresh_from_db()
        self.assertEqual((lot.code, lot.name), ("LOT-001", "Lot 1"))

    def test_create_and_update_reject_active_and_inactive_reserved_codes(self):
        reserved = self.make_lot("LOT-001")
        lot = self.make_lot()
        for inactive in (False, True):
            if inactive:
                reserved.delete()
            originals = [self.snapshot(reserved), self.snapshot(lot)]
            for operation in ("create", "update"):
                with self.subTest(inactive=inactive, operation=operation):
                    with patch.object(Lot, "save", autospec=True, side_effect=Lot.save) as save:
                        with self.assertRaisesMessage(LotValidationError, self.reserved_message):
                            if operation == "create":
                                LotService.create(self.context(), LotCreateSchema(**self.payload))
                            else:
                                self.update(lot)
                        save.assert_not_called()
                    self.assertEqual(self.snapshot(lot), originals[1])
                    reserved.refresh_from_db()
                    lot.refresh_from_db()
                    self.assertEqual([self.snapshot(reserved), self.snapshot(lot)], originals)
                    self.assertEqual(Lot._base_manager.count(), 2)

    def test_direct_create_and_update_translate_validation_and_restore_instance(self):
        lot = self.make_lot()
        original = self.snapshot(lot)
        for operation in ("create", "update"):
            with self.subTest(operation=operation):
                with self.assertRaises(LotValidationError) as raised:
                    if operation == "create":
                        LotService.create(self.context(), LotCreateSchema(**dict(self.payload, name="N" * 201)))
                    else:
                        self.update(lot, name="N" * 201)
                cause = raised.exception.__cause__
                self.assertIsInstance(cause, ValidationError)
                self.assertEqual(cause.error_dict["name"][0].code, "max_length")
                self.assertEqual(str(raised.exception), " ".join(cause.messages))
                self.assertEqual(self.snapshot(lot), original)
                lot.refresh_from_db()
                self.assertEqual(self.snapshot(lot), original)
                self.assertEqual(Lot._base_manager.count(), 1)

    def test_model_defaults_uuid_relations_and_timestamps(self):
        before = timezone.now()
        lot = self.make_lot()
        lot.refresh_from_db()
        self.assertIsInstance(lot.pk, UUID)
        self.assertEqual(lot.organization_id, self.organization_a.pk)
        self.assertEqual(lot.farm_id, self.farm_a.pk)
        self.assertEqual((lot.code, lot.name, lot.description, lot.capacity), ("EXISTING", "Original", "", 0))
        self.assertTrue(lot.is_active)
        self.assertIsNone(lot.deleted_at)
        self.assertLessEqual(before, lot.created_at)
        self.assertLessEqual(lot.created_at, lot.updated_at)
        self.assertLessEqual(lot.updated_at, timezone.now())
        created, updated = lot.created_at, lot.updated_at
        lot.name = "Changed"
        lot.save()
        lot.refresh_from_db()
        self.assertEqual(lot.created_at, created)
        self.assertGreaterEqual(lot.updated_at, updated)

    def test_model_allows_duplicate_names(self):
        first = self.make_lot("FIRST")
        second = self.make_lot("SECOND")
        second.full_clean()
        self.assertEqual(first.name, second.name)
        self.assertEqual(Lot.objects.count(), 2)

    def test_model_validates_required_text_code_length_and_numeric_capacity(self):
        # Name max_length is already covered through HTTP and direct service.
        for field, value, code in (("name", "", "blank"), ("code", "", "blank"),
                                    ("code", "C" * 31, "max_length"), ("capacity", -1, "min_value")):
            with self.subTest(field=field, code=code):
                lot = Lot(organization=self.organization_a, farm=self.farm_a, code="VALID", name="Valid")
                setattr(lot, field, value)
                with self.assertRaises(ValidationError) as raised:
                    lot.full_clean()
                self.assertEqual(raised.exception.error_dict[field][0].code, code)
        lot = Lot(organization=self.organization_a, farm=self.farm_a, code="ZERO", name="Zero", capacity=0)
        lot.full_clean()
        lot.save()
        lot.refresh_from_db()
        self.assertEqual(lot.capacity, 0)

    def test_selector_list_scopes_filters_orders_and_loads_relations(self):
        zulu = self.make_lot("Z")
        zulu.name = "Zulu"
        zulu.save()
        alpha = self.make_lot("A")
        alpha.name = "Alpha"
        alpha.save()
        self.make_lot("INACTIVE").delete()
        self.make_lot("FOREIGN", self.organization_b, self.farm_b)
        with self.assertNumQueries(1):
            lots = list(LotSelector.list(self.context()))
            self.assertEqual([lot.pk for lot in lots], [alpha.pk, zulu.pk])
            for lot in lots:
                self.assertEqual(lot.organization.name, self.organization_a.name)
                self.assertEqual(lot.farm.name, self.farm_a.name)

    def test_selector_detail_scopes_filters_and_loads_relations(self):
        own = self.make_lot()
        inactive = self.make_lot("INACTIVE")
        inactive.delete()
        foreign = self.make_lot("FOREIGN", self.organization_b, self.farm_b)
        with self.assertNumQueries(1):
            selected = LotSelector.get_by_id(self.context(), own.pk)
            self.assertEqual(selected.pk, own.pk)
            self.assertEqual(selected.organization.name, self.organization_a.name)
            self.assertEqual(selected.farm.name, self.farm_a.name)
        for identifier in (inactive.pk, foreign.pk, uuid4()):
            with self.subTest(identifier=identifier):
                self.assertIsNone(LotSelector.get_by_id(self.context(), identifier))

    def test_service_valid_create_and_update_persist_all_fields_and_defaults(self):
        payload = dict(self.payload, description="Description", capacity=15)
        lot = LotService.create(self.context(), LotCreateSchema(**payload))
        lot.refresh_from_db()
        self.assert_lot_payload(lot, payload)
        created = lot.created_at
        destination = Farm.objects.create(organization=self.organization_a,
            farm_type=self.farm_a.farm_type, code="DEST", name="Destination")
        updated = dict(payload, farm_id=str(destination.pk), code="UPDATED", name="Updated",
                       description="Updated description", capacity=25)
        LotService.update(lot, self.context(), LotUpdateSchema(**updated))
        lot.refresh_from_db()
        self.assert_lot_payload(lot, updated)
        self.assertEqual(lot.created_at, created)
        defaults = LotService.create(self.context(), LotCreateSchema(**dict(self.payload, code="DEFAULTS")))
        defaults.refresh_from_db()
        self.assertEqual((defaults.description, defaults.capacity), ("", 0))

    def assert_lot_payload(self, lot, payload):
        self.assertEqual(lot.organization_id, self.organization_a.pk)
        for field, value in payload.items():
            self.assertEqual(getattr(lot, field), UUID(value) if field == "farm_id" else value)

    def response_body(self, lot):
        return dict(id=str(lot.pk), organization_id=str(lot.organization_id), farm_id=str(lot.farm_id),
                    code=lot.code, name=lot.name, description=lot.description, capacity=lot.capacity)

    def test_http_valid_crud_contract_and_soft_delete_lifecycle(self):
        payload = dict(self.payload, description="HTTP description", capacity=12)
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        lot = Lot.objects.get(pk=response.json()["id"])
        self.assert_lot_payload(lot, payload)
        self.assertEqual(response.json(), self.response_body(lot))
        listing = self.client.get("/api/lots/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json(), [self.response_body(lot)])
        detail = self.client.get(f"/api/lots/{lot.pk}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json(), self.response_body(lot))
        payload.update(code="HTTP-UPDATED", name="HTTP updated", description="New", capacity=20)
        response = self.client.put(f"/api/lots/{lot.pk}", payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        lot.refresh_from_db()
        self.assert_lot_payload(lot, payload)
        self.assertEqual(response.json(), self.response_body(lot))
        response = self.client.delete(f"/api/lots/{lot.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        lot.refresh_from_db()
        self.assertFalse(lot.is_active)
        self.assertIsNotNone(lot.deleted_at)
        self.assertEqual(Lot._base_manager.count(), 1)
        original = self.snapshot(lot)
        listing = self.client.get("/api/lots/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json(), [])
        for method in ("get", "put", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"/api/lots/{lot.pk}", payload,
                                                       content_type="application/json")
                self.assertEqual(response.status_code, 404)
                lot.refresh_from_db()
                self.assertEqual(self.snapshot(lot), original)

    def test_http_extra_fields_cannot_control_persisted_server_values(self):
        fake_id = uuid4()
        fake_time = "2000-01-01T00:00:00Z"
        payload = dict(self.payload, id=str(fake_id), organization=str(self.organization_b.pk),
            organization_id=str(self.organization_b.pk), is_active=False, deleted_at=fake_time,
            created_at=fake_time, updated_at=fake_time)
        before = timezone.now()
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        lot = Lot.objects.get(pk=response.json()["id"])
        self.assertNotEqual(lot.pk, fake_id)
        original_id, created = lot.pk, lot.created_at
        for operation in ("post", "put"):
            with self.subTest(operation=operation):
                if operation == "put":
                    payload["name"] = "Updated with extras"
                    response = self.client.put(f"/api/lots/{lot.pk}", payload, content_type="application/json")
                    self.assertEqual(response.status_code, 200)
                    lot.refresh_from_db()
                    self.assertEqual(lot.name, payload["name"])
                self.assertEqual(lot.pk, original_id)
                self.assertEqual(lot.organization_id, self.organization_a.pk)
                self.assertEqual(lot.farm_id, self.farm_a.pk)
                self.assertTrue(lot.is_active)
                self.assertIsNone(lot.deleted_at)
                self.assertEqual(lot.created_at, created)
                self.assertGreaterEqual(lot.created_at, before)
                self.assertGreaterEqual(lot.updated_at, before)

    def test_http_put_requires_farm_code_and_name_without_writes(self):
        lot = self.make_lot()
        original = self.snapshot(lot)
        for field in ("farm_id", "code", "name"):
            with self.subTest(missing=field):
                payload = dict(self.payload)
                del payload[field]
                response = self.client.put(f"/api/lots/{lot.pk}", payload, content_type="application/json")
                self.assertEqual(response.status_code, 422)
                self.assertTrue(any(error["loc"][-1] == field for error in response.json()["detail"]))
                lot.refresh_from_db()
                self.assertEqual(self.snapshot(lot), original)

    def test_http_put_omitted_optionals_replace_existing_values_with_defaults(self):
        lot = LotService.create(self.context(), LotCreateSchema(**dict(self.payload, description="Previous", capacity=20)))
        response = self.client.put(f"/api/lots/{lot.pk}", self.payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        lot.refresh_from_db()
        self.assertEqual((lot.description, lot.capacity), ("", 0))

    def test_http_foreign_lot_hidden_and_mutations_leave_row_intact(self):
        own = self.make_lot()
        foreign = self.make_lot("FOREIGN", self.organization_b, self.farm_b)
        original = self.snapshot(foreign)
        response = self.client.get("/api/lots/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [self.response_body(own)])
        for method in ("get", "put", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"/api/lots/{foreign.pk}", self.payload,
                                                       content_type="application/json")
                self.assertEqual(response.status_code, 404)
                foreign.refresh_from_db()
                self.assertEqual(self.snapshot(foreign), original)

    def test_existing_lot_under_inactive_farm_current_http_behavior(self):
        lot = self.make_lot()
        original = self.snapshot(lot)
        self.farm_a.delete()
        response = self.client.get("/api/lots/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [self.response_body(lot)])
        response = self.client.get(f"/api/lots/{lot.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.response_body(lot))
        response = self.client.put(f"/api/lots/{lot.pk}", self.payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail":
            "La unidad productiva no existe o no pertenece a la organización actual."})
        lot.refresh_from_db()
        self.assertEqual(self.snapshot(lot), original)
        self.assertEqual(self.client.delete(f"/api/lots/{lot.pk}").status_code, 200)
        lot.refresh_from_db()
        self.assertFalse(lot.is_active)

    def test_inherited_restore_reactivates_lot_without_animals(self):
        lot = self.make_lot()
        lot.delete()
        lot.restore()
        lot.refresh_from_db()
        self.assertTrue(lot.is_active)
        self.assertIsNone(lot.deleted_at)
        self.assertEqual(LotSelector.get_by_id(self.context(), lot.pk).pk, lot.pk)

    def test_openapi_registers_lot_collection_and_detail_methods(self):
        response = self.client.get("/api/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertEqual(set(paths["/api/lots/"]), {"get", "post"})
        self.assertEqual(set(paths["/api/lots/{lot_id}"]), {"get", "put", "delete"})

    def test_real_db_constraint_defense_create_and_update_rolls_back(self):
        reserved = self.make_lot("LOT-001")
        reserved.delete()
        lot = self.make_lot()
        originals = [self.snapshot(reserved), self.snapshot(lot)]
        for operation in ("create", "update"):
            with self.subTest(operation=operation):
                # Only omit precheck; real full_clean ignores the inactive row,
                # and real save reaches the database UNIQUE constraint.
                with patch.object(LotService, "_validate_reserved_code"):
                    with self.assertRaises(LotValidationError) as raised:
                        if operation == "create":
                            LotService.create(self.context(), LotCreateSchema(**self.payload))
                        else:
                            self.update(lot)
                self.assertEqual(str(raised.exception), self.reserved_message)
                self.assertIsInstance(raised.exception.__cause__, IntegrityError)
                self.assertIn("UNIQUE constraint failed: lots.organization_id, lots.code",
                              str(raised.exception.__cause__))
                self.assertEqual(self.snapshot(lot), originals[1])
                self.assertEqual(Lot._base_manager.count(), 2)
                reserved.refresh_from_db()
                lot.refresh_from_db()
                self.assertEqual([self.snapshot(reserved), self.snapshot(lot)], originals)

    def test_unrelated_real_integrity_error_propagates_create_and_update(self):
        lot = self.make_lot()
        original = self.snapshot(lot)
        real_save = Lot.save

        def invalid_save(instance, *args, **kwargs):
            instance.name = None
            return real_save(instance, *args, **kwargs)

        for operation in ("create", "update"):
            with self.subTest(operation=operation):
                with patch.object(Lot, "save", autospec=True, side_effect=invalid_save):
                    with self.assertRaises(IntegrityError) as raised:
                        if operation == "create":
                            LotService.create(self.context(), LotCreateSchema(**self.payload))
                        else:
                            self.update(lot)
                self.assertIn("NOT NULL", str(raised.exception))
                self.assertEqual(Lot._base_manager.count(), 1)
                lot.refresh_from_db()
                self.assertEqual(self.snapshot(lot), original)

    def test_constraint_name_recognition_is_exact(self):
        for name, expected in (("unique_lot_code_per_organization", True), ("other_constraint", False)):
            with self.subTest(name=name):
                cause = Exception("Backend error")
                cause.diag = SimpleNamespace(constraint_name=name)
                error = IntegrityError("Backend error")
                error.__cause__ = cause
                self.assertEqual(LotService._is_reserved_code_error(error), expected)

    def test_update_and_delete_reject_inactive_stale_and_missing_instances(self):
        lot = self.make_lot()
        stale = Lot.objects.get(pk=lot.pk)
        lot.delete()
        original = self.snapshot(lot)
        missing = Lot(organization=self.organization_a, farm=self.farm_a, code="MISSING", name="Missing")
        for instance in (lot, stale, missing):
            for operation in ("update", "delete"):
                with self.subTest(instance=instance.pk, operation=operation):
                    before = self.snapshot(instance)
                    with self.assertRaisesMessage(LotValidationError, self.instance_message):
                        if operation == "update":
                            self.update(instance)
                        else:
                            LotService.delete(instance, self.context())
                    self.assertEqual(self.snapshot(instance), before)
                    lot.refresh_from_db()
                    self.assertEqual(self.snapshot(lot), original)

    def test_update_and_delete_reject_missing_organization(self):
        lot = self.make_lot()
        original = self.snapshot(lot)
        for operation in ("update", "delete"):
            with self.subTest(operation=operation):
                with self.assertRaisesMessage(LotValidationError, self.instance_message):
                    if operation == "update":
                        LotService.update(lot, RequestContext(), LotUpdateSchema(**self.payload))
                    else:
                        LotService.delete(lot, RequestContext())
                self.assertEqual(self.snapshot(lot), original)
                lot.refresh_from_db()
                self.assertEqual(self.snapshot(lot), original)

    def test_delete_rejects_foreign_lot_without_changes(self):
        lot = self.make_lot(organization=self.organization_b, farm=self.farm_b)
        original = self.snapshot(lot)
        with self.assertRaisesMessage(LotValidationError, self.instance_message):
            LotService.delete(lot, self.context())
        self.assertEqual(self.snapshot(lot), original)
        lot.refresh_from_db()
        self.assertEqual(self.snapshot(lot), original)

    def test_direct_delete_own_active_lot_without_animals(self):
        lot = self.make_lot()
        LotService.delete(lot, self.context())
        lot.refresh_from_db()
        self.assertFalse(lot.is_active)
        self.assertIsNotNone(lot.deleted_at)
        self.assertEqual(Lot._base_manager.count(), 1)
        self.assertEqual(Lot.objects.count(), 0)

    def test_farm_change_without_animals_is_allowed(self):
        lot = self.make_lot()
        destination = Farm.objects.create(organization=self.organization_a,
            farm_type=self.farm_a.farm_type, code="DEST", name="Destination")
        self.update(lot, farm_id=destination.pk)
        lot.refresh_from_db()
        self.assertEqual(lot.farm_id, destination.pk)

    def test_farm_change_with_only_inactive_animals_is_allowed(self):
        lot = self.make_lot()
        animal = self.make_animal(lot)
        animal.delete()
        original = self.snapshot(animal)
        destination = Farm.objects.create(organization=self.organization_a,
            farm_type=self.farm_a.farm_type, code="DEST", name="Destination")
        self.update(lot, farm_id=destination.pk)
        lot.refresh_from_db()
        animal.refresh_from_db()
        self.assertEqual(lot.farm_id, destination.pk)
        self.assertEqual(self.snapshot(animal), original)

    def test_same_farm_with_active_animal_allows_editing_fields(self):
        lot = self.make_lot()
        animal = self.make_animal(lot)
        original = self.snapshot(animal)
        self.update(lot, name="Edited", description="New description", capacity=10)
        lot.refresh_from_db()
        animal.refresh_from_db()
        self.assertEqual((lot.name, lot.description, lot.capacity), ("Edited", "New description", 10))
        self.assertEqual(lot.farm_id, self.farm_a.pk)
        self.assertEqual(self.snapshot(animal), original)

    def test_update_unavailable_farm_preserves_instance_and_original_cause(self):
        lot = self.make_lot()
        original = self.snapshot(lot)
        inactive = Farm.objects.create(organization=self.organization_a,
            farm_type=self.farm_a.farm_type, code="INACTIVE", name="Inactive", is_active=False)
        for identifier in (uuid4(), inactive.pk, self.farm_b.pk):
            with self.subTest(identifier=identifier):
                with self.assertRaises(LotValidationError) as raised:
                    self.update(lot, farm_id=identifier)
                self.assertIsInstance(raised.exception.__cause__, Farm.DoesNotExist)
                self.assertEqual(str(raised.exception),
                    "La unidad productiva no existe o no pertenece a la organización actual.")
                self.assertEqual(self.snapshot(lot), original)
                lot.refresh_from_db()
                self.assertEqual(self.snapshot(lot), original)
