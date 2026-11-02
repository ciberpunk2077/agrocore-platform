from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.animals.models import Animal
from apps.breeding.api.schemas import BreedingCreateSchema
from apps.breeding.models import BreedingEvent
from apps.breeding.services import BreedingService
from apps.breeding.selectors import BreedingSelector
from apps.catalogs.models import AnimalStatus, Breed, BreedingType, Gender, Species
from apps.common.context.context import RequestContext
from apps.common.exceptions.breeding import BreedingValidationError
from apps.organizations.models import Organization


class BreedingTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization = Organization.objects.create(
            code="TEST_BREEDING",
            name="Test breeding organization",
        )
        cls.other_organization = Organization.objects.create(
            code="TEST_BREEDING_OTHER",
            name="Test other breeding organization",
        )
        species = Species.objects.create(
            code="TEST_SPECIES",
            name="Test breeding species",
        )
        breed = Breed.objects.create(
            species=species,
            code="TEST_BREED",
            name="Test breeding breed",
        )
        female_gender = Gender.objects.get(code="F")
        male_gender = Gender.objects.get(code="M")
        status = AnimalStatus.objects.create(
            code="TEST_STATUS",
            name="Test breeding status",
        )
        animal_fields = {
            "organization": cls.organization,
            "species": species,
            "breed": breed,
            "status": status,
        }
        cls.original_animal = Animal.objects.create(
            **animal_fields,
            gender=female_gender,
            internal_id="TEST_FEMALE_1",
        )
        cls.new_animal = Animal.objects.create(
            **animal_fields,
            gender=female_gender,
            internal_id="TEST_FEMALE_2",
        )
        cls.original_male = Animal.objects.create(
            **animal_fields,
            gender=male_gender,
            internal_id="TEST_MALE_1",
        )
        cls.new_male = Animal.objects.create(
            **animal_fields,
            gender=male_gender,
            internal_id="TEST_MALE_2",
        )
        other_animal_fields = {
            **animal_fields,
            "organization": cls.other_organization,
        }
        cls.other_female = Animal.objects.create(
            **other_animal_fields,
            gender=female_gender,
            internal_id="TEST_OTHER_FEMALE",
        )
        cls.other_male = Animal.objects.create(
            **other_animal_fields,
            gender=male_gender,
            internal_id="TEST_OTHER_MALE",
        )
        cls.original_type = BreedingType.objects.create(
            code="TEST_TYPE_1",
            name="Test original breeding type",
        )
        cls.new_type = BreedingType.objects.create(
            code="TEST_TYPE_2",
            name="Test new breeding type",
        )

    def make_event(self, **overrides):
        fields = {
            "organization": self.organization,
            "animal": self.original_animal,
            "male": self.original_male,
            "breeding_type": self.original_type,
            "date": date(2025, 1, 1),
            "expected_birth": date(2025, 10, 1),
            "technician": "Original technician",
            "notes": "Original notes",
        }
        fields.update(overrides)
        return BreedingEvent(**fields)


