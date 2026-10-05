from datetime import date, timedelta, datetime, timezone as datetime_timezone
from decimal import Decimal
from uuid import UUID
from unittest.mock import patch
from types import SimpleNamespace
import sqlite3

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.db import connection, IntegrityError, transaction

from apps.animals.models import Animal
from apps.animals.api.schemas import AnimalCreateSchema, AnimalUpdateSchema
from apps.animals.services import AnimalService
from apps.catalogs.models import AnimalStatus, Breed, Gender, Species
from apps.catalogs.models import FarmType
from apps.common.context.context import RequestContext
from apps.common.exceptions import RelatedObjectNotFound, BusinessException
from apps.breeding.models import BreedingEvent
from apps.catalogs.models import BreedingType, WeighingMethod, ProductionType
from apps.weights.models import Weight
from apps.production.models import ProductionRecord
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization


class AnimalBirthWeightRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="BIRTH_WEIGHT", name="Birth weight")
        cls.species = Species.objects.create(code="BIRTH_WEIGHT", name="Birth weight species")
        cls.breed = Breed.objects.create(species=cls.species, code="BIRTH_WEIGHT", name="Birth weight breed")
        cls.gender = Gender.objects.create(code="BW_G", name="Birth weight fixture gender")
        cls.status = AnimalStatus.objects.create(code="BIRTH_WEIGHT", name="Birth weight status")
        farm_type = FarmType.objects.create(code="BIRTH_WEIGHT", name="Birth weight farm type")
        cls.farm = Farm.objects.create(organization=cls.organization, farm_type=farm_type, code="BIRTH_WEIGHT", name="Birth weight farm")
        cls.lot = Lot.objects.create(organization=cls.organization, farm=cls.farm, code="BIRTH_WEIGHT", name="Birth weight lot")

    def model(self, **changes):
        fields = dict(organization=self.organization, species=self.species,
                      breed=self.breed, gender=self.gender, status=self.status,
                      internal_id="BIRTH_WEIGHT", birth_weight=Decimal("32.50"))
        fields.update(changes)
        return Animal(**fields)

    def payload(self, schema, **changes):
        fields = dict(farm_id=self.farm.pk, lot_id=self.lot.pk,
                      species_id=self.species.pk, breed_id=self.breed.pk,
                      gender_id=self.gender.pk, status_id=self.status.pk,
                      internal_id="BIRTH_WEIGHT", official_tag="", electronic_tag="",
                      name="Original", notes="Original", birth_weight=Decimal("32.50"))
        fields.update(changes)
        return schema(**fields)

    def assert_birth_weight_error(self, operation, domain=False):
        with self.assertRaises(BusinessException if domain else ValidationError) as error:
            operation()
        validation = error.exception.__cause__ if domain else error.exception
        self.assertIsInstance(validation, ValidationError)
        self.assertEqual(validation.message_dict["birth_weight"],
                         ["El peso al nacimiento debe ser mayor que cero."])

    def test_model_full_clean_and_save_reject_nonpositive_birth_weight(self):
        for value in (Decimal("0.00"), Decimal("-0.01")):
            with self.subTest(value=value):
                animal = self.model(birth_weight=value)
                self.assert_birth_weight_error(animal.full_clean)
                self.assert_birth_weight_error(animal.save)
                self.assertFalse(Animal._base_manager.filter(pk=animal.pk).exists())

    def test_model_update_rejection_preserves_persisted_fields(self):
        animal = self.model()
        animal.save()
        before = Animal._base_manager.filter(pk=animal.pk).values().get()
        for value in (Decimal("0.00"), Decimal("-0.01")):
            with self.subTest(value=value):
                animal.birth_weight = value
                animal.name = "Changed"
                self.assert_birth_weight_error(animal.save)
                self.assertEqual(Animal._base_manager.filter(pk=animal.pk).values().get(), before)

    def test_model_accepts_none_and_positive_birth_weight(self):
        for index, value in enumerate((None, Decimal("0.01"), Decimal("32.50"))):
            with self.subTest(value=value):
                animal = self.model(internal_id=f"VALID_{index}", birth_weight=value)
                animal.full_clean()
                animal.save()
                animal.refresh_from_db()
                self.assertEqual(animal.birth_weight, value)

    def test_service_create_rejects_nonpositive_birth_weight(self):
        context = RequestContext(organization=self.organization)
        for value in (Decimal("0.00"), Decimal("-0.01")):
            with self.subTest(value=value):
                count = Animal._base_manager.count()
                self.assert_birth_weight_error(lambda: AnimalService.create(
                    context, self.payload(AnimalCreateSchema, birth_weight=value,
                                          internal_id=f"INVALID_{value}")), domain=True)
                self.assertEqual(Animal._base_manager.count(), count)

    def test_service_update_rejection_preserves_all_persisted_fields(self):
        context = RequestContext(organization=self.organization)
        animal = AnimalService.create(context, self.payload(AnimalCreateSchema))
        before = Animal._base_manager.filter(pk=animal.pk).values().get()
        for value in (Decimal("0.00"), Decimal("-0.01")):
            with self.subTest(value=value):
                self.assert_birth_weight_error(lambda: AnimalService.update(
                    animal, context, self.payload(AnimalUpdateSchema, birth_weight=value,
                                                 internal_id="CHANGED", name="Changed", notes="Changed")), domain=True)
                self.assertEqual(Animal._base_manager.filter(pk=animal.pk).values().get(), before)

    def test_service_create_and_update_accept_none_and_positive_birth_weight(self):
        context = RequestContext(organization=self.organization)
        for index, value in enumerate((None, Decimal("0.01"), Decimal("32.50"))):
            with self.subTest(value=value):
                animal = AnimalService.create(context, self.payload(
                    AnimalCreateSchema, internal_id=f"VALID_{index}", birth_weight=value))
                animal.refresh_from_db()
                self.assertEqual(animal.birth_weight, value)
                for updated_value in (Decimal("0.01"), None):
                    AnimalService.update(animal, context, self.payload(
                        AnimalUpdateSchema, internal_id=animal.internal_id, birth_weight=updated_value))
                    animal.refresh_from_db()
                    self.assertEqual(animal.birth_weight, updated_value)


