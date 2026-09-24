from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.animals.models import Animal
from apps.breeding.api.schemas import BreedingCreateSchema
from apps.breeding.models import BreedingEvent
from apps.breeding.services import BreedingService
from apps.catalogs.models import AnimalStatus, Breed, BreedingType, Gender, Species
from apps.common.context.context import RequestContext
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
        female_gender = Gender.objects.create(
            code="F",
            name="Test female",
        )
        male_gender = Gender.objects.create(
            code="M",
            name="Test male",
        )
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
