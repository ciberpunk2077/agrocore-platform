from datetime import date
from decimal import Decimal
from uuid import UUID

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token

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
        cls.female = Gender.objects.create(code="F", name="Test female parent")
        cls.male = Gender.objects.create(code="M", name="Test male parent")
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
        cls.female = Gender.objects.create(code="F", name="Contract female")
        cls.male = Gender.objects.create(code="M", name="Contract male")
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
        self.assertEqual(detail.json(), response.json())

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
