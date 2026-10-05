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
            "apps.breeding.services.breeding_service.timezone.localdate",
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