class BreedingModelValidationTests(BreedingTestBase):
    def test_full_clean_rejects_non_female_animal(self):
        event = self.make_event(animal=self.original_male, male=None)

        with self.assertRaises(ValidationError) as raised:
            event.full_clean()

        self.assertEqual(raised.exception.message_dict, {
            "animal": ["El animal reproductor principal debe ser una hembra."],
        })

    def test_full_clean_rejects_animal_from_other_organization(self):
        event = self.make_event(animal=self.other_female)

        with self.assertRaises(ValidationError) as raised:
            event.full_clean()

        self.assertEqual(raised.exception.message_dict, {
            "animal": [
                "La hembra no pertenece a la organización del evento reproductivo."
            ],
        })

    def test_full_clean_rejects_non_male_male(self):
        event = self.make_event(male=self.new_animal)

        with self.assertRaises(ValidationError) as raised:
            event.full_clean()

        self.assertEqual(raised.exception.message_dict, {
            "male": ["El animal seleccionado como macho debe ser un macho."],
        })

    def test_full_clean_rejects_male_from_other_organization(self):
        event = self.make_event(male=self.other_male)

        with self.assertRaises(ValidationError) as raised:
            event.full_clean()

        self.assertEqual(raised.exception.message_dict, {
            "male": [
                "El macho no pertenece a la organización del evento reproductivo."
            ],
        })

    def test_full_clean_rejects_same_animal_in_both_roles(self):
        # The sex checks currently reject these states before the ID check.
        # This tests rejection, not independent coverage of the ID comparison.
        cases = (
            (
                self.original_animal,
                "male",
                "El animal seleccionado como macho debe ser un macho.",
            ),
            (
                self.original_male,
                "animal",
                "El animal reproductor principal debe ser una hembra.",
            ),
        )
        for animal, field, message in cases:
            with self.subTest(gender=animal.gender.code):
                event = self.make_event(animal=animal, male=animal)

                with self.assertRaises(ValidationError) as raised:
                    event.full_clean()

                self.assertEqual(raised.exception.message_dict, {
                    field: [message],
                })

    def test_full_clean_accepts_valid_event(self):
        event = self.make_event()

        event.full_clean()


class BreedingServiceUpdateTests(BreedingTestBase):
    def test_update_loads_relations_with_context_and_preserves_event(self):
        event = self.make_event()
        event.save()
        original_id = event.pk
        original_organization_id = event.organization_id
        context = RequestContext(organization=self.organization)
        payload = BreedingCreateSchema(
            animal_id=self.new_animal.pk,
            male_id=self.new_male.pk,
            breeding_type_id=self.new_type.pk,
            date=date(2025, 2, 1),
            expected_birth=date(2025, 11, 1),
            technician="Updated technician",
            notes="Updated notes",
        )
        self.assertEqual(BreedingEvent._base_manager.count(), 1)

        result = BreedingService.update(event, context, payload)

        self.assertIs(result, event)
        self.assertEqual(result.pk, original_id)

        event.refresh_from_db()

        self.assertEqual(event.pk, original_id)
        self.assertEqual(event.organization_id, original_organization_id)
        self.assertEqual(event.animal_id, self.new_animal.pk)
        self.assertEqual(event.male_id, self.new_male.pk)
        self.assertEqual(event.breeding_type_id, self.new_type.pk)
        self.assertEqual(event.date, payload.date)
        self.assertEqual(event.expected_birth, payload.expected_birth)
        self.assertEqual(event.technician, payload.technician)
        self.assertEqual(event.notes, payload.notes)
        self.assertEqual(BreedingEvent._base_manager.count(), 1)


