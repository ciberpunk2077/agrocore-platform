from datetime import date

from django.test import TestCase

from apps.animals.models import Animal
from apps.breeding.api.schemas import BreedingCreateSchema
from apps.breeding.models import BreedingEvent
from apps.breeding.services import BreedingService
from apps.catalogs.models import AnimalStatus, Breed, BreedingType, Gender, Species
from apps.common.context.context import RequestContext
from apps.organizations.models import Organization


class BreedingServiceUpdateTests(TestCase):
    def test_update_loads_relations_with_context_and_preserves_event(self):
        organization = Organization.objects.create(
            code="TEST_BREEDING",
            name="Test breeding organization",
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
            code="TEST_F",
            name="Test female",
        )
        male_gender = Gender.objects.create(
            code="TEST_M",
            name="Test male",
        )
        status = AnimalStatus.objects.create(
            code="TEST_STATUS",
            name="Test breeding status",
        )
        animal_fields = {
            "organization": organization,
            "species": species,
            "breed": breed,
            "status": status,
        }
        original_animal = Animal.objects.create(
            **animal_fields,
            gender=female_gender,
            internal_id="TEST_FEMALE_1",
        )
        new_animal = Animal.objects.create(
            **animal_fields,
            gender=female_gender,
            internal_id="TEST_FEMALE_2",
        )
        original_male = Animal.objects.create(
            **animal_fields,
            gender=male_gender,
            internal_id="TEST_MALE_1",
        )
        new_male = Animal.objects.create(
            **animal_fields,
            gender=male_gender,
            internal_id="TEST_MALE_2",
        )
        original_type = BreedingType.objects.create(
            code="TEST_TYPE_1",
            name="Test original breeding type",
        )
        new_type = BreedingType.objects.create(
            code="TEST_TYPE_2",
            name="Test new breeding type",
        )
        event = BreedingEvent.objects.create(
            organization=organization,
            animal=original_animal,
            male=original_male,
            breeding_type=original_type,
            date=date(2025, 1, 1),
            expected_birth=date(2025, 10, 1),
            technician="Original technician",
            notes="Original notes",
        )
        original_id = event.pk
        original_organization_id = event.organization_id
        context = RequestContext(organization=organization)
        payload = BreedingCreateSchema(
            animal_id=new_animal.pk,
            male_id=new_male.pk,
            breeding_type_id=new_type.pk,
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
        self.assertEqual(event.animal_id, new_animal.pk)
        self.assertEqual(event.male_id, new_male.pk)
        self.assertEqual(event.breeding_type_id, new_type.pk)
        self.assertEqual(event.date, payload.date)
        self.assertEqual(event.expected_birth, payload.expected_birth)
        self.assertEqual(event.technician, payload.technician)
        self.assertEqual(event.notes, payload.notes)
        self.assertEqual(BreedingEvent._base_manager.count(), 1)
