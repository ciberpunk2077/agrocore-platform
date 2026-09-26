from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.animals.models import Animal
from apps.animals.api.schemas import AnimalCreateSchema, AnimalUpdateSchema
from apps.animals.services import AnimalService
from apps.catalogs.models import AnimalStatus, Breed, Gender, Species
from apps.catalogs.models import FarmType
from apps.common.context.context import RequestContext
from apps.common.exceptions import RelatedObjectNotFound
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization


class AnimalParentOrganizationRegressionTests(TestCase):
    """P1: reject cross-organization parents in model and service writes."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization_a = Organization.objects.create(
            code="P1_A", name="P1 organization A",
        )
        cls.organization_b = Organization.objects.create(
            code="P1_B", name="P1 organization B",
        )
        cls.species = Species.objects.create(code="P1", name="P1 species")
        cls.breed = Breed.objects.create(
            species=cls.species, code="P1", name="P1 breed",
        )
        cls.female = Gender.objects.create(code="F", name="P1 female")
        cls.male = Gender.objects.create(code="M", name="P1 male")
        cls.status = AnimalStatus.objects.create(code="P1", name="P1 status")
        parent_fields = {
            "organization": cls.organization_b,
            "species": cls.species,
            "breed": cls.breed,
            "status": cls.status,
            "is_active": True,
        }
        cls.mother_b = Animal.objects.create(
            **parent_fields, gender=cls.female, internal_id="P1_MOTHER_B",
        )
        cls.father_b = Animal.objects.create(
            **parent_fields, gender=cls.male, internal_id="P1_FATHER_B",
        )

    def make_animal_a(self, internal_id, gender=None):
        return Animal.objects.create(
            organization=self.organization_a,
            species=self.species,
            breed=self.breed,
            gender=gender or self.female,
            status=self.status,
            internal_id=internal_id,
            is_active=True,
        )

    def make_service_data(self):
        farm_type = FarmType.objects.create(code="P1", name="P1 farm type")
        farm = Farm.objects.create(
            organization=self.organization_a, farm_type=farm_type,
            code="P1_FARM", name="P1 farm",
        )
        lot = Lot.objects.create(
            organization=self.organization_a, farm=farm,
            code="P1_LOT", name="P1 lot",
        )
        return {
            "farm_id": farm.pk, "lot_id": lot.pk,
            "species_id": self.species.pk, "breed_id": self.breed.pk,
            "gender_id": self.female.pk, "status_id": self.status.pk,
            "official_tag": "", "electronic_tag": "", "name": "", "notes": "",
        }

    def test_model_rejects_parent_from_other_organization(self):
        for field, parent in (("mother", self.mother_b), ("father", self.father_b)):
            with self.subTest(parent=field):
                child = self.make_animal_a(f"P1_MODEL_{field}")
                setattr(child, field, parent)
                with self.assertRaises(ValidationError) as clean_error:
                    child.full_clean()
                self.assertEqual(
                    clean_error.exception.error_dict[field][0].code,
                    "parent_organization",
                )
                with self.assertRaises(ValidationError) as save_error:
                    child.save()
                self.assertEqual(
                    save_error.exception.error_dict[field][0].code,
                    "parent_organization",
                )
                child.refresh_from_db()
                self.assertEqual(child.organization_id, self.organization_a.pk)
                self.assertIsNone(child.mother_id)
                self.assertIsNone(child.father_id)

    def test_service_create_rejects_parent_from_other_organization(self):
        data = self.make_service_data()
        context = RequestContext(organization=self.organization_a)
        for field, parent in (("mother", self.mother_b), ("father", self.father_b)):
            with self.subTest(parent=field):
                payload = AnimalCreateSchema(
                    **data, internal_id=f"P1_CREATE_{field}",
                    **{f"{field}_id": parent.pk},
                )
                count_before = Animal._base_manager.count()
                with self.assertRaises(RelatedObjectNotFound) as error:
                    AnimalService.create(context, payload)
                self.assertEqual(
                    str(error.exception), "Uno de los registros relacionados no existe.",
                )
                self.assertEqual(Animal._base_manager.count(), count_before)
                self.assertFalse(Animal._base_manager.filter(
                    organization=self.organization_a, internal_id=payload.internal_id,
                ).exists())

    def test_service_update_rejects_parent_from_other_organization(self):
        data = self.make_service_data()
        context = RequestContext(organization=self.organization_a)
        mother_a = self.make_animal_a("P1_MOTHER_A", self.female)
        father_a = self.make_animal_a("P1_FATHER_A", self.male)
        for field, parent in (("mother", self.mother_b), ("father", self.father_b)):
            with self.subTest(parent=field):
                child = self.make_animal_a(f"P1_UPDATE_{field}")
                child.mother = mother_a
                child.father = father_a
                child.save()
                parents = {"mother_id": mother_a.pk, "father_id": father_a.pk}
                parents[f"{field}_id"] = parent.pk
                payload = AnimalUpdateSchema(
                    **data, internal_id=child.internal_id, **parents,
                )
                with self.assertRaises(RelatedObjectNotFound):
                    AnimalService.update(child, context, payload)
                child.refresh_from_db()
                self.assertEqual(child.organization_id, self.organization_a.pk)
                self.assertEqual(child.mother_id, mother_a.pk)
                self.assertEqual(child.father_id, father_a.pk)

    def test_service_accepts_parents_from_same_organization(self):
        data = self.make_service_data()
        mother_a = self.make_animal_a("P1_MOTHER_A", self.female)
        father_a = self.make_animal_a("P1_FATHER_A", self.male)
        payload = AnimalCreateSchema(
            **data, internal_id="P1_VALID_CHILD",
            mother_id=mother_a.pk, father_id=father_a.pk,
        )
        child = AnimalService.create(
            RequestContext(organization=self.organization_a), payload,
        )
        child.refresh_from_db()
        child.full_clean()
        self.assertEqual(child.organization_id, self.organization_a.pk)
        self.assertEqual(child.mother_id, mother_a.pk)
        self.assertEqual(child.father_id, father_a.pk)


class AnimalGenealogyRegressionTests(TestCase):
    """B5: reject genealogy cycles without changing persisted valid links."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization = Organization.objects.create(
            code="TEST_B5", name="B5 test organization",
        )
        cls.species = Species.objects.create(
            code="TEST_B5", name="B5 test species",
        )
        cls.breed = Breed.objects.create(
            species=cls.species, code="TEST_B5", name="B5 test breed",
        )
        cls.female = Gender.objects.create(code="F", name="B5 female")
        cls.male = Gender.objects.create(code="M", name="B5 male")
        cls.status = AnimalStatus.objects.create(
            code="TEST_B5", name="B5 test status",
        )

    def make_animal(self, internal_id, gender):
        return Animal.objects.create(
            organization=self.organization,
            species=self.species,
            breed=self.breed,
            gender=gender,
            status=self.status,
            internal_id=internal_id,
            is_active=True,
        )

    def test_existing_animal_cannot_be_its_own_parent(self):
        for field, gender in (("mother", self.female), ("father", self.male)):
            with self.subTest(parent=field):
                # Separate persisted animals keep the subtests independent.
                animal = self.make_animal(f"SELF_{field}", gender)
                self.assertIsNone(animal.mother_id)
                self.assertIsNone(animal.father_id)

                setattr(animal, field, animal)
                with self.assertRaises(ValidationError) as clean_error:
                    animal.full_clean()
                self.assertEqual(
                    clean_error.exception.error_dict[field][0].code,
                    "self_reference",
                )
                with self.assertRaises(ValidationError) as save_error:
                    animal.save()
                self.assertEqual(
                    save_error.exception.error_dict[field][0].code,
                    "self_reference",
                )
                animal.refresh_from_db()

                self.assertIsNone(animal.mother_id)
                self.assertIsNone(animal.father_id)

    def test_three_node_maternal_cycle_is_rejected(self):
        a = self.make_animal("MATERNAL_A", self.female)
        b = self.make_animal("MATERNAL_B", self.female)
        c = self.make_animal("MATERNAL_C", self.female)

        a.mother = b
        a.full_clean()
        a.save()
        b.mother = c
        b.full_clean()
        b.save()
        c.mother = a
        with self.assertRaises(ValidationError) as clean_error:
            c.full_clean()
        self.assertEqual(
            clean_error.exception.error_dict["mother"][0].code,
            "genealogy_cycle",
        )
        with self.assertRaises(ValidationError) as save_error:
            c.save()
        self.assertEqual(
            save_error.exception.error_dict["mother"][0].code,
            "genealogy_cycle",
        )

        for animal in (a, b, c):
            animal.refresh_from_db()

        self.assertEqual(a.mother_id, b.id)
        self.assertEqual(b.mother_id, c.id)
        self.assertIsNone(c.mother_id)

        for animal in (a, b, c):
            animal.full_clean()

    def test_mixed_mother_father_cycle_is_rejected(self):
        # A and B act as mothers; C acts as a father.
        a = self.make_animal("MIXED_A", self.female)
        b = self.make_animal("MIXED_B", self.female)
        c = self.make_animal("MIXED_C", self.male)

        a.mother = b
        a.full_clean()
        a.save()
        b.father = c
        b.full_clean()
        b.save()
        c.mother = a
        with self.assertRaises(ValidationError) as clean_error:
            c.full_clean()
        self.assertEqual(
            clean_error.exception.error_dict["mother"][0].code,
            "genealogy_cycle",
        )
        with self.assertRaises(ValidationError) as save_error:
            c.save()
        self.assertEqual(
            save_error.exception.error_dict["mother"][0].code,
            "genealogy_cycle",
        )

        for animal in (a, b, c):
            animal.refresh_from_db()

        self.assertEqual(a.mother_id, b.id)
        self.assertEqual(b.father_id, c.id)
        self.assertIsNone(c.mother_id)

        for animal in (a, b, c):
            animal.full_clean()