class BreedingServiceValidationTests(BreedingTestBase):
    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.today = date(2025, 3, 1)
        clock = patch(
            "apps.breeding.services.breeding_service.get_business_today",
            return_value=self.today,
        )
        clock.start()
        self.addCleanup(clock.stop)

    def payload(self, **overrides):
        data = dict(
            animal_id=self.original_animal.id,
            breeding_type_id=self.original_type.id,
            date=self.today,
        )
        data.update(overrides)
        return BreedingCreateSchema(**data)

    def assert_create_rejected(self, payload, message):
        before = list(BreedingEvent._base_manager.values())
        with self.assertRaisesMessage(BreedingValidationError, message):
            BreedingService.create(self.context, payload)
        self.assertEqual(list(BreedingEvent._base_manager.values()), before)

    def test_first_event_today_without_male_or_expected_birth_is_valid(self):
        self.assertFalse(BreedingEvent._base_manager.exists())
        event = BreedingService.create(self.context, self.payload())
        event.refresh_from_db()
        self.assertEqual(BreedingEvent._base_manager.count(), 1)
        self.assertEqual(event.date, self.today)
        self.assertEqual(event.organization_id, self.organization.id)
        self.assertEqual(event.animal_id, self.original_animal.id)
        self.assertIsNone(event.male_id)
        self.assertIsNone(event.expected_birth)

    def test_past_event_with_male_and_later_expected_birth_is_valid(self):
        event = BreedingService.create(self.context, self.payload(
            date=self.today - timedelta(days=1), male_id=self.original_male.id,
            expected_birth=self.today + timedelta(days=1),
        ))
        event.refresh_from_db()
        self.assertEqual(event.male_id, self.original_male.id)
        self.assertEqual(event.expected_birth, self.today + timedelta(days=1))

    def test_future_date_is_rejected_without_persistence(self):
        self.assert_create_rejected(
            self.payload(date=self.today + timedelta(days=1)),
            "La fecha del evento reproductivo no puede ser futura.",
        )

    def test_equal_or_earlier_expected_birth_is_rejected_without_persistence(self):
        for expected_birth in (self.today, self.today - timedelta(days=1)):
            with self.subTest(expected_birth=expected_birth):
                self.assert_create_rejected(
                    self.payload(expected_birth=expected_birth),
                    "La fecha estimada de parto debe ser posterior a la fecha del evento reproductivo.",
                )

    def test_incorrect_sexes_are_rejected(self):
        cases = (
            (dict(animal_id=self.original_male.id), "El animal reproductor principal debe ser una hembra."),
            (dict(male_id=self.new_animal.id), "El animal seleccionado como macho debe ser un macho."),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                self.assert_create_rejected(self.payload(**overrides), message)

    def test_foreign_relations_are_rejected(self):
        for overrides in (
            dict(animal_id=self.other_female.id), dict(male_id=self.other_male.id),
        ):
            with self.subTest(overrides=overrides):
                self.assert_create_rejected(
                    self.payload(**overrides),
                    "La hembra, el macho o el tipo de reproducción no existen.",
                )

    def test_inactive_relations_are_rejected(self):
        for relation, field in (
            (self.new_animal, "animal_id"), (self.new_male, "male_id"),
            (self.new_type, "breeding_type_id"),
        ):
            with self.subTest(field=field):
                relation.delete()
                self.assert_create_rejected(
                    self.payload(**{field: relation.id}),
                    "La hembra, el macho o el tipo de reproducción no existen.",
                )

    def test_update_rejects_invalid_dates_without_changing_event(self):
        event = self.make_event()
        event.save()
        before = list(BreedingEvent._base_manager.values())
        cases = (
            (dict(date=self.today + timedelta(days=1)), "La fecha del evento reproductivo no puede ser futura."),
            (dict(expected_birth=self.today), "La fecha estimada de parto debe ser posterior a la fecha del evento reproductivo."),
            (dict(expected_birth=self.today - timedelta(days=1)), "La fecha estimada de parto debe ser posterior a la fecha del evento reproductivo."),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesMessage(BreedingValidationError, message):
                    BreedingService.update(event, self.context, self.payload(**overrides))
                self.assertEqual(event.date, date(2025, 1, 1))
                self.assertEqual(event.expected_birth, date(2025, 10, 1))
                self.assertEqual(list(BreedingEvent._base_manager.values()), before)

    def test_update_accepts_today_and_optional_or_later_expected_birth(self):
        event = self.make_event()
        event.save()
        for expected_birth in (None, self.today + timedelta(days=1)):
            with self.subTest(expected_birth=expected_birth):
                BreedingService.update(event, self.context, self.payload(expected_birth=expected_birth))
                event.refresh_from_db()
                self.assertEqual(event.date, self.today)
                self.assertEqual(event.expected_birth, expected_birth)
                self.assertIsNone(event.male_id)
                self.assertEqual(BreedingEvent._base_manager.count(), 1)


class BreedingHistoryTests(BreedingTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create_user(email="breeding-history@example.com")
        cls.other_user = User.objects.create_user(email="other-breeding-history@example.com")
        for user, organization in (
            (cls.user, cls.organization), (cls.other_user, cls.other_organization),
        ):
            Membership.objects.create(
                user=user, organization=organization,
                role=Membership.Role.VIEWER, is_default=True,
            )

    def saved_event(self, **overrides):
        event = self.make_event(**overrides)
        event.save()
        return event

    def history(self, animal_id, user=None):
        response = self.client.get(
            f"/api/breeding/animal/{animal_id}/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user or self.user)}",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_history_filters_active_events_by_animal_and_orders_descending(self):
        oldest = self.saved_event(date=date(2025, 1, 1))
        newest = self.saved_event(date=date(2025, 3, 1))
        middle = self.saved_event(date=date(2025, 2, 1))
        deleted = self.saved_event()
        deleted.delete()
        self.saved_event(animal=self.new_animal)
        self.saved_event(organization=self.other_organization, animal=self.other_female, male=self.other_male)
        result = self.history(self.original_animal.id)
        self.assertEqual([item["id"] for item in result], [str(newest.id), str(middle.id), str(oldest.id)])
        self.assertTrue(all(item["animal_id"] == str(self.original_animal.id) for item in result))
        with self.assertNumQueries(1):
            events = list(BreedingSelector.history(
                RequestContext(organization=self.organization), self.original_animal.id,
            ))
        self.assertEqual([event.id for event in events], [newest.id, middle.id, oldest.id])

    def test_empty_missing_and_foreign_animals_return_empty_history(self):
        foreign = self.saved_event(
            organization=self.other_organization, animal=self.other_female, male=self.other_male,
        )
        for animal_id in (self.original_animal.id, uuid4(), self.other_female.id):
            with self.subTest(animal_id=animal_id):
                self.assertEqual(self.history(animal_id), [])
        self.assertEqual(
            [item["id"] for item in self.history(self.other_female.id, self.other_user)],
            [str(foreign.id)],
        )

    def test_inactive_animal_keeps_active_history(self):
        event = self.saved_event()
        self.original_animal.delete()
        self.assertEqual([item["id"] for item in self.history(self.original_animal.id)], [str(event.id)])

    def test_invalid_uuid_is_rejected_by_api(self):
        response = self.client.get(
            "/api/breeding/animal/not-a-uuid/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}",
        )
        self.assertEqual(response.status_code, 422)

    def test_openapi_history_contract_without_update_or_delete(self):
        from config.api import api

        paths = api.get_openapi_schema()["paths"]
        path = "/api/breeding/animal/{animal_id}/history"
        self.assertIn(path, paths)
        self.assertEqual(set(paths[path]), {"get"})
        operation = paths[path]["get"]
        parameter = next(p for p in operation["parameters"] if p["name"] == "animal_id")
        self.assertEqual(parameter["in"], "path")
        self.assertTrue(parameter["required"])
        self.assertEqual(parameter["schema"]["format"], "uuid")
        response = operation["responses"][200]["content"]["application/json"]["schema"]
        self.assertEqual(response["type"], "array")
        self.assertEqual(response["items"]["$ref"], "#/components/schemas/BreedingResponseSchema")
        for path, operations in paths.items():
            if path.startswith("/api/breeding/"):
                self.assertNotIn("put", operations)
                self.assertNotIn("delete", operations)


class BreedingCreateReadContractTests(BreedingTestBase):
    """FV1-6A certifies the existing public contract; adds no business rules."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create_user(email="breeding-create-contract@example.com")
        cls.membership = Membership.objects.create(
            user=cls.user, organization=cls.organization,
            role=Membership.Role.OPERATOR, is_default=True,
        )

    def setUp(self):
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {create_access_token(self.user)}"}

    def payload(self, **overrides):
        payload = {
            "animal_id": str(self.original_animal.pk),
            "breeding_type_id": str(self.original_type.pk),
            "date": "2025-01-01",
        }
        payload.update(overrides)
        return payload

    def post(self, **overrides):
        return self.client.post("/api/breeding/", self.payload(**overrides), content_type="application/json", **self.headers)

    def get(self, path):
        return self.client.get(path, **self.headers)

    def test_minimal_post_200_exact_shape_defaults_and_fresh_get(self):
        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(set(result), {"id", "animal_id", "male_id", "breeding_type_id", "date", "expected_birth", "technician", "notes"})
        self.assertEqual(result["animal_id"], str(self.original_animal.pk))
        self.assertEqual(result["breeding_type_id"], str(self.original_type.pk))
        self.assertEqual(result["date"], "2025-01-01")
        self.assertIsNone(result["male_id"])
        self.assertIsNone(result["expected_birth"])
        self.assertEqual(result["technician"], "")
        self.assertEqual(result["notes"], "")
        event = BreedingEvent.objects.get(pk=result["id"])
        self.assertEqual(event.organization_id, self.organization.pk)
        self.assertTrue(event.is_active)
        fresh = self.get(f"/api/breeding/{result['id']}")
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(fresh.json(), result)

    def test_full_post_preserves_text_spaces_and_nullable_fields(self):
        fields = dict(male_id=str(self.original_male.pk), expected_birth="2025-10-01", technician="  Técnico  ", notes="\n notas \n")
        response = self.post(**fields)
        self.assertEqual(response.status_code, 200)
        for key, value in fields.items():
            self.assertEqual(response.json()[key], value)

    def test_explicit_null_optional_relations_and_dates_are_valid(self):
        response = self.post(male_id=None, expected_birth=None)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["male_id"])
        self.assertIsNone(response.json()["expected_birth"])

    def test_null_texts_are_422_without_persistence(self):
        for field in ("technician", "notes"):
            with self.subTest(field=field):
                response = self.post(**{field: None})
                self.assertEqual(response.status_code, 422)
                self.assertFalse(BreedingEvent._base_manager.exists())

    def test_technician_150_accepted_and_151_returns_400(self):
        accepted = self.post(technician="x" * 150)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["technician"], "x" * 150)
        rejected = self.post(technician="x" * 151)
        self.assertEqual(rejected.status_code, 400)
        self.assertIsInstance(rejected.json()["detail"], str)
        self.assertEqual(BreedingEvent._base_manager.count(), 1)

    def test_sequential_equivalent_posts_remain_permitted(self):
        first, second = self.post(), self.post()
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertNotEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(BreedingEvent.objects.count(), 2)

    def test_all_four_writer_roles_create(self):
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.VETERINARIAN, Membership.Role.OPERATOR):
            with self.subTest(role=role):
                self.membership.role = role
                self.membership.save(update_fields=["role"])
                self.assertEqual(self.post().status_code, 200)
        self.assertEqual(BreedingEvent.objects.count(), 4)

    def test_viewer_reads_but_cannot_create_before_service(self):
        self.membership.role = Membership.Role.VIEWER
        self.membership.save(update_fields=["role"])
        with patch("apps.breeding.api.endpoints.BreedingService.create") as service:
            self.assertEqual(self.post().status_code, 403)
            service.assert_not_called()
        self.assertEqual(self.get("/api/breeding/").status_code, 200)
        self.assertFalse(BreedingEvent._base_manager.exists())

    def test_foreign_and_missing_relations_are_400(self):
        cases = (
            dict(animal_id=str(self.other_female.pk)), dict(male_id=str(self.other_male.pk)),
            dict(animal_id=str(uuid4())), dict(male_id=str(uuid4())), dict(breeding_type_id=str(uuid4())),
        )
        for fields in cases:
            with self.subTest(fields=fields):
                self.assertEqual(self.post(**fields).status_code, 400)
                self.assertFalse(BreedingEvent._base_manager.exists())

    def test_inactive_relations_are_400(self):
        for relation, field in ((self.new_animal, "animal_id"), (self.new_male, "male_id"), (self.new_type, "breeding_type_id")):
            with self.subTest(field=field):
                relation.delete()
                self.assertEqual(self.post(**{field: str(relation.pk)}).status_code, 400)
                self.assertFalse(BreedingEvent._base_manager.exists())

    def test_wrong_sexes_and_same_animal_are_400(self):
        for fields in (dict(animal_id=str(self.original_male.pk)), dict(male_id=str(self.new_animal.pk)), dict(male_id=str(self.original_animal.pk))):
            with self.subTest(fields=fields):
                self.assertEqual(self.post(**fields).status_code, 400)
                self.assertFalse(BreedingEvent._base_manager.exists())

    def test_list_history_detail_tenant_isolation(self):
        own = self.post().json()
        foreign = self.make_event(organization=self.other_organization, animal=self.other_female, male=self.other_male)
        foreign.save()
        self.assertEqual([item["id"] for item in self.get("/api/breeding/").json()], [own["id"]])
        history = self.get(f"/api/breeding/animal/{self.original_animal.pk}/history")
        self.assertEqual(history.json(), [own])
        self.assertEqual(self.get(f"/api/breeding/animal/{self.other_female.pk}/history").json(), [])
        self.assertEqual(self.get(f"/api/breeding/{foreign.pk}").status_code, 404)
        self.assertEqual(self.get(f"/api/breeding/{uuid4()}").status_code, 404)

    def test_soft_deleted_event_absent_from_list_history_and_detail(self):
        created = self.post().json()
        event = BreedingEvent.objects.get(pk=created["id"])
        event.delete()
        self.assertEqual(self.get("/api/breeding/").json(), [])
        self.assertEqual(self.get(f"/api/breeding/animal/{self.original_animal.pk}/history").json(), [])
        self.assertEqual(self.get(f"/api/breeding/{event.pk}").status_code, 404)
        persisted = BreedingEvent._base_manager.get(pk=event.pk)
        self.assertFalse(persisted.is_active)
        self.assertIsNotNone(persisted.deleted_at)

    def test_inactive_animal_still_allows_existing_event_reads(self):
        created = self.post().json()
        self.original_animal.delete()
        self.assertEqual(self.get(f"/api/breeding/{created['id']}").json(), created)
        self.assertEqual(self.get(f"/api/breeding/animal/{self.original_animal.pk}/history").json(), [created])

    def test_put_patch_delete_remain_unpublished(self):
        from config.api import api
        for path, operations in api.get_openapi_schema()["paths"].items():
            if path.startswith("/api/breeding/"):
                self.assertTrue(set(operations).issubset({"get", "post"}))
        created = self.post().json()
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"/api/breeding/{created['id']}", self.payload(), content_type="application/json", **self.headers)
                self.assertEqual(response.status_code, 405)
        self.assertTrue(BreedingEvent.objects.filter(pk=created["id"]).exists())

    def test_no_new_birth_date_or_type_specific_male_rule(self):
        Animal._base_manager.filter(pk=self.original_animal.pk).update(birth_date=date(2025, 2, 1))
        for breeding_type in (self.original_type, self.new_type):
            with self.subTest(type=breeding_type.code):
                response = self.post(breeding_type_id=str(breeding_type.pk), male_id=None)
                self.assertEqual(response.status_code, 200)

    def test_invalid_uuid_and_date_payload_are_422(self):
        for fields in (dict(animal_id="bad"), dict(male_id=""), dict(date="2025-02-30"), dict(expected_birth="")):
            with self.subTest(fields=fields):
                self.assertEqual(self.post(**fields).status_code, 422)
                self.assertFalse(BreedingEvent._base_manager.exists())


class BreedingTenantBusinessDateTests(BreedingTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create_user(email="tenant-date@example.com")
        Membership.objects.create(user=cls.user, organization=cls.organization, role=Membership.Role.OPERATOR, is_default=True)

    def post_date(self, value):
        return self.client.post("/api/breeding/", {
            "animal_id": str(self.original_animal.pk), "breeding_type_id": str(self.original_type.pk), "date": value,
        }, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def test_post_mexico_boundaries_without_mocking_localdate(self):
        from datetime import datetime
        for instant, tomorrow_status in (
            ("2026-10-05T23:30:00+00:00", 400),
            ("2026-10-06T00:30:00+00:00", 400),
            ("2026-10-06T05:59:59+00:00", 400),
            ("2026-10-06T06:00:00+00:00", 200),
        ):
            with self.subTest(instant=instant), patch("apps.common.temporal.timezone.now", return_value=datetime.fromisoformat(instant)):
                self.assertEqual(self.post_date("2026-10-05").status_code, 200)
                before = BreedingEvent.objects.count()
                response = self.post_date("2026-10-06")
                self.assertEqual(response.status_code, tomorrow_status, response.content)
                self.assertEqual(BreedingEvent.objects.count(), before + (tomorrow_status == 200))

    def test_corrupt_timezone_blocks_post_without_persistence(self):
        Organization._base_manager.filter(pk=self.organization.pk).update(timezone="invalid")
        response = self.post_date("2025-01-01")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "tenant_timezone_unavailable")
        self.assertFalse(BreedingEvent.objects.exists())

    def test_existing_future_record_remains_readable_and_unchanged(self):
        from datetime import datetime
        event = self.make_event(date=date(2026, 10, 6))
        event.save()
        with patch("apps.common.temporal.timezone.now", return_value=datetime.fromisoformat("2026-10-06T00:30:00+00:00")):
            response = self.client.get(f"/api/breeding/animal/{event.animal_id}/history", HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0]["date"], "2026-10-06")
            self.assertEqual(self.post_date("2026-10-06").status_code, 400)
        event.refresh_from_db()
        self.assertEqual(event.date, date(2026, 10, 6))


class BreedingDetailReadContractTests(BreedingTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create_user(email="breeding-detail@example.com")
        cls.membership = Membership.objects.create(user=cls.user, organization=cls.organization,
                                                  role=Membership.Role.VIEWER, is_default=True)

    def detail(self, event_id):
        return self.client.get(f"/api/breeding/{event_id}", HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def test_all_five_roles_read_exact_detail_contract(self):
        event = self.make_event(technician="  Técnico fresco  ", notes="\n Notas frescas \n")
        event.save()
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.VETERINARIAN,
                     Membership.Role.OPERATOR, Membership.Role.VIEWER):
            with self.subTest(role=role):
                Membership._base_manager.filter(pk=self.membership.pk).update(role=role)
                response = self.detail(event.pk)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {
                    "id": str(event.pk), "animal_id": str(event.animal_id), "male_id": str(event.male_id),
                    "breeding_type_id": str(event.breeding_type_id), "date": "2025-01-01", "expected_birth": "2025-10-01",
                    "technician": "  Técnico fresco  ", "notes": "\n Notas frescas \n",
                })

    def test_foreign_missing_and_soft_deleted_are_indistinguishable(self):
        foreign = self.make_event(organization=self.other_organization, animal=self.other_female, male=self.other_male)
        foreign.save()
        deleted = self.make_event()
        deleted.save()
        deleted.delete()
        responses = [self.detail(pk) for pk in (foreign.pk, uuid4(), deleted.pk)]
        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"detail": "Evento de reproducción no encontrado."})

    def test_historical_nullable_fields_and_inactive_animal_remain_readable(self):
        event = self.make_event(male=None, expected_birth=None, technician="", notes="", date=date(2099, 1, 1))
        event.save()
        self.original_animal.delete()
        Organization._base_manager.filter(pk=self.organization.pk).update(timezone="corrupt")
        response = self.detail(event.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["date"], "2099-01-01")
        for field in ("male_id", "expected_birth"):
            self.assertIsNone(response.json()[field])
        # The public schema also permits null texts, even though the current
        # database columns store blank strings rather than NULL.
        from apps.breeding.api.schemas import BreedingResponseSchema
        nullable = BreedingResponseSchema.model_validate({**response.json(), "technician": None, "notes": None})
        self.assertIsNone(nullable.technician)
        self.assertIsNone(nullable.notes)

    def test_detail_auth_and_invalid_role_reject_before_selector(self):
        event = self.make_event()
        event.save()
        with patch("apps.breeding.api.endpoints.BreedingSelector.get_by_id") as selector:
            self.assertEqual(self.client.get(f"/api/breeding/{event.pk}").status_code, 401)
            Membership._base_manager.filter(pk=self.membership.pk).update(role="UNKNOWN")
            self.assertEqual(self.detail(event.pk).status_code, 403)
            selector.assert_not_called()

    def test_detail_openapi_remains_get_only(self):
        from config.api import api
        operation = api.get_openapi_schema()["paths"]["/api/breeding/{event_id}"]
        self.assertEqual(set(operation), {"get"})
        response = operation["get"]["responses"][200]["content"]["application/json"]["schema"]
        self.assertEqual(response["$ref"], "#/components/schemas/BreedingResponseSchema")
