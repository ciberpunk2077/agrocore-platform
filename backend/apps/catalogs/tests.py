from django.test import TestCase

from apps.catalogs.models import (
    AnimalStatus,
    Breed,
    BreedingType,
    FarmType,
    Gender,
    MovementType,
    Species,
    WeighingMethod,
)
from apps.catalogs.services import CatalogService


class CatalogServiceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.species_a = Species.objects.create(
            code="CAT_SPECIES_A",
            name="Catalog Species A",
        )

        cls.species_b = Species.objects.create(
            code="CAT_SPECIES_B",
            name="Catalog Species B",
        )

        cls.breed_a1 = Breed.objects.create(
            species=cls.species_a,
            code="CAT_BREED_A1",
            name="Catalog Breed A1",
        )

        cls.breed_a2 = Breed.objects.create(
            species=cls.species_a,
            code="CAT_BREED_A2",
            name="Catalog Breed A2",
        )

        cls.breed_b1 = Breed.objects.create(
            species=cls.species_b,
            code="CAT_BREED_B1",
            name="Catalog Breed B1",
        )

        cls.gender = Gender.objects.create(
            code="CAT_GENDER",
            name="Catalog Gender",
        )

        cls.animal_status = AnimalStatus.objects.create(
            code="CAT_STATUS",
            name="Catalog Status",
        )

        cls.movement_type = MovementType.objects.create(
            code="CAT_MOVEMENT",
            name="Catalog Movement",
        )

        cls.breeding_type = BreedingType.objects.create(
            code="CAT_BREEDING",
            name="Catalog Breeding",
        )

        cls.weighing_method = WeighingMethod.objects.create(
            code="CAT_WEIGHING",
            name="Catalog Weighing",
        )

        cls.farm_type = FarmType.objects.create(
            code="CAT_FARM",
            name="Catalog Farm",
            description="Catalog test farm type",
        )

        cls.inactive_species = Species.objects.create(
            code="CAT_SPECIES_INACTIVE",
            name="Catalog Species Inactive",
            is_active=False,
        )

    def test_get_farm_types_returns_only_active_records(self):
        results = CatalogService.get_farm_types()

        self.assertIn(self.farm_type, results)

    def test_get_species_returns_only_active_records(self):
        results = CatalogService.get_species()

        self.assertIn(self.species_a, results)
        self.assertIn(self.species_b, results)
        self.assertNotIn(self.inactive_species, results)

    def test_get_breeds_returns_all_active_breeds(self):
        results = CatalogService.get_breeds()

        self.assertIn(self.breed_a1, results)
        self.assertIn(self.breed_a2, results)
        self.assertIn(self.breed_b1, results)

    def test_get_breeds_can_filter_by_species(self):
        results = CatalogService.get_breeds(
            species_id=self.species_a.pk,
        )

        self.assertEqual(
            set(results),
            {
                self.breed_a1,
                self.breed_a2,
            },
        )

    def test_get_genders_returns_active_records(self):
        results = CatalogService.get_genders()

        self.assertIn(self.gender, results)

    def test_get_animal_statuses_returns_active_records(self):
        results = CatalogService.get_animal_statuses()

        self.assertIn(self.animal_status, results)

    def test_get_movement_types_returns_active_records(self):
        results = CatalogService.get_movement_types()

        self.assertIn(self.movement_type, results)

    def test_get_breeding_types_returns_active_records(self):
        results = CatalogService.get_breeding_types()

        self.assertIn(self.breeding_type, results)

    def test_get_weighing_methods_returns_active_records(self):
        results = CatalogService.get_weighing_methods()

        self.assertIn(self.weighing_method, results)