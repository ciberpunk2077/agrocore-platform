from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.animals.models import Animal
from apps.catalogs.models import AnimalStatus, Breed, Gender, Species
from apps.organizations.models import Organization


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