class AnimalParentCoherenceCharacterizationTests(TestCase):
    """Characterize parental gender and species independently of business policy."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization = Organization.objects.create(
            code="PARENT_COHERENCE", name="Parent coherence organization",
        )
        cls.bovine = Species.objects.create(code="TEST_BOVINE", name="Test bovine")
        cls.porcine = Species.objects.create(code="TEST_PORCINE", name="Test porcine")
        cls.bovine_breed = Breed.objects.create(
            species=cls.bovine, code="TEST_BOVINE", name="Test bovine breed",
        )
        cls.porcine_breed = Breed.objects.create(
            species=cls.porcine, code="TEST_PORCINE", name="Test porcine breed",
        )
        cls.female = Gender.objects.get(code="F")
        cls.male = Gender.objects.get(code="M")
        cls.status = AnimalStatus.objects.create(
            code="PARENT_COHERENCE", name="Parent coherence status",
        )

    def make_animal(self, internal_id, species, breed, gender):
        return Animal.objects.create(
            organization=self.organization, species=species, breed=breed,
            gender=gender, status=self.status, internal_id=internal_id,
            is_active=True,
        )

    def assert_parent_link(self, child, field, parent):
        self.assertEqual(getattr(child, f"{field}_id"), parent.pk)
        persisted_parent = getattr(child, field)
        self.assertEqual(persisted_parent.pk, parent.pk)
        self.assertEqual(child.organization_id, self.organization.pk)
        self.assertEqual(persisted_parent.organization_id, self.organization.pk)
        self.assertIsNone(persisted_parent.mother_id)
        self.assertIsNone(persisted_parent.father_id)
        other_field = "father" if field == "mother" else "mother"
        self.assertIsNone(getattr(child, f"{other_field}_id"))
        self.assertEqual(child.breed.species_id, child.species_id)
        self.assertEqual(persisted_parent.breed.species_id, persisted_parent.species_id)
        return persisted_parent

    def test_model_rejects_parent_with_incorrect_gender_for_role(self):
        for field, gender, expected_code in (
            ("mother", self.male, "invalid_mother_gender"),
            ("father", self.female, "invalid_father_gender"),
        ):
            with self.subTest(parent=field):
                parent = self.make_animal(
                    f"GENDER_PARENT_{field}",
                    self.bovine,
                    self.bovine_breed,
                    gender,
                )
                child = self.make_animal(
                    f"GENDER_CHILD_{field}",
                    self.bovine,
                    self.bovine_breed,
                    self.female,
                )

                setattr(child, field, parent)

                with self.assertRaises(ValidationError) as clean_error:
                    child.full_clean()

                self.assertEqual(
                    clean_error.exception.error_dict[field][0].code,
                    expected_code,
                )

                with self.assertRaises(ValidationError) as save_error:
                    child.save()

                self.assertEqual(
                    save_error.exception.error_dict[field][0].code,
                    expected_code,
                )

                child.refresh_from_db()

                self.assertIsNone(child.mother_id)
                self.assertIsNone(child.father_id)

    def test_model_persists_parent_from_different_species(self):
        for field, gender, expected_code in (
            ("mother", self.female, "F"), ("father", self.male, "M"),
        ):
            with self.subTest(parent=field):
                parent = self.make_animal(
                    f"SPECIES_PARENT_{field}", self.porcine, self.porcine_breed, gender,
                )
                child = self.make_animal(
                    f"SPECIES_CHILD_{field}", self.bovine, self.bovine_breed, self.female,
                )
                setattr(child, field, parent)
                child.full_clean()
                child.save()
                child.refresh_from_db()
                persisted_parent = self.assert_parent_link(child, field, parent)
                self.assertEqual(child.species_id, self.bovine.pk)
                self.assertEqual(persisted_parent.species_id, self.porcine.pk)
                self.assertEqual(persisted_parent.gender.code, expected_code)


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
        cls.female = Gender.objects.get(code="F")
        cls.male = Gender.objects.get(code="M")
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
        cls.female = Gender.objects.get(code="F")
        cls.male = Gender.objects.get(code="M")
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


class AnimalAPIContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="CONTRACT", name="Contract")
        cls.other_organization = Organization.objects.create(code="OTHER", name="Other")
        cls.user = User.objects.create_user(email="animal-contract@example.com")
        Membership.objects.create(
            user=cls.user, organization=cls.organization,
            role=Membership.Role.OWNER, is_default=True,
        )
        cls.species = Species.objects.create(code="CONTRACT", name="Contract species")
        cls.breed = Breed.objects.create(
            species=cls.species, code="CONTRACT", name="Contract breed",
        )
        cls.female = Gender.objects.get(code="F")
        cls.male = Gender.objects.get(code="M")
        cls.status = AnimalStatus.objects.create(code="CONTRACT", name="Contract status")
        farm_type = FarmType.objects.create(code="CONTRACT", name="Contract type")
        cls.farm = Farm.objects.create(
            organization=cls.organization, farm_type=farm_type,
            code="CONTRACT", name="Contract farm",
        )
        cls.lot = Lot.objects.create(
            organization=cls.organization, farm=cls.farm,
            code="CONTRACT", name="Contract lot",
        )
        fields = dict(
            organization=cls.organization, species=cls.species, breed=cls.breed,
            status=cls.status, gender=cls.female,
        )
        cls.mother = Animal.objects.create(**fields, internal_id="MOTHER")
        cls.father = Animal.objects.create(
            **dict(fields, gender=cls.male), internal_id="FATHER",
        )
        cls.animal = Animal.objects.create(
            **fields, internal_id="CHILD", farm=cls.farm, lot=cls.lot,
            official_tag="TAG", electronic_tag="RFID", name="Calf",
            birth_date=date(2024, 1, 2), birth_weight=Decimal("32.75"),
            mother=cls.mother, father=cls.father, notes="Birth notes",
        )
        cls.other_animal = Animal.objects.create(
            **dict(fields, organization=cls.other_organization), internal_id="OTHER",
        )

    def setUp(self):
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {create_access_token(self.user)}"}

    def request(self, method, path, data=None):
        return getattr(self.client, method)(
            path, data=data, content_type="application/json", **self.headers,
        )

    def payload(self, **changes):
        data = {
            "farm_id": str(self.farm.pk), "lot_id": str(self.lot.pk),
            "species_id": str(self.species.pk), "breed_id": str(self.breed.pk),
            "gender_id": str(self.female.pk), "status_id": str(self.status.pk),
            "internal_id": "NEW", "official_tag": "NEW-TAG",
            "electronic_tag": "NEW-RFID", "name": "New calf",
            "birth_date": "2024-02-03", "birth_weight": "41.25",
            "mother_id": str(self.mother.pk), "father_id": str(self.father.pk),
            "notes": "New notes",
        }
        data.update(changes)
        return data

    def assert_contract(self, data, animal):
        expected = {
            "id", "internal_id", "official_tag", "electronic_tag", "name",
            "species_id", "species", "breed_id", "breed", "gender_id", "gender",
            "status_id", "status", "farm_id", "farm", "lot_id", "lot",
            "birth_date", "birth_weight", "mother_id", "father_id", "notes", "is_active",
        }
        if "mother_reference" in data:
            expected.update({"mother_reference", "father_reference"})
        self.assertEqual(set(data), expected)
        self.assertEqual(UUID(data["id"]), animal.pk)
        for field in ("internal_id", "official_tag", "electronic_tag", "name", "notes", "is_active"):
            self.assertEqual(data[field], getattr(animal, field))
        for field in ("species", "breed", "gender", "status", "farm", "lot", "mother", "father"):
            relation_id = getattr(animal, f"{field}_id")
            actual = data[f"{field}_id"]
            self.assertEqual(UUID(actual) if actual is not None else None, relation_id)
            if field not in ("mother", "father"):
                relation = getattr(animal, field)
                self.assertEqual(data[field], relation.name if relation else None)
        self.assertEqual(data["birth_date"], animal.birth_date.isoformat() if animal.birth_date else None)
        weight = data["birth_weight"]
        self.assertEqual(Decimal(str(weight)) if weight is not None else None, animal.birth_weight)

    def test_detail_returns_complete_contract(self):
        response = self.request("get", f"/api/animals/{self.animal.pk}")
        self.assertEqual(response.status_code, 200)
        self.assert_contract(response.json(), self.animal)

    def test_detail_and_list_support_nullable_fields(self):
        self.mother.internal_id = None
        self.mother.save()
        response = self.request("get", f"/api/animals/{self.mother.pk}")
        self.assertEqual(response.status_code, 200)
        self.assert_contract(response.json(), self.mother)
        response = self.request("get", "/api/animals/")
        self.assertEqual(response.status_code, 200)
        data = next(item for item in response.json() if item["id"] == str(self.mother.pk))
        self.assert_contract(data, self.mother)

    def test_list_returns_complete_contract_and_isolates_tenant(self):
        response = self.request("get", "/api/animals/")
        self.assertEqual(response.status_code, 200)
        animals = {str(animal.pk): animal for animal in (self.animal, self.mother, self.father)}
        self.assertEqual({item["id"] for item in response.json()}, set(animals))
        for item in response.json():
            self.assert_contract(item, animals[item["id"]])

    def test_post_returns_complete_persisted_contract(self):
        payload = self.payload()
        response = self.request("post", "/api/animals/", payload)
        self.assertEqual(response.status_code, 200)
        animal = Animal.objects.get(pk=response.json()["id"])
        self.assertEqual(animal.organization_id, self.organization.pk)
        self.assert_contract(response.json(), animal)
        for field, value in payload.items():
            self.assertEqual(response.json()[field], value)

    def test_put_returns_updated_complete_contract(self):
        payload = self.payload(gender_id=str(self.male.pk), mother_id=None, father_id=None)
        response = self.request("put", f"/api/animals/{self.animal.pk}", payload)
        self.assertEqual(response.status_code, 200)
        self.animal.refresh_from_db()
        self.assert_contract(response.json(), self.animal)
        for field, value in payload.items():
            self.assertEqual(response.json()[field], value)
        detail = self.request("get", f"/api/animals/{self.animal.pk}")
        self.assertEqual({key: value for key, value in detail.json().items()
            if key not in {"mother_reference", "father_reference"}}, response.json())

    def test_post_and_put_return_optional_nulls_and_empty_strings(self):
        payload = self.payload(
            birth_date=None, birth_weight=None, mother_id=None, father_id=None,
            official_tag="", electronic_tag="", name="", notes="",
        )
        for method, path in (("post", "/api/animals/"), ("put", f"/api/animals/{self.animal.pk}")):
            with self.subTest(method=method):
                payload["internal_id"] = f"EMPTY-{method}"
                response = self.request(method, path, payload)
                self.assertEqual(response.status_code, 200)
                self.assert_contract(response.json(), Animal.objects.get(pk=response.json()["id"]))
                for field, value in payload.items():
                    self.assertEqual(response.json()[field], value)

    def test_other_tenant_detail_and_update_remain_inaccessible(self):
        path = f"/api/animals/{self.other_animal.pk}"
        self.assertEqual(self.request("get", path).status_code, 404)
        self.assertEqual(self.request("put", path, self.payload()).status_code, 404)
        self.other_animal.refresh_from_db()
        self.assertEqual(self.other_animal.internal_id, "OTHER")
        self.assertEqual(self.other_animal.organization_id, self.other_organization.pk)

    def test_delete_malformed_uuid_returns_422_before_lookup_or_service(self):
        from apps.animals.selectors import AnimalSelector

        before = list(Animal._base_manager.order_by("pk").values())
        self.client.raise_request_exception = False
        with patch.object(AnimalSelector, "get_by_id", wraps=AnimalSelector.get_by_id) as lookup, patch.object(
            AnimalService, "delete", wraps=AnimalService.delete,
        ) as delete:
            response = self.request("delete", "/api/animals/not-a-uuid")
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before)
        self.assertFalse(connection.needs_rollback)
        delete.assert_not_called()
        self.assertEqual(response.status_code, 422, str(response.exc_info))
        lookup.assert_not_called()

    def test_delete_preserves_missing_foreign_inactive_and_soft_delete_contract(self):
        before = list(Animal._base_manager.order_by("pk").values())
        for identifier in (UUID(int=0), self.other_animal.pk):
            with self.subTest(identifier=identifier):
                self.assertEqual(self.request("delete", f"/api/animals/{identifier}").status_code, 404)
                self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before)

        Animal._base_manager.filter(pk=self.father.pk).update(is_active=False)
        before = list(Animal._base_manager.order_by("pk").values())
        self.assertEqual(self.request("delete", f"/api/animals/{self.father.pk}").status_code, 404)
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before)

        original = Animal._base_manager.values().get(pk=self.animal.pk)
        response = self.request("delete", f"/api/animals/{self.animal.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        self.animal.refresh_from_db()
        self.assertFalse(self.animal.is_active)
        self.assertIsNotNone(self.animal.deleted_at)
        persisted = Animal._base_manager.values().get(pk=self.animal.pk)
        for field in original.keys() - {"is_active", "deleted_at", "updated_at"}:
            self.assertEqual(persisted[field], original[field])
        self.assertEqual(list(Animal._base_manager.exclude(pk=self.animal.pk).order_by("pk").values()),
                         [row for row in before if row["id"] != self.animal.pk])

        before = list(Animal._base_manager.order_by("pk").values())
        self.assertEqual(self.request("delete", f"/api/animals/{self.animal.pk}").status_code, 404)
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before)
        self.assertFalse(connection.needs_rollback)


class AnimalDependentInvariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="H2", name="H2 organization")
        cls.species = Species.objects.create(code="H2", name="H2 species")
        cls.breed = Breed.objects.create(species=cls.species, code="H2", name="H2 breed")
        cls.female = Gender.objects.get(code="F")
        cls.male = Gender.objects.get(code="M")
        cls.status = AnimalStatus.objects.get(code="ACTIVE")
        farm_type = FarmType.objects.first()
        cls.farm = Farm.objects.create(organization=cls.organization, farm_type=farm_type, code="H2", name="H2 farm")
        cls.lot = Lot.objects.create(organization=cls.organization, farm=cls.farm, code="H2", name="H2 lot")
        cls.initial = timezone.localdate() - timedelta(days=120)
        cls.event_date = cls.initial + timedelta(days=30)
        cls.invalid_date = cls.event_date + timedelta(days=1)
        fields = dict(organization=cls.organization, species=cls.species, breed=cls.breed,
                      status=cls.status, farm=cls.farm, lot=cls.lot, birth_date=cls.initial)
        cls.mother = Animal.objects.create(**fields, gender=cls.female, internal_id="H2-MOTHER")
        cls.father = Animal.objects.create(**fields, gender=cls.male, internal_id="H2-FATHER")
        cls.method = WeighingMethod.objects.create(code="H2", name="H2 method")
        cls.production_type = ProductionType.objects.create(code="H2", name="H2 production", default_unit="L")
        cls.breeding_type = BreedingType.objects.create(code="H2", name="H2 breeding")
        cls.user = User.objects.create_user(email="h2@example.com")
        Membership.objects.create(user=cls.user, organization=cls.organization,
                                  role=Membership.Role.OWNER, is_default=True)

    def setUp(self):
        self.context = RequestContext(organization=self.organization)

    def payload(self, animal, **changes):
        data = dict(farm_id=str(self.farm.pk), lot_id=str(self.lot.pk),
                    species_id=str(self.species.pk), breed_id=str(self.breed.pk),
                    gender_id=str(animal.gender_id), status_id=str(self.status.pk),
                    internal_id=animal.internal_id, official_tag="", electronic_tag="",
                    name="", notes="", mother_id=None, father_id=None,
                    birth_date=animal.birth_date.isoformat() if animal.birth_date else None,
                    birth_weight=None)
        data.update(changes)
        return data

    def put(self, animal, **changes):
        return self.client.put(f"/api/animals/{animal.pk}", data=self.payload(animal, **changes),
                               content_type="application/json",
                               HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def child(self, deleted=False):
        child = Animal.objects.create(organization=self.organization, species=self.species,
                                      breed=self.breed, gender=self.female, status=self.status,
                                      internal_id="H2-CHILD", mother=self.mother, father=self.father)
        if deleted:
            child.delete()
        return child

    def breeding(self, deleted=False):
        event = BreedingEvent.objects.create(organization=self.organization, animal=self.mother,
                                             male=self.father, breeding_type=self.breeding_type,
                                             date=self.event_date)
        if deleted:
            event.delete()
        return event

    def weight(self, deleted=False):
        record = Weight.objects.create(organization=self.organization, animal=self.mother,
                                      weighing_method=self.method, date=self.event_date,
                                      weight=Decimal("50.00"), notes="")
        if deleted:
            record.delete()
        return record

    def production(self, deleted=False, recorded_at=None):
        record = ProductionRecord.objects.create(
            organization=self.organization, animal=self.mother, production_type=self.production_type,
            recorded_at=recorded_at or timezone.make_aware(datetime.combine(self.event_date, datetime.min.time())),
            quantity=Decimal("2.000"), unit="L", notes="")
        if deleted:
            record.delete()
        return record

    def assert_gender_rejected(self, animal, gender):
        before = list(Animal._base_manager.order_by("pk").values())
        response = self.put(animal, gender_id=str(gender.pk))
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before)

    def assert_date_rejected(self):
        before = list(Animal._base_manager.order_by("pk").values())
        self.assertEqual(self.put(self.mother, birth_date=self.invalid_date.isoformat()).status_code, 400)
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before)

    def test_mother_active_child_protects_gender(self):
        self.child()
        self.assert_gender_rejected(self.mother, self.male)

    def test_father_active_child_protects_gender(self):
        self.child()
        self.assert_gender_rejected(self.father, self.female)

    def test_deleted_child_protects_both_parent_roles(self):
        self.child(deleted=True)
        for animal, gender in ((self.mother, self.male), (self.father, self.female)):
            with self.subTest(role=animal.internal_id):
                self.assert_gender_rejected(animal, gender)

    def test_breeding_female_protects_gender_without_children(self):
        self.breeding()
        self.assert_gender_rejected(self.mother, self.male)

    def test_breeding_male_protects_gender_without_children(self):
        self.breeding()
        self.assert_gender_rejected(self.father, self.female)

    def test_deleted_breeding_protects_both_roles(self):
        self.breeding(deleted=True)
        for animal, gender in ((self.mother, self.male), (self.father, self.female)):
            with self.subTest(role=animal.internal_id):
                self.assert_gender_rejected(animal, gender)

    def test_weight_protects_birth_date(self):
        self.weight()
        self.assert_date_rejected()

    def test_deleted_weight_protects_birth_date(self):
        self.weight(deleted=True)
        self.assert_date_rejected()

    def test_production_protects_birth_date(self):
        self.production()
        self.assert_date_rejected()

    def test_deleted_production_protects_birth_date(self):
        self.production(deleted=True)
        self.assert_date_rejected()

    def test_weight_equal_birth_date_is_allowed(self):
        self.weight()
        self.assertEqual(self.put(self.mother, birth_date=self.event_date.isoformat()).status_code, 200)
        self.mother.refresh_from_db()
        self.assertEqual(self.mother.birth_date, self.event_date)

    def test_production_equal_local_birth_date_is_allowed(self):
        # UTC day is the following day; active timezone must define the boundary.
        tz = datetime_timezone(timedelta(hours=-6))
        with timezone.override(tz):
            timestamp = datetime.combine(self.event_date, datetime.min.time()).replace(hour=23, tzinfo=tz)
            self.production(recorded_at=timestamp)
            self.assertEqual(self.put(self.mother, birth_date=self.event_date.isoformat()).status_code, 200)
            self.assertEqual(self.put(self.mother, birth_date=self.invalid_date.isoformat()).status_code, 400)

    def test_earlier_compatible_birth_date_is_allowed(self):
        self.weight()
        self.production()
        earlier = self.initial - timedelta(days=1)
        self.assertEqual(self.put(self.mother, birth_date=earlier.isoformat()).status_code, 200)

    def test_unreferenced_gender_is_editable(self):
        self.assertEqual(self.put(self.mother, gender_id=str(self.male.pk)).status_code, 200)

    def test_none_to_incompatible_birth_date_is_rejected(self):
        self.mother.birth_date = None
        self.mother.save()
        self.weight()
        self.assert_date_rejected()

    def test_none_to_compatible_birth_date_is_allowed(self):
        self.mother.birth_date = None
        self.mother.save()
        self.weight()
        self.production()
        self.assertEqual(self.put(self.mother, birth_date=self.event_date.isoformat()).status_code, 200)

    def test_birth_date_none_remains_allowed_with_history(self):
        self.weight()
        self.production()
        self.assertEqual(self.put(self.mother, birth_date=None).status_code, 200)

    def test_direct_save_rejects_incompatible_gender(self):
        self.child(deleted=True)
        self.mother.gender = self.male
        with self.assertRaises(ValidationError):
            self.mother.save()
        self.mother.refresh_from_db()
        self.assertEqual(self.mother.gender_id, self.female.pk)

    def test_direct_save_rejects_incompatible_birth_date(self):
        self.weight(deleted=True)
        self.mother.birth_date = self.invalid_date
        with self.assertRaises(ValidationError):
            self.mother.save()
        self.mother.refresh_from_db()
        self.assertEqual(self.mother.birth_date, self.initial)

    def test_service_rejects_foreign_instance(self):
        foreign = Organization.objects.create(code="H2-FOREIGN", name="H2 foreign")
        foreign_animal = Animal.objects.create(
            organization=foreign, species=self.species, breed=self.breed,
            gender=self.female, status=self.status, internal_id="H2-FOREIGN-ANIMAL",
        )
        before = list(Animal._base_manager.order_by("pk").values())
        with self.assertRaises(BusinessException):
            AnimalService.update(foreign_animal, self.context,
                                 AnimalUpdateSchema(**self.payload(foreign_animal)))
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before)

    def test_unchanged_fields_skip_inverse_history_queries(self):
        self.weight()
        self.production()
        self.breeding()
        self.mother.name = "Compatible name correction"
        with CaptureQueriesContext(connection) as queries:
            self.mother.save()
        sql = " ".join(query["sql"] for query in queries.captured_queries)
        for table in ("weights", "production_records", "breeding_events"):
            self.assertNotIn(f'FROM "{table}"', sql)
        self.mother.refresh_from_db()
        self.assertEqual(self.mother.name, "Compatible name correction")


class AnimalErrorTranslationHTTPTests(TestCase):
    setUpTestData = classmethod(AnimalAPIContractTests.setUpTestData.__func__)
    setUp = AnimalAPIContractTests.setUp
    payload = AnimalAPIContractTests.payload

    def request(self, method, path, data=None):
        # Keep pre-fix raw database failures from poisoning TestCase's outer
        # transaction; the request and actual database write remain real.
        with transaction.atomic():
            return AnimalAPIContractTests.request(self, method, path, data)

    def assert_bad_input(self, method, data, animal=None):
        before = list(Animal._base_manager.order_by("id").values())
        path = "/api/animals/" if method == "post" else f"/api/animals/{(animal or self.animal).pk}"
        response = self.request(method, path, data)
        self.assertEqual(response.status_code, 400)
        self.assertIsInstance(response.json()["detail"], str)
        self.assertTrue(response.json()["detail"])
        self.assertEqual(list(Animal._base_manager.order_by("id").values()), before)

    def test_post_future_birth_returns_400(self):
        self.assert_bad_input("post", self.payload(birth_date=(timezone.now().date() + timedelta(days=1)).isoformat()))

    def test_post_nonpositive_birth_weight_returns_400(self):
        for weight in ("0", "-0.01"):
            with self.subTest(weight=weight):
                self.assert_bad_input("post", self.payload(birth_weight=weight))

    def test_post_incompatible_parent_gender_returns_400(self):
        for changes in ({"mother_id": str(self.father.pk)}, {"father_id": str(self.mother.pk)}):
            with self.subTest(changes=changes):
                self.assert_bad_input("post", self.payload(**changes))

    def test_post_duplicate_internal_id_full_clean_returns_400(self):
        self.assert_bad_input("post", self.payload(internal_id=self.animal.internal_id))

    def test_post_omitted_optional_texts_are_empty(self):
        data = self.payload()
        for field in ("official_tag", "electronic_tag", "name", "notes"):
            data.pop(field)
        response = self.request("post", "/api/animals/", data)
        self.assertEqual(response.status_code, 200)
        animal = Animal._base_manager.get(pk=response.json()["id"])
        for field in ("official_tag", "electronic_tag", "name", "notes"):
            self.assertEqual(getattr(animal, field), "")
        animal.full_clean()

    def test_put_omitted_or_null_optional_texts_replace_with_empty(self):
        for explicit_null in (False, True):
            with self.subTest(explicit_null=explicit_null):
                data = self.payload(internal_id=self.animal.internal_id)
                for field in ("official_tag", "electronic_tag", "name", "notes"):
                    if explicit_null:
                        data[field] = None
                    else:
                        data.pop(field)
                response = self.request("put", f"/api/animals/{self.animal.pk}", data)
                self.assertEqual(response.status_code, 200)
                self.animal.refresh_from_db()
                for field in ("official_tag", "electronic_tag", "name", "notes"):
                    self.assertEqual(getattr(self.animal, field), "")
                self.animal.full_clean()

    def test_post_explicit_null_notes_are_empty(self):
        response = self.request("post", "/api/animals/", self.payload(notes=None))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Animal._base_manager.get(pk=response.json()["id"]).notes, "")

    def test_put_expected_non_h2_validation_returns_400(self):
        for changes in (
            {"birth_date": (timezone.now().date() + timedelta(days=1)).isoformat()},
            {"birth_weight": "0"}, {"birth_weight": "10000.00"},
            {"birth_weight": "1.001"}, {"birth_weight": "10000"},
            {"name": "x" * 151}, {"internal_id": self.father.internal_id},
            {"mother_id": str(self.father.pk)}, {"father_id": str(self.mother.pk)},
        ):
            with self.subTest(changes=changes):
                self.assert_bad_input("put", self.payload(**changes))

    def test_put_self_reference_and_genealogy_cycle_return_400(self):
        self.assert_bad_input("put", self.payload(mother_id=str(self.animal.pk)))
        # CHILD already references MOTHER. Making CHILD the mother's mother
        # closes a cycle through persisted records without corrupting fixtures.
        self.assert_bad_input(
            "put", self.payload(mother_id=str(self.animal.pk), father_id=None), self.mother,
        )

    def test_unrelated_validation_errors_propagate(self):
        for errors in (
            {"notes": ValidationError("Unexpected validator", code="unexpected")},
            {"organization": ValidationError("Wrong field", code="max_length")},
            {"birth_date": ValidationError("Other uncoded error")},
            {
                "gender": ValidationError("Known H2 error", code="dependent_gender"),
                "notes": ValidationError("Unexpected validator", code="unexpected"),
            },
        ):
            for method in ("post", "put"):
                with self.subTest(errors=errors, method=method):
                    error = ValidationError(errors)
                    before = list(Animal._base_manager.order_by("id").values())
                    with patch.object(Animal, "full_clean", side_effect=error):
                        with self.assertRaises(ValidationError) as caught:
                            self.request(method, "/api/animals/" if method == "post" else f"/api/animals/{self.animal.pk}", self.payload())
                    self.assertIs(caught.exception, error)
                    self.assertEqual(list(Animal._base_manager.order_by("id").values()), before)

    def test_unrelated_integrity_error_propagates(self):
        for method in ("post", "put"):
            with self.subTest(method=method):
                error = IntegrityError("Unrelated database failure")
                before = list(Animal._base_manager.order_by("id").values())
                with patch.object(Animal, "save", side_effect=error):
                    with self.assertRaises(IntegrityError) as caught:
                        self.request(method, "/api/animals/" if method == "post" else f"/api/animals/{self.animal.pk}", self.payload())
                self.assertIs(caught.exception, error)
                self.assertEqual(list(Animal._base_manager.order_by("id").values()), before)

    def test_real_internal_id_db_collision_returns_400_and_rolls_back(self):
        for method in ("post", "put"):
            with self.subTest(method=method):
                # Bypass both validation calls, but preserve the real database
                # write to characterize the full_clean/save race boundary.
                with patch.object(Animal, "full_clean"):
                    self.assert_bad_input(method, self.payload(internal_id=self.father.internal_id))

    def test_real_internal_id_db_collision_preserves_cause_and_connection(self):
        context = RequestContext(organization=self.organization)
        for schema, operation in (
            (AnimalCreateSchema, lambda data: AnimalService.create(context, data)),
            (AnimalUpdateSchema, lambda data: AnimalService.update(self.animal, context, data)),
        ):
            with self.subTest(schema=schema):
                before = list(Animal._base_manager.order_by("id").values())
                with patch.object(Animal, "full_clean"):
                    with self.assertRaises(BusinessException) as caught:
                        operation(schema(**self.payload(internal_id=self.father.internal_id)))
                self.assertIsInstance(caught.exception.__cause__, IntegrityError)
                if connection.vendor == "sqlite":
                    self.assertEqual(str(caught.exception.__cause__.__cause__),
                                     "UNIQUE constraint failed: animals.organization_id, animals.internal_id")
                self.assertEqual(list(Animal._base_manager.order_by("id").values()), before)

    def test_internal_id_classifier_requires_exact_backend_diagnostic(self):
        for name, expected in (
            ("unique_internal_id_per_organization", True),
            ("other_constraint", False),
        ):
            with self.subTest(postgresql_constraint=name):
                cause = Exception("PostgreSQL diagnostic")
                cause.diag = SimpleNamespace(constraint_name=name)
                error = IntegrityError("Database error")
                error.__cause__ = cause
                self.assertEqual(AnimalService._is_internal_id_collision(error), expected)
        for message, expected in (
            ("UNIQUE constraint failed: animals.organization_id, animals.internal_id", True),
            ("UNIQUE constraint failed: animals.id", False),
            ("NOT NULL constraint failed: animals.notes", False),
        ):
            with self.subTest(sqlite_message=message):
                error = IntegrityError(message)
                error.__cause__ = sqlite3.IntegrityError(message)
                self.assertEqual(AnimalService._is_internal_id_collision(error), expected)
        self.assertFalse(AnimalService._is_internal_id_collision(
            IntegrityError("UNIQUE constraint failed: animals.organization_id, animals.internal_id"),
        ))

    def test_unrelated_real_integrity_error_preserves_connection(self):
        original_assign = AnimalService._assign_fields

        def corrupt_assignment(animal, data, relations):
            original_assign(animal, data, relations)
            animal.notes = None

        context = RequestContext(organization=self.organization)
        for schema, operation in (
            (AnimalCreateSchema, lambda data: AnimalService.create(context, data)),
            (AnimalUpdateSchema, lambda data: AnimalService.update(self.animal, context, data)),
        ):
            with self.subTest(schema=schema):
                before = list(Animal._base_manager.order_by("id").values())
                with patch.object(AnimalService, "_assign_fields", side_effect=corrupt_assignment), patch.object(Animal, "full_clean"):
                    with self.assertRaises(IntegrityError) as caught:
                        operation(schema(**self.payload()))
                if connection.vendor == "sqlite":
                    self.assertEqual(str(caught.exception), "NOT NULL constraint failed: animals.notes")
                self.assertEqual(list(Animal._base_manager.order_by("id").values()), before)


class AnimalDetailGenealogyContractTests(TestCase):
    setUpTestData = classmethod(AnimalAPIContractTests.setUpTestData.__func__)
    setUp = AnimalAPIContractTests.setUp
    request = AnimalAPIContractTests.request
    payload = AnimalAPIContractTests.payload

    def detail(self):
        response = self.request("get", f"/api/animals/{self.animal.pk}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_active_parent_identification(self):
        for role in ("mother", "father"):
            parent = getattr(self, role)
            parent.name = f"Named {role}"
            parent.save(update_fields=["name"])
            self.assertEqual(self.detail()[f"{role}_reference"], {
                "id": str(parent.pk), "internal_id": parent.internal_id,
                "name": parent.name, "is_active": True, "is_deleted": False})

    def test_business_inactive_parents_remain_visible(self):
        for role in ("mother", "father"):
            Animal._base_manager.filter(pk=getattr(self, role).pk).update(is_active=False)
        data = self.detail()
        for role in ("mother", "father"):
            self.assertFalse(data[f"{role}_reference"]["is_active"])
            self.assertFalse(data[f"{role}_reference"]["is_deleted"])

    def test_deleted_historical_parents_visible_but_not_candidates(self):
        self.mother.delete()
        self.father.delete()
        data = self.detail()
        for role in ("mother", "father"):
            self.assertEqual(data[f"{role}_reference"]["id"], str(getattr(self, role).pk))
            self.assertTrue(data[f"{role}_reference"]["is_deleted"])
        response = self.request("get", "/api/animals/parents/candidates")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()}
        self.assertNotIn(str(self.mother.pk), ids)
        self.assertNotIn(str(self.father.pk), ids)

    def test_null_parents_have_null_references(self):
        Animal._base_manager.filter(pk=self.animal.pk).update(mother=None, father=None)
        data = self.detail()
        for field in ("mother_id", "father_id", "mother_reference", "father_reference"):
            self.assertIsNone(data[field])

    def test_corrupt_foreign_parent_does_not_expose_identification(self):
        Animal._base_manager.filter(pk=self.animal.pk).update(mother=self.other_animal)
        self.assertIsNone(self.detail()["mother_reference"])
        response = self.request("get", f"/api/animals/{self.other_animal.pk}")
        self.assertEqual(response.status_code, 404)

    def test_detail_selector_and_parent_serialization_use_one_query(self):
        from apps.animals.selectors import AnimalSelector
        from apps.animals.api.endpoints import get_animal
        context = RequestContext(organization=self.organization)
        with self.assertNumQueries(1):
            response = get_animal(SimpleNamespace(context=context), self.animal.pk)
            self.assertEqual(response.mother_reference.id, self.mother.pk)
            self.assertEqual(response.father_reference.id, self.father.pk)

    def test_list_and_write_responses_do_not_gain_detail_fields(self):
        responses = [self.request("get", "/api/animals/"),
            self.request("post", "/api/animals/", self.payload()),
            self.request("put", f"/api/animals/{self.animal.pk}", self.payload(internal_id="CHILD"))]
        for response in responses:
            self.assertEqual(response.status_code, 200)
            items = response.json() if isinstance(response.json(), list) else [response.json()]
            for item in items:
                self.assertNotIn("mother_reference", item)
                self.assertNotIn("father_reference", item)


class AnimalUpdateLocationContractTests(TestCase):
    setUpTestData = classmethod(AnimalAPIContractTests.setUpTestData.__func__)
    setUp = AnimalAPIContractTests.setUp
    request = AnimalAPIContractTests.request
    payload = AnimalAPIContractTests.payload

    def put(self, **changes):
        return self.request("put", f"/api/animals/{self.animal.pk}", self.payload(**changes))

    def snapshot(self):
        return list(Animal._base_manager.order_by("id").values())

    def test_create_null_farm_is_422_without_persistence(self):
        before = self.snapshot()
        self.assertEqual(self.request("post", "/api/animals/", self.payload(farm_id=None)).status_code, 422)
        self.assertEqual(self.snapshot(), before)

    def test_create_null_lot_is_422_without_persistence(self):
        before = self.snapshot()
        self.assertEqual(self.request("post", "/api/animals/", self.payload(lot_id=None)).status_code, 422)
        self.assertEqual(self.snapshot(), before)

    def test_create_omitted_location_fields_remain_422(self):
        for field in ("farm_id", "lot_id"):
            with self.subTest(field=field):
                data = self.payload()
                del data[field]
                before = self.snapshot()
                self.assertEqual(self.request("post", "/api/animals/", data).status_code, 422)
                self.assertEqual(self.snapshot(), before)

    def test_put_null_pair_on_unlocated_animal_updates_metadata_and_preserves_parents(self):
        Animal._base_manager.filter(pk=self.animal.pk).update(farm=None, lot=None)
        response = self.put(farm_id=None, lot_id=None, name="Edited without location", notes="New notes")
        self.assertEqual(response.status_code, 200)
        self.animal.refresh_from_db()
        self.assertIsNone(self.animal.farm_id)
        self.assertIsNone(self.animal.lot_id)
        self.assertEqual(self.animal.name, "Edited without location")
        self.assertEqual(self.animal.notes, "New notes")
        self.assertEqual(self.animal.mother_id, self.mother.pk)
        self.assertEqual(self.animal.father_id, self.father.pk)
        for field in ("farm_id", "farm", "lot_id", "lot"):
            self.assertIsNone(response.json()[field])

    def test_put_uuid_pair_assigns_valid_location(self):
        Animal._base_manager.filter(pk=self.animal.pk).update(farm=None, lot=None)
        self.assertEqual(self.put().status_code, 200)
        self.animal.refresh_from_db()
        self.assertEqual(self.animal.farm_id, self.farm.pk)
        self.assertEqual(self.animal.lot_id, self.lot.pk)

    def test_put_null_pair_removes_existing_location(self):
        self.assertEqual(self.put(farm_id=None, lot_id=None).status_code, 200)
        self.animal.refresh_from_db()
        self.assertIsNone(self.animal.farm_id)
        self.assertIsNone(self.animal.lot_id)

    def test_put_partial_pairs_are_400_and_atomic(self):
        for changes in ({"farm_id": None}, {"lot_id": None}):
            with self.subTest(changes=changes):
                before = self.snapshot()
                response = self.put(**changes, name="Must not persist", notes="Must not persist",
                    gender_id=str(self.male.pk), birth_date="2020-01-01", mother_id=None, father_id=None)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {
                    "detail": "Debe indicar finca y lote juntos o dejar ambos sin ubicación."})
                self.assertEqual(self.snapshot(), before)

    def test_put_omitted_location_fields_are_422_and_atomic(self):
        for field in ("farm_id", "lot_id"):
            with self.subTest(field=field):
                data = self.payload(name="Must not persist")
                del data[field]
                before = self.snapshot()
                response = self.request("put", f"/api/animals/{self.animal.pk}", data)
                self.assertEqual(response.status_code, 422)
                self.assertTrue(any(error["loc"][-1] == field for error in response.json()["detail"]))
                self.assertEqual(self.snapshot(), before)

    def test_put_foreign_or_incoherent_location_pairs_are_rejected_atomically(self):
        other_farm = Farm.objects.create(organization=self.other_organization,
            farm_type=self.farm.farm_type, code="FOREIGN", name="Foreign")
        other_lot = Lot.objects.create(organization=self.other_organization,
            farm=other_farm, code="FOREIGN", name="Foreign")
        local_farm = Farm.objects.create(organization=self.organization,
            farm_type=self.farm.farm_type, code="LOCAL", name="Local")
        local_lot = Lot.objects.create(organization=self.organization,
            farm=local_farm, code="LOCAL", name="Local")
        for farm, lot in ((other_farm, other_lot), (self.farm, other_lot),
                          (other_farm, self.lot), (self.farm, local_lot)):
            with self.subTest(farm=farm.pk, lot=lot.pk):
                before = self.snapshot()
                self.assertEqual(self.put(farm_id=str(farm.pk), lot_id=str(lot.pk),
                    name="Must not persist", notes="Must not persist").status_code, 400)
                self.assertEqual(self.snapshot(), before)

    def test_put_inactive_location_is_rejected_atomically(self):
        for relation in (self.farm, self.lot):
            with self.subTest(relation=type(relation).__name__):
                relation.is_active = False
                relation.save(update_fields=["is_active"])
                before = self.snapshot()
                self.assertEqual(self.put(name="Must not persist").status_code, 400)
                self.assertEqual(self.snapshot(), before)
                relation.is_active = True
                relation.save(update_fields=["is_active"])

    def test_put_null_location_preserves_unchanged_deleted_parents(self):
        self.mother.delete()
        self.father.delete()
        self.assertEqual(self.put(farm_id=None, lot_id=None).status_code, 200)
        self.animal.refresh_from_db()
        self.assertEqual(self.animal.mother_id, self.mother.pk)
        self.assertEqual(self.animal.father_id, self.father.pk)

    def test_put_null_location_does_not_allow_new_deleted_parent(self):
        self.mother.delete()
        Animal._base_manager.filter(pk=self.animal.pk).update(mother=None)
        before = self.snapshot()
        self.assertEqual(self.put(farm_id=None, lot_id=None, name="Must not persist").status_code, 400)
        self.assertEqual(self.snapshot(), before)


class AnimalDeletedParentWriteTests(TestCase):
    setUpTestData = classmethod(AnimalAPIContractTests.setUpTestData.__func__)
    setUp = AnimalAPIContractTests.setUp
    request = AnimalAPIContractTests.request
    payload = AnimalAPIContractTests.payload

    def put(self, data):
        return self.request("put", f"/api/animals/{self.animal.pk}", data)

    def parent(self, role, **changes):
        fields = dict(organization=self.organization, species=self.species,
            breed=self.breed, gender=self.female if role == "mother" else self.male,
            status=self.status, internal_id=f"{role}-{Animal._base_manager.count()}")
        fields.update(changes)
        return Animal._base_manager.create(**fields)

    def assert_rejected(self, response, before):
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Uno de los registros relacionados no existe."})
        self.assertEqual(list(Animal._base_manager.order_by("id").values()), before)

    def test_create_active_and_inactive_parents(self):
        for role in ("mother", "father"):
            for active in (True, False):
                with self.subTest(role=role, active=active):
                    parent = self.parent(role, is_active=active)
                    response = self.request("post", "/api/animals/", self.payload(
                        **{f"{role}_id": str(parent.pk),
                           "internal_id": f"child-{role}-{active}"}))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()[f"{role}_id"], str(parent.pk))

    def test_create_deleted_parents_rejected_regardless_of_activity(self):
        for role in ("mother", "father"):
            for active in (True, False):
                with self.subTest(role=role, active=active):
                    parent = self.parent(role, is_active=active, deleted_at=timezone.now())
                    before = list(Animal._base_manager.order_by("id").values())
                    self.assert_rejected(self.request("post", "/api/animals/",
                        self.payload(**{f"{role}_id": str(parent.pk)})), before)

    def test_update_new_active_and_inactive_parents_from_null_and_existing(self):
        for role in ("mother", "father"):
            for from_null in (True, False):
                for active in (True, False):
                    with self.subTest(role=role, from_null=from_null, active=active):
                        original = getattr(self, role)
                        Animal._base_manager.filter(pk=self.animal.pk).update(
                            **{f"{role}_id": None if from_null else original.pk})
                        parent = self.parent(role, is_active=active)
                        response = self.put(self.payload(**{f"{role}_id": str(parent.pk)}))
                        self.assertEqual(response.status_code, 200)
                        self.animal.refresh_from_db()
                        self.assertEqual(getattr(self.animal, f"{role}_id"), parent.pk)

    def test_update_new_deleted_parents_from_null_and_existing_rejected(self):
        for role in ("mother", "father"):
            for from_null in (True, False):
                with self.subTest(role=role, from_null=from_null):
                    Animal._base_manager.filter(pk=self.animal.pk).update(
                        **{f"{role}_id": None if from_null else getattr(self, role).pk})
                    parent = self.parent(role, deleted_at=timezone.now())
                    before = list(Animal._base_manager.order_by("id").values())
                    self.assert_rejected(self.put(self.payload(
                        **{f"{role}_id": str(parent.pk)})), before)

    def test_unchanged_deleted_mother_and_father_preserved(self):
        self.mother.delete()
        self.father.delete()
        response = self.put(self.payload(internal_id=self.animal.internal_id,
            name="Edited name", notes="Edited notes"))
        self.assertEqual(response.status_code, 200)
        self.animal.refresh_from_db()
        self.assertEqual(self.animal.mother_id, self.mother.pk)
        self.assertEqual(self.animal.father_id, self.father.pk)
        self.assertEqual(self.animal.name, "Edited name")
        self.assertEqual(self.animal.notes, "Edited notes")

    def test_explicit_null_removes_deleted_historical_parents(self):
        for role in ("mother", "father"):
            with self.subTest(role=role):
                getattr(self, role).delete()
                self.animal.refresh_from_db()
                data = self.payload(mother_id=str(self.animal.mother_id) if self.animal.mother_id else None,
                    father_id=str(self.animal.father_id) if self.animal.father_id else None)
                data[f"{role}_id"] = None
                response = self.put(data)
                self.assertEqual(response.status_code, 200)
                self.animal.refresh_from_db()
                self.assertIsNone(getattr(self.animal, f"{role}_id"))

    def test_deleted_historical_parent_replaced_with_valid_parent(self):
        for role in ("mother", "father"):
            with self.subTest(role=role):
                getattr(self, role).delete()
                parent = self.parent(role)
                self.animal.refresh_from_db()
                data = self.payload(mother_id=str(self.animal.mother_id),
                    father_id=str(self.animal.father_id))
                data[f"{role}_id"] = str(parent.pk)
                response = self.put(data)
                self.assertEqual(response.status_code, 200)
                self.animal.refresh_from_db()
                self.assertEqual(getattr(self.animal, f"{role}_id"), parent.pk)

    def test_deleted_historical_parent_cannot_be_replaced_with_deleted_parent(self):
        for role in ("mother", "father"):
            with self.subTest(role=role):
                getattr(self, role).delete()
                parent = self.parent(role, deleted_at=timezone.now())
                before = list(Animal._base_manager.order_by("id").values())
                self.assert_rejected(self.put(self.payload(
                    **{f"{role}_id": str(parent.pk)})), before)

    def test_omitted_parent_fields_keep_existing_full_put_removal_semantics(self):
        self.mother.delete()
        self.father.delete()
        data = self.payload()
        del data["mother_id"]
        del data["father_id"]
        self.assertEqual(self.put(data).status_code, 200)
        self.animal.refresh_from_db()
        self.assertIsNone(self.animal.mother_id)
        self.assertIsNone(self.animal.father_id)

    def test_invalid_mother_or_father_assignment_persists_no_other_changes(self):
        farm = Farm.objects.create(organization=self.organization,
            farm_type=self.farm.farm_type, code="SECOND", name="Second")
        lot = Lot.objects.create(organization=self.organization,
            farm=farm, code="SECOND", name="Second")
        for role in ("mother", "father"):
            with self.subTest(role=role):
                parent = self.parent(role, deleted_at=timezone.now())
                before = list(Animal._base_manager.order_by("id").values())
                self.assert_rejected(self.put(self.payload(
                    **{f"{role}_id": str(parent.pk)}, gender_id=str(self.male.pk),
                    farm_id=str(farm.pk), lot_id=str(lot.pk), name="Changed",
                    birth_date="2020-01-01", notes="Changed")), before)

    def test_cross_species_parent_allowed_on_create_and_update(self):
        species = Species.objects.create(code="WRITE_OTHER", name="Other")
        breed = Breed.objects.create(species=species, code="WRITE_OTHER", name="Other")
        for role in ("mother", "father"):
            for method in ("post", "put"):
                with self.subTest(role=role, method=method):
                    parent = self.parent(role, species=species, breed=breed)
                    data = self.payload(**{f"{role}_id": str(parent.pk),
                        "internal_id": f"cross-{role}-{method}"})
                    response = self.request(method,
                        "/api/animals/" if method == "post" else f"/api/animals/{self.animal.pk}", data)
                    self.assertEqual(response.status_code, 200)

    def test_unchanged_deleted_parent_still_requires_valid_gender_and_tenant(self):
        for changes in ({"gender_id": self.male.pk},
                        {"organization_id": self.other_organization.pk}):
            with self.subTest(changes=changes):
                Animal._base_manager.filter(pk=self.mother.pk).update(
                    deleted_at=timezone.now(), **changes)
                before = list(Animal._base_manager.order_by("id").values())
                self.assertEqual(self.put(self.payload()).status_code, 400)
                self.assertEqual(list(Animal._base_manager.order_by("id").values()), before)
                Animal._base_manager.filter(pk=self.mother.pk).update(
                    gender=self.female, organization=self.organization)


class AnimalParentCandidateContractTests(TestCase):
    setUpTestData = classmethod(AnimalAPIContractTests.setUpTestData.__func__)
    path = "/api/animals/parents/candidates"

    def request_candidates(self, **query):
        return self.client.get(self.path, query,
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def ids(self):
        response = self.request_candidates()
        self.assertEqual(response.status_code, 200)
        return {item["id"] for item in response.json()}

    def test_authentication_required(self):
        self.assertEqual(self.client.get(self.path).status_code, 401)

    def test_tenant_isolation(self):
        self.assertNotIn(str(self.other_animal.pk), self.ids())

    def test_active_non_deleted_included(self):
        self.assertIn(str(self.mother.pk), self.ids())

    def test_inactive_non_deleted_included(self):
        Animal._base_manager.filter(pk=self.mother.pk).update(is_active=False)
        data = self.request_candidates().json()
        item = next(item for item in data if item["id"] == str(self.mother.pk))
        self.assertFalse(item["is_active"])

    def test_deleted_excluded_regardless_of_active_flag(self):
        for active in (False, True):
            with self.subTest(active=active):
                Animal._base_manager.filter(pk=self.mother.pk).update(
                    is_active=active, deleted_at=timezone.now())
                self.assertNotIn(str(self.mother.pk), self.ids())

    def test_cross_species_included(self):
        species = Species.objects.create(code="PARENT_OTHER", name="Other species")
        breed = Breed.objects.create(species=species, code="PARENT_OTHER", name="Other breed")
        parent = Animal.objects.create(organization=self.organization,
            species=species, breed=breed, gender=self.female, status=self.status,
            internal_id="OTHER-SPECIES")
        self.assertIn(str(parent.pk), self.ids())

    def test_both_gender_codes_returned(self):
        self.assertEqual({item["gender_code"] for item in self.request_candidates().json()}, {"F", "M"})

    def test_minimal_response_and_static_route(self):
        response = self.request_candidates()
        self.assertEqual(response.status_code, 200)  # Must not match UUID detail validation.
        for item in response.json():
            self.assertEqual(set(item), {"id", "internal_id", "name", "gender_code", "is_active"})
        mother = next(item for item in response.json() if item["id"] == str(self.mother.pk))
        self.assertEqual(mother["internal_id"], self.mother.internal_id)
        self.assertEqual(mother["name"], self.mother.name)

    def test_order_is_deterministic(self):
        first = self.request_candidates().json()
        self.assertEqual(first, self.request_candidates().json())
        keys = [(item["internal_id"], item["id"]) for item in first]
        self.assertEqual(keys, sorted(keys))

    def test_normal_inventory_excludes_inactive_and_deleted(self):
        Animal._base_manager.filter(pk=self.mother.pk).update(is_active=False)
        self.father.delete()
        response = self.client.get("/api/animals/",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.json()}, {str(self.animal.pk)})
        self.assertIn(str(self.mother.pk), self.ids())
        self.assertNotIn(str(self.father.pk), self.ids())

    def test_organization_query_cannot_switch_tenant(self):
        response = self.request_candidates(organization_id=str(self.other_organization.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(self.other_animal.pk), {item["id"] for item in response.json()})
        self.assertEqual(response.json(), self.request_candidates().json())

    def test_viewer_read_policy_preserved(self):
        Membership._base_manager.filter(user=self.user).update(role=Membership.Role.VIEWER)
        self.assertEqual(self.request_candidates().status_code, 200)

    def test_selector_has_no_n_plus_one(self):
        from apps.animals.selectors import AnimalSelector
        context = RequestContext(organization=self.organization)
        with self.assertNumQueries(1):
            candidates = list(AnimalSelector.parent_candidates(context))
            self.assertTrue(candidates)
            for candidate in candidates:
                self.assertIn(candidate.gender.code, ("F", "M"))

    def test_candidates_use_real_mounted_route_even_with_detail_first(self):
        from django.conf import settings
        from django.urls import URLResolver, get_resolver, resolve
        self.assertEqual(settings.ROOT_URLCONF, "config.urls")
        match = resolve(self.path)
        self.assertEqual(match.url_name, "parent_candidates")
        self.assertEqual(match.kwargs, {})
        api_mount = next(pattern for pattern in get_resolver().url_patterns
            if isinstance(pattern, URLResolver) and str(pattern.pattern) == "api/")
        # Reorder the actual mounted URLPattern objects, without constructing
        # a separate Ninja API or using Ninja's isolated TestClient.
        mounted = list(api_mount.url_patterns)
        details = [pattern for pattern in mounted if pattern.name == "get_animal"]
        self.assertTrue(details)
        reordered = details + [pattern for pattern in mounted if pattern not in details]
        with patch.object(api_mount, "url_patterns", reordered):
            self.assertEqual(resolve(self.path).url_name, "parent_candidates")
            self.assertEqual(self.request_candidates().status_code, 200)

    def test_valid_uuid_detail_uses_real_mounted_route(self):
        from django.urls import resolve
        path = f"/api/animals/{self.animal.pk}"
        self.assertEqual(resolve(path).url_name, "get_animal")
        response = self.client.get(path,
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.animal.pk))

    def test_invalid_uuid_detail_preserves_422_validation(self):
        from django.urls import resolve
        path = "/api/animals/not-a-uuid"
        self.assertEqual(resolve(path).url_name, "get_animal")
        response = self.client.get(path,
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")
        self.assertEqual(response.status_code, 422)
        error = response.json()["detail"][0]
        self.assertEqual(error["type"], "uuid_parsing")
        self.assertEqual(error["loc"], ["path", "animal_id"])
