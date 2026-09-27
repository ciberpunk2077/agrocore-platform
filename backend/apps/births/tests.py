from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.animals.models import Animal
from apps.births.api.schemas import BirthCreateSchema
from apps.births.models import Birth
from apps.births.services import BirthService
from apps.breeding.models import BreedingEvent
from apps.catalogs.models import AnimalStatus, Breed, BreedingType, Gender, Species
from apps.common.context.context import RequestContext
from apps.common.exceptions import BusinessException
from apps.organizations.models import Organization
from apps.pregnancy.models import Pregnancy, PregnancyStatus


class BirthAutomaticCalfRegressionTests(TestCase):
    """P3: automatic creation and atomic failures through the real birth flow."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization = Organization.objects.create(code="P3", name="P3 organization")
        species = Species.objects.create(code="P3", name="P3 species")
        breed = Breed.objects.create(species=species, code="P3", name="P3 breed")
        cls.female = Gender.objects.create(code="F", name="P3 female")
        male = Gender.objects.create(code="M", name="P3 male")
        status = AnimalStatus.objects.create(code="ACTIVE", name="P3 active")
        animal_fields = {
            "organization": cls.organization,
            "species": species,
            "breed": breed,
            "status": status,
            "is_active": True,
        }
        cls.mother = Animal.objects.create(
            **animal_fields, gender=cls.female, internal_id="P3_MOTHER",
        )
        cls.father = Animal.objects.create(
            **animal_fields, gender=male, internal_id="P3_FATHER",
        )
        breeding_type = BreedingType.objects.create(code="P3", name="P3 breeding")
        cls.breeding = BreedingEvent(
            organization=cls.organization,
            animal=cls.mother,
            male=cls.father,
            breeding_type=breeding_type,
            date=date(2025, 1, 1),
            expected_birth=date(2025, 10, 1),
        )
        cls.breeding.full_clean()
        cls.breeding.save()
        cls.pregnancy = Pregnancy(
            organization=cls.organization,
            breeding=cls.breeding,
            animal=cls.mother,
            diagnosis_date=date(2025, 2, 1),
            expected_birth=date(2025, 10, 1),
            confirmed=True,
            status=PregnancyStatus.ACTIVE,
        )
        cls.pregnancy.full_clean()
        cls.pregnancy.save()

    def make_payload(self, calf_gender_id):
        return BirthCreateSchema(
            pregnancy_id=self.pregnancy.pk,
            mother_id=self.mother.pk,
            calf_id=None,
            calf_gender_id=calf_gender_id,
            birth_date=date(2025, 10, 1),
            birth_weight=Decimal("30.00"),
        )

    def snapshot(self):
        return {
            model: list(model._base_manager.order_by("pk").values())
            for model in (Birth, Pregnancy, Animal, BreedingEvent)
        }

    def assert_state_unchanged(self, before):
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(Birth._base_manager.count(), 0)
        self.assertEqual(Animal._base_manager.count(), 2)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.ACTIVE)
        self.assertEqual(self.pregnancy.animal_id, self.mother.pk)
        self.assertEqual(self.pregnancy.breeding_id, self.breeding.pk)
        self.assertFalse(Birth._base_manager.filter(pregnancy=self.pregnancy).exists())

    def test_valid_gender_creates_birth_and_calf(self):
        before_ids = set(Animal._base_manager.values_list("pk", flat=True))
        birth = BirthService.create(
            RequestContext(organization=self.organization),
            self.make_payload(self.female.pk),
        )
        birth.refresh_from_db()
        calf = Animal._base_manager.get(pk=birth.calf_id)
        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertEqual(
            set(Animal._base_manager.values_list("pk", flat=True)),
            before_ids | {calf.pk},
        )
        self.assertNotIn(calf.pk, before_ids)
        self.assertEqual(calf.gender_id, self.female.pk)
        self.assertEqual(calf.organization_id, self.organization.pk)
        self.assertEqual(calf.mother_id, self.mother.pk)
        self.assertEqual(calf.father_id, self.father.pk)
        self.assertEqual(birth.calf_id, calf.pk)
        self.assertEqual(birth.calf_gender_id, self.female.pk)
        self.assertEqual(birth.pregnancy_id, self.pregnancy.pk)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)

    def test_omitted_gender_rejects_before_birth_insert(self):
        before = self.snapshot()
        with CaptureQueriesContext(connection) as queries:
            with self.assertRaises(BusinessException) as raised:
                BirthService.create(
                    RequestContext(organization=self.organization),
                    self.make_payload(None),
                )
        self.assertIs(type(raised.exception), BusinessException)
        self.assertEqual(
            str(raised.exception),
            "Debe indicar el sexo de la cría para crearla automáticamente.",
        )
        self.assertFalse(any(
            query["sql"].lstrip().upper().startswith("INSERT") for query in queries
        ))
        self.assert_state_unchanged(before)

    def test_animal_validation_failure_rolls_back_inserted_birth(self):
        # A catalog reassignment leaves the inherited breed/species inconsistent.
        # This triggers Animal.clean() without mocks or time-dependent data.
        other_species = Species.objects.create(code="P3_OTHER", name="P3 other species")
        breed = self.mother.breed
        breed.species = other_species
        breed.save()
        before = self.snapshot()
        with CaptureQueriesContext(connection) as queries:
            with self.assertRaises(BusinessException) as raised:
                BirthService.create(
                    RequestContext(organization=self.organization),
                    self.make_payload(self.female.pk),
                )
        self.assertIs(type(raised.exception), BusinessException)
        self.assertEqual(
            str(raised.exception),
            "No se pudo crear la cría: los datos del animal son inválidos.",
        )
        self.assertIsInstance(raised.exception.__cause__, ValidationError)
        self.assertEqual(set(raised.exception.__cause__.error_dict), {"breed"})
        # Observe the real INSERT before the service's atomic block rolls it back.
        birth_table = connection.ops.quote_name(Birth._meta.db_table)
        self.assertTrue(any(
            query["sql"].startswith(f"INSERT INTO {birth_table}") for query in queries
        ))
        self.assertTrue(any(
            "ROLLBACK TO SAVEPOINT" in query["sql"].upper() for query in queries
        ))
        self.assert_state_unchanged(before)

    def test_existing_calf_accepts_omitted_gender(self):
        calf = Animal.objects.create(
            organization=self.organization,
            species=self.mother.species,
            breed=self.mother.breed,
            gender=self.female,
            status=self.mother.status,
            internal_id="P3_EXISTING_CALF",
            mother=self.mother,
            father=self.father,
        )
        before_ids = set(Animal._base_manager.values_list("pk", flat=True))
        payload = self.make_payload(None)
        payload.calf_id = calf.pk
        birth = BirthService.create(RequestContext(organization=self.organization), payload)
        birth.refresh_from_db()
        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertEqual(birth.calf_id, calf.pk)
        self.assertIsNone(birth.calf_gender_id)
        self.assertEqual(
            set(Animal._base_manager.values_list("pk", flat=True)), before_ids,
        )
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)



    def test_rejects_birth_for_finished_pregnancy(self):
        self.pregnancy.status = PregnancyStatus.FINISHED
        self.pregnancy.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            BirthService.create(
                RequestContext(organization=self.organization),
                self.make_payload(self.female.pk),
            )

        self.assertEqual(Birth.objects.count(), 0)

        self.pregnancy.refresh_from_db()
        self.assertEqual(
            self.pregnancy.status,
            PregnancyStatus.FINISHED,
        )

    def test_rejects_birth_for_aborted_pregnancy(self):
        self.pregnancy.status = PregnancyStatus.ABORTED
        self.pregnancy.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            BirthService.create(
                RequestContext(organization=self.organization),
                self.make_payload(self.female.pk),
            )

        self.assertEqual(Birth.objects.count(), 0)

        self.pregnancy.refresh_from_db()
        self.assertEqual(
            self.pregnancy.status,
            PregnancyStatus.ABORTED,
        )