from datetime import date, timedelta
from decimal import Decimal
import sqlite3
from unittest.mock import patch
from uuid import UUID, uuid4


from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from apps.animals.models import Animal
from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.births.api.schemas import BirthCreateSchema
from apps.births.models import Birth
from apps.births.services import BirthService
from apps.births.services.calf_service import CalfService
from apps.births.selectors import BirthSelector
from apps.breeding.models import BreedingEvent
from apps.catalogs.models import AnimalStatus, Breed, BreedingType, FarmType, Gender, Species
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.common.context.context import RequestContext
from apps.common.temporal import get_business_today
from apps.common.exceptions import (
    BirthValidationError,
    BusinessException,
)

from apps.organizations.models import Organization
from apps.pregnancy.models import Pregnancy, PregnancyStatus
from apps.pregnancy.services import PregnancyService
from apps.common.exceptions.pregnancy import PregnancyValidationError


class BirthAutomaticCalfRegressionTests(TestCase):
    """P3: automatic creation and atomic failures through the real birth flow."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization = Organization.objects.create(code="P3", name="P3 organization")
        species = Species.objects.create(code="P3", name="P3 species")
        breed = Breed.objects.create(species=species, code="P3", name="P3 breed")
        cls.female = Gender.objects.get(code="F")
        male = Gender.objects.get(code="M")
        status = AnimalStatus.objects.get(code="ACTIVE")
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

    def test_birth_wins_and_stale_abort_cannot_overwrite_finished(self):
        context = RequestContext(organization=self.organization)
        stale = Pregnancy.objects.get(pk=self.pregnancy.pk)
        birth = BirthService.create(context, self.make_payload(self.female.pk))
        calf_id = birth.calf_id
        # Replay the abort's old read after the winning birth has committed.
        # Only the read is controlled; the conditional UPDATE is real.
        with patch.object(Pregnancy.objects, "get", return_value=stale):
            with self.assertRaises(PregnancyValidationError):
                PregnancyService.abort(context, stale.pk)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)
        self.assertTrue(Birth.objects.filter(pk=birth.pk, calf_id=calf_id).exists())
        self.assertTrue(Animal.objects.filter(pk=calf_id).exists())

    def test_abort_wins_and_stale_birth_rolls_back_birth_and_calf(self):
        context = RequestContext(organization=self.organization)
        stale = Pregnancy.objects.get(pk=self.pregnancy.pk)
        PregnancyService.abort(context, self.pregnancy.pk)
        before_animals = list(Animal._base_manager.order_by("pk").values())
        real_finish = BirthService._finish_pregnancy

        def finish_after_inserts(pregnancy):
            pending = Birth.objects.get(pregnancy_id=pregnancy.pk)
            self.assertIsNotNone(pending.calf_id)
            self.assertTrue(Animal.objects.filter(pk=pending.calf_id).exists())
            return real_finish(pregnancy)

        # The winner is stored before the loser's transaction, so its state
        # survives rollback. Replay the already-read ACTIVE instance.
        with patch.object(Pregnancy.objects, "get", return_value=stale), patch.object(
            BirthService, "_finish_pregnancy", side_effect=finish_after_inserts,
        ):
            with self.assertRaises(BirthValidationError):
                BirthService.create(context, self.make_payload(self.female.pk))
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.ABORTED)
        self.assertFalse(Birth._base_manager.filter(pregnancy=self.pregnancy).exists())
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before_animals)

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

    def reserve_cria_id(self, internal_id, organization=None):
        return Animal.objects.create(
            organization=organization or self.organization,
            species=self.mother.species, breed=self.mother.breed,
            gender=self.female, status=self.mother.status,
            internal_id=internal_id,
        )

    def assert_auto_cria_id(self, expected):
        birth = BirthService.create(
            RequestContext(organization=self.organization),
            self.make_payload(self.female.pk),
        )
        birth.refresh_from_db()
        self.assertEqual(birth.calf.internal_id, expected)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)

    def test_cria_first_id_is_00001(self):
        self.assert_auto_cria_id("CRIA-00001")

    def test_cria_id_increments_reserved_numbers(self):
        self.reserve_cria_id("CRIA-00001")
        self.reserve_cria_id("CRIA-00002")
        self.assert_auto_cria_id("CRIA-00003")

    def test_cria_soft_deleted_animal_reserves_number(self):
        reserved = self.reserve_cria_id("CRIA-00001")
        reserved.delete()
        reserved.refresh_from_db()
        self.assertIs(reserved.is_active, False)
        self.assertIsNotNone(reserved.deleted_at)
        before = Animal._base_manager.filter(pk=reserved.pk).values().get()
        self.assert_auto_cria_id("CRIA-00002")
        self.assertEqual(Animal._base_manager.filter(pk=reserved.pk).values().get(), before)

    def test_cria_id_sequence_is_isolated_by_organization(self):
        foreign = Organization.objects.create(code="CRIA_FOREIGN", name="Cria foreign organization")
        reserved = self.reserve_cria_id("CRIA-00001", organization=foreign)
        self.assert_auto_cria_id("CRIA-00001")
        self.assertEqual(Animal._base_manager.filter(internal_id="CRIA-00001").count(), 2)
        self.assertEqual(reserved.organization_id, foreign.pk)

    def test_cria_id_does_not_fill_gaps(self):
        self.reserve_cria_id("CRIA-00001")
        self.reserve_cria_id("CRIA-00003")
        self.assert_auto_cria_id("CRIA-00004")

    def test_cria_id_ignores_malformed_suffixes_without_changes(self):
        for internal_id in ("CRIA-ABC", "CRIA-", "CRIA-12X", "CRIA-²", "CRIA-CRIA-9"):
            self.reserve_cria_id(internal_id)
        self.reserve_cria_id("CRIA-00002")
        before = list(Animal._base_manager.order_by("pk").values())
        self.assert_auto_cria_id("CRIA-00003")
        self.assertEqual(
            list(Animal._base_manager.filter(pk__in=[row["id"] for row in before]).order_by("pk").values()),
            before,
        )

    def test_cria_id_uses_numeric_maximum_above_99999(self):
        self.reserve_cria_id("CRIA-99999")
        self.reserve_cria_id("CRIA-100000")
        self.assert_auto_cria_id("CRIA-100001")

    def test_cria_real_db_id_collision_is_domain_error_and_rolls_back(self):
        reserved = self.reserve_cria_id("CRIA-00001")
        reserved.delete()
        before = self.snapshot()
        # Force a stale allocation; validation and INSERT remain real.
        with patch.object(CalfService, "_generate_internal_id", return_value="CRIA-00001"):
            with self.assertRaises(BirthValidationError) as raised:
                BirthService.create(RequestContext(organization=self.organization), self.make_payload(self.female.pk))
        self.assertIsInstance(raised.exception.__cause__, IntegrityError)
        self.assertIsNotNone(raised.exception.__cause__.__cause__)
        self.assertEqual(self.snapshot(), before)

    def test_cria_unrelated_integrity_error_propagates_and_rolls_back(self):
        before = self.snapshot()

        def invalid_save(instance, *args, **kwargs):
            instance.name = None
            kwargs.pop("_birth_business_today", None)
            # Bypass model validation only to reach a real NOT NULL DB error.
            return models.Model.save(instance, *args, **kwargs)

        with patch.object(Animal, "save", autospec=True, side_effect=invalid_save):
            with self.assertRaises(IntegrityError) as raised:
                BirthService.create(RequestContext(organization=self.organization), self.make_payload(self.female.pk))
        self.assertIn("NOT NULL", str(raised.exception))
        self.assertEqual(self.snapshot(), before)

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

    def test_alive_automatic_calf_starts_active(self):
        before_ids = set(Animal._base_manager.values_list("pk", flat=True))
        self.assertEqual(self.mother.status.code, "ACTIVE")
        payload = self.make_payload(self.female.pk)
        payload.alive = True

        birth = BirthService.create(RequestContext(organization=self.organization), payload)
        birth.refresh_from_db()
        calf = Animal._base_manager.get(pk=birth.calf_id)
        self.pregnancy.refresh_from_db()

        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertTrue(birth.alive)
        self.assertNotIn(calf.pk, before_ids)
        self.assertEqual(set(Animal._base_manager.values_list("pk", flat=True)), before_ids | {calf.pk})
        self.assertEqual(calf.status.code, "ACTIVE")
        self.assertIs(calf.is_active, True)
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)

    def test_alive_automatic_calf_does_not_inherit_sold_status(self):
        self.mother.status = AnimalStatus.objects.get(code="SOLD")
        self.mother.save(update_fields=["status"])
        self.assertIs(self.mother.is_active, True)
        before_ids = set(Animal._base_manager.values_list("pk", flat=True))
        payload = self.make_payload(self.female.pk)
        payload.alive = True

        birth = BirthService.create(RequestContext(organization=self.organization), payload)
        birth.refresh_from_db()
        calf = Animal._base_manager.get(pk=birth.calf_id)
        self.pregnancy.refresh_from_db()

        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertTrue(birth.alive)
        self.assertNotIn(calf.pk, before_ids)
        self.assertEqual(set(Animal._base_manager.values_list("pk", flat=True)), before_ids | {calf.pk})
        self.assertIs(calf.is_active, True)
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)
        self.assertEqual(calf.status.code, "ACTIVE")
        self.assertNotEqual(calf.status_id, self.mother.status_id)

    def test_not_alive_birth_does_not_create_automatic_calf(self):
        before_ids = set(Animal._base_manager.values_list("pk", flat=True))
        payload = self.make_payload(self.female.pk)
        payload.alive = False

        birth = BirthService.create(RequestContext(organization=self.organization), payload)
        birth.refresh_from_db()
        self.pregnancy.refresh_from_db()

        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertIs(birth.alive, False)
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)
        self.assertIsNone(birth.calf)
        self.assertEqual(Animal._base_manager.count(), len(before_ids))
        self.assertEqual(set(Animal._base_manager.values_list("pk", flat=True)), before_ids)

    def make_existing_contract_calf(self):
        status = AnimalStatus.objects.create(code="BIRTH_EXISTING", name="Birth existing calf fixture status")
        return Animal.objects.create(
            organization=self.organization,
            species=self.mother.species,
            breed=self.mother.breed,
            gender=self.female,
            status=status,
            internal_id="P3_CONTRACT_CALF",
            mother=self.mother,
            father=self.father,
            birth_date=date(2025, 10, 1),
            birth_weight=Decimal("29.00"),
            official_tag="CONTRACT-TAG",
            name="Existing contract calf",
            notes="Preserve existing calf data.",
        )

    def test_not_alive_birth_rejects_existing_calf_without_changes(self):
        calf = self.make_existing_contract_calf()
        before = self.snapshot()
        before_calf = Animal._base_manager.filter(pk=calf.pk).values().get()
        payload = self.make_payload(None)
        payload.calf_id = calf.pk
        payload.alive = False

        # The domain error category is fixed; its final wording is not.
        with self.assertRaises(BusinessException):
            BirthService.create(RequestContext(organization=self.organization), payload)

        self.assertEqual(Birth._base_manager.count(), 0)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.ACTIVE)
        self.assertEqual(Animal._base_manager.filter(pk=calf.pk).values().get(), before_calf)
        self.assertEqual(self.snapshot(), before)

    def test_alive_birth_preserves_existing_calf_status_and_data(self):
        calf = self.make_existing_contract_calf()
        self.assertNotEqual(calf.status.code, "ACTIVE")
        before_animals = list(Animal._base_manager.order_by("pk").values())
        before_calf = Animal._base_manager.filter(pk=calf.pk).values().get()
        payload = self.make_payload(None)
        payload.calf_id = calf.pk
        payload.alive = True

        birth = BirthService.create(RequestContext(organization=self.organization), payload)
        birth.refresh_from_db()
        calf.refresh_from_db()
        self.pregnancy.refresh_from_db()

        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertTrue(birth.alive)
        self.assertEqual(birth.calf_id, calf.pk)
        self.assertEqual(calf.status_id, before_calf["status_id"])
        self.assertIs(calf.is_active, before_calf["is_active"])
        self.assertEqual(Animal._base_manager.filter(pk=calf.pk).values().get(), before_calf)
        self.assertEqual(list(Animal._base_manager.order_by("pk").values()), before_animals)
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
            "Debe indicar el sexo de la crÃ­a para crearla automÃ¡ticamente.",
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
            "No se pudo crear la crÃ­a: los datos del animal son invÃ¡lidos.",
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

        with self.assertRaises(BirthValidationError):
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

        with self.assertRaises(BirthValidationError):
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


    def test_rejects_birth_before_breeding_date(self):
        payload = self.make_payload(self.female.pk)
        payload.birth_date = date(2024, 12, 31)

        with self.assertRaisesMessage(
            BirthValidationError,
            "La fecha del parto no puede ser anterior a la reproducciÃ³n.",
        ):
            BirthService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Birth.objects.count(), 0)

        self.pregnancy.refresh_from_db()
        self.assertEqual(
            self.pregnancy.status,
            PregnancyStatus.ACTIVE,
        )

    def test_rejects_birth_before_diagnosis_date(self):
        payload = self.make_payload(self.female.pk)
        payload.birth_date = date(2025, 1, 15)

        with self.assertRaisesMessage(
            BirthValidationError,
            "La fecha del parto no puede ser anterior al diagnÃ³stico de gestaciÃ³n.",
        ):
            BirthService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Birth.objects.count(), 0)

        self.pregnancy.refresh_from_db()
        self.assertEqual(
            self.pregnancy.status,
            PregnancyStatus.ACTIVE,
        )

    def test_rejects_future_birth_date(self):
        payload = self.make_payload(self.female.pk)
        payload.birth_date = timezone.localdate() + timedelta(days=1)

        with self.assertRaisesMessage(
            BirthValidationError,
            "La fecha del parto no puede estar en el futuro.",
        ):
            BirthService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Birth.objects.count(), 0)

        self.pregnancy.refresh_from_db()
        self.assertEqual(
            self.pregnancy.status,
            PregnancyStatus.ACTIVE,
        )

    def test_accepts_birth_on_diagnosis_date(self):
        payload = self.make_payload(self.female.pk)
        payload.birth_date = self.pregnancy.diagnosis_date

        birth = BirthService.create(
            RequestContext(organization=self.organization),
            payload,
        )

        self.assertEqual(birth.birth_date, self.pregnancy.diagnosis_date)
        self.assertEqual(Birth.objects.count(), 1)

        self.pregnancy.refresh_from_db()
        self.assertEqual(
            self.pregnancy.status,
            PregnancyStatus.FINISHED,
        )



# -------------------------------------------------------------------

class BirthHistorySelectorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.organization = Organization.objects.create(
            code="BH",
            name="Birth History Organization",
        )

        cls.other_organization = Organization.objects.create(
            code="BH2",
            name="Other Birth History Organization",
        )

        species = Species.objects.create(
            code="BH",
            name="Birth History Species",
        )

        breed = Breed.objects.create(
            species=species,
            code="BH",
            name="Birth History Breed",
        )

        cls.female = Gender.objects.create(
            code="BHF",
            name="Birth History Female",
        )

        cls.male = Gender.objects.create(
            code="BHM",
            name="Birth History Male",
        )

        status = AnimalStatus.objects.create(
            code="BH",
            name="Birth History Active",
        )

        cls.mother = Animal.objects.create(
            organization=cls.organization,
            species=species,
            breed=breed,
            gender=cls.female,
            status=status,
            internal_id="BH_MOTHER",
            is_active=True,
        )

        cls.other_mother = Animal.objects.create(
            organization=cls.organization,
            species=species,
            breed=breed,
            gender=cls.female,
            status=status,
            internal_id="BH_OTHER_MOTHER",
            is_active=True,
        )

        cls.other_tenant_mother = Animal.objects.create(
            organization=cls.other_organization,
            species=species,
            breed=breed,
            gender=cls.female,
            status=status,
            internal_id="BH_OTHER_TENANT",
            is_active=True,
        )

        cls.breeding_type = BreedingType.objects.create(
            code="BH",
            name="Birth History Breeding",
        )

    @classmethod
    def create_pregnancy(cls, mother, breeding_date, diagnosis_date):
        breeding = BreedingEvent.objects.create(
            organization=mother.organization,
            animal=mother,
            male=None,
            breeding_type=cls.breeding_type,
            date=breeding_date,
            expected_birth=diagnosis_date,
        )

        return Pregnancy.objects.create(
            organization=mother.organization,
            breeding=breeding,
            animal=mother,
            diagnosis_date=diagnosis_date,
            expected_birth=diagnosis_date,
            confirmed=True,
            status=PregnancyStatus.FINISHED,
        )

    @classmethod
    def create_birth(
        cls,
        mother,
        birth_date,
        is_active=True,
    ):
        pregnancy = cls.create_pregnancy(
            mother=mother,
            breeding_date=date(2025, 1, 1),
            diagnosis_date=date(2025, 2, 1),
        )

        return Birth.objects.create(
            organization=mother.organization,
            pregnancy=pregnancy,
            mother=mother,
            calf=None,
            calf_gender=None,
            birth_date=birth_date,
            birth_weight=Decimal("30.00"),
            alive=True,
            dystocia=False,
            notes=None,
            is_active=is_active,
        )

    def test_history_returns_only_requested_mother(self):
        requested_birth = self.create_birth(
            self.mother,
            date(2025, 10, 1),
        )

        self.create_birth(
            self.other_mother,
            date(2025, 10, 2),
        )

        history = list(
            BirthSelector.history(
                RequestContext(organization=self.organization),
                self.mother.pk,
            )
        )

        self.assertEqual(
            [birth.pk for birth in history],
            [requested_birth.pk],
        )

    def test_history_filters_by_organization(self):
        organization_birth = self.create_birth(
            self.mother,
            date(2025, 10, 1),
        )

        other_tenant_birth = self.create_birth(
            self.other_tenant_mother,
            date(2025, 10, 2),
        )

        history = list(
            BirthSelector.history(
                RequestContext(organization=self.organization),
                self.mother.pk,
            )
        )

        self.assertEqual(
            [birth.pk for birth in history],
            [organization_birth.pk],
        )
        self.assertNotIn(
            other_tenant_birth.pk,
            [birth.pk for birth in history],
        )

    def test_history_excludes_inactive_births(self):
        active_birth = self.create_birth(
            self.mother,
            date(2025, 10, 1),
            is_active=True,
        )

        inactive_birth = self.create_birth(
            self.mother,
            date(2025, 10, 2),
            is_active=False,
        )

        history = list(
            BirthSelector.history(
                RequestContext(organization=self.organization),
                self.mother.pk,
            )
        )

        self.assertEqual(
            [birth.pk for birth in history],
            [active_birth.pk],
        )
        self.assertNotIn(
            inactive_birth.pk,
            [birth.pk for birth in history],
        )

    def test_history_is_ordered_by_most_recent_birth(self):
        oldest = self.create_birth(
            self.mother,
            date(2025, 8, 1),
        )

        newest = self.create_birth(
            self.mother,
            date(2025, 10, 1),
        )

        middle = self.create_birth(
            self.mother,
            date(2025, 9, 1),
        )

        history = list(
            BirthSelector.history(
                RequestContext(organization=self.organization),
                self.mother.pk,
            )
        )

        self.assertEqual(
            [birth.pk for birth in history],
            [
                newest.pk,
                middle.pk,
                oldest.pk,
            ],
        )

    def test_history_returns_empty_list_when_no_births_exist(self):
        history = list(
            BirthSelector.history(
                RequestContext(organization=self.organization),
                self.mother.pk,
            )
        )

        self.assertEqual(history, [])

    def test_history_does_not_require_animal_lookup(self):
        with CaptureQueriesContext(connection) as queries:
            history = list(
                BirthSelector.history(
                    RequestContext(organization=self.organization),
                    self.mother.pk,
                )
            )

        self.assertEqual(history, [])

        self.assertFalse(
            any(
                "FROM animals" in query["sql"].lower()
                and "WHERE" in query["sql"].upper()
                for query in queries
            )
        )


class ReproductiveFlowHttpE2ETests(TestCase):
    """Chain the public reproductive endpoints without ORM writes to the flow."""

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="REPRO_E2E", name="Reproductive E2E organization")
        cls.user = User.objects.create_user(email="reproductive-e2e@example.com")
        Membership.objects.create(user=cls.user, organization=cls.organization,
                                  role=Membership.Role.OPERATOR, is_default=True)
        cls.species = Species.objects.create(code="REPRO_E2E", name="Reproductive E2E species")
        cls.breed = Breed.objects.create(species=cls.species, code="REPRO_E2E", name="Reproductive E2E breed")
        cls.female = Gender.objects.get(code="F")
        cls.male = Gender.objects.get(code="M")
        cls.active = AnimalStatus.objects.get(code="ACTIVE")
        cls.breeding_type = BreedingType.objects.create(code="REPRO_E2E", name="Reproductive E2E type")
        farm_type = FarmType.objects.create(code="REPRO_E2E", name="Reproductive E2E farm type")
        cls.farm = Farm.objects.create(organization=cls.organization, farm_type=farm_type,
                                       code="REPRO_E2E", name="Reproductive E2E farm")
        cls.lot = Lot.objects.create(organization=cls.organization, farm=cls.farm,
                                     code="REPRO_E2E", name="Reproductive E2E lot")
        fields = dict(organization=cls.organization, species=cls.species, breed=cls.breed,
                      status=cls.active, farm=cls.farm, lot=cls.lot,
                      birth_date=get_business_today(RequestContext(organization=cls.organization)) - timedelta(days=1000))
        cls.mother = Animal.objects.create(**fields, gender=cls.female, internal_id="E2E_MOTHER")
        cls.father = Animal.objects.create(**fields, gender=cls.male, internal_id="E2E_FATHER")
        cls.other_female = Animal.objects.create(**fields, gender=cls.female, internal_id="E2E_OTHER_FEMALE")
        cls.foreign_organization = Organization.objects.create(code="REPRO_FOREIGN", name="Foreign reproductive E2E")
        cls.foreign_user = User.objects.create_user(email="foreign-reproductive-e2e@example.com")
        Membership.objects.create(user=cls.foreign_user, organization=cls.foreign_organization,
                                  role=Membership.Role.OPERATOR, is_default=True)
        cls.foreign_female = Animal.objects.create(
            organization=cls.foreign_organization, species=cls.species, breed=cls.breed,
            gender=cls.female, status=cls.active, internal_id="E2E_FOREIGN_FEMALE",
            birth_date=get_business_today(RequestContext(organization=cls.organization)) - timedelta(days=1000),
        )
        cls.initial_animals = list(Animal._base_manager.order_by("pk").values())


    def test_public_http_flow_creates_breeding_pregnancy_birth_and_calf(self):
        today = get_business_today(RequestContext(organization=self.organization))
        expected_birth = (today + timedelta(days=20)).isoformat()
        weight = Decimal("30.00")
        headers = dict(HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

        response = self.client.post("/api/breeding/", {
            "animal_id": str(self.mother.pk), "male_id": str(self.father.pk),
            "breeding_type_id": str(self.breeding_type.pk),
            "date": (today - timedelta(days=300)).isoformat(),
            "expected_birth": expected_birth, "technician": "E2E technician",
        }, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        breeding = response.json()
        self.assertIsInstance(UUID(breeding["id"]), UUID)
        self.assertEqual(breeding["animal_id"], str(self.mother.pk))
        self.assertEqual(breeding["male_id"], str(self.father.pk))
        self.assertEqual(breeding["breeding_type_id"], str(self.breeding_type.pk))

        response = self.client.post("/api/pregnancies/", {
            "breeding_id": breeding["id"], "animal_id": breeding["animal_id"],
            "diagnosis_date": (today - timedelta(days=250)).isoformat(),
            "expected_birth": expected_birth, "confirmed": True,
        }, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        pregnancy = response.json()
        self.assertIsInstance(UUID(pregnancy["id"]), UUID)
        self.assertEqual(pregnancy["breeding_id"], breeding["id"])
        self.assertEqual(pregnancy["animal_id"], breeding["animal_id"])
        self.assertIs(pregnancy["confirmed"], True)
        self.assertEqual(pregnancy["status"], "ACTIVE")

        response = self.client.post("/api/births/", {
            "pregnancy_id": pregnancy["id"], "mother_id": pregnancy["animal_id"],
            "calf_gender_id": str(self.female.pk), "birth_date": today.isoformat(),
            "birth_weight": str(weight), "alive": True, "dystocia": False,
            "notes": "Public HTTP reproductive flow.",
        }, content_type="application/json", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        birth = response.json()
        self.assertIsInstance(UUID(birth["id"]), UUID)
        self.assertEqual(birth["pregnancy_id"], pregnancy["id"])
        self.assertEqual(birth["mother_id"], pregnancy["animal_id"])
        self.assertIsNotNone(birth["calf_id"])
        self.assertIsInstance(UUID(birth["calf_id"]), UUID)
        self.assertIs(birth["alive"], True)

        response = self.client.get(f"/api/births/{birth['id']}", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        saved_birth = response.json()
        for field in ("id", "pregnancy_id", "mother_id", "calf_id", "calf_gender_id"):
            self.assertEqual(saved_birth[field], birth[field])
        self.assertIs(saved_birth["alive"], True)
        self.assertIs(saved_birth["dystocia"], False)
        self.assertEqual(saved_birth["birth_date"], today.isoformat())
        self.assertEqual(Decimal(str(saved_birth["birth_weight"])), weight)

        response = self.client.get(f"/api/pregnancies/{pregnancy['id']}", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        saved_pregnancy = response.json()
        self.assertEqual(saved_pregnancy["id"], pregnancy["id"])
        self.assertEqual(saved_pregnancy["breeding_id"], breeding["id"])
        self.assertEqual(saved_pregnancy["animal_id"], str(self.mother.pk))
        self.assertIs(saved_pregnancy["confirmed"], True)
        self.assertEqual(saved_pregnancy["status"], "FINISHED")

        response = self.client.get(f"/api/animals/{birth['calf_id']}", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        calf = response.json()
        self.assertEqual(calf["id"], birth["calf_id"])
        for field, expected in (
            ("species_id", self.species.pk), ("breed_id", self.breed.pk),
            ("gender_id", self.female.pk), ("status_id", self.active.pk),
            ("mother_id", self.mother.pk), ("father_id", self.father.pk),
            ("farm_id", self.farm.pk), ("lot_id", self.lot.pk),
        ):
            self.assertEqual(calf[field], str(expected))
        self.assertEqual(calf["status"], self.active.name)
        self.assertIs(calf["is_active"], True)
        self.assertEqual(calf["birth_date"], today.isoformat())
        self.assertEqual(Decimal(str(calf["birth_weight"])), weight)
        self.assertEqual(calf["internal_id"], "CRIA-00001")

        # Organization is absent from these response schemas. ORM is read-only
        # here, after all HTTP stages, solely to verify structural tenant scope.
        for model, identifier in ((BreedingEvent, breeding["id"]),
                                  (Pregnancy, pregnancy["id"]),
                                  (Birth, birth["id"]), (Animal, calf["id"])):
            self.assertEqual(model._base_manager.values_list("organization_id", flat=True).get(pk=identifier),
                             self.organization.pk)


    def flow_request(self, method, path, payload=None, user=None, expected_status=200):
        headers = dict(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user or self.user)}")
        if method == "POST":
            response = self.client.post(path, payload or {}, content_type="application/json", **headers)
        else:
            response = self.client.get(path, **headers)
        self.assertEqual(response.status_code, expected_status, f"{method} {path}: {response.content!r}")
        body = response.json()
        if expected_status == 400:
            self.assertIsInstance(body["detail"], str)
            self.assertTrue(body["detail"])
        return body

    def create_http_breeding(self):
        today = get_business_today(RequestContext(organization=self.organization))
        return self.flow_request("POST", "/api/breeding/", {
            "animal_id": str(self.mother.pk), "male_id": str(self.father.pk),
            "breeding_type_id": str(self.breeding_type.pk),
            "date": (today - timedelta(days=300)).isoformat(),
            "expected_birth": (today + timedelta(days=20)).isoformat(),
        })

    def create_http_pregnancy(self, breeding):
        today = get_business_today(RequestContext(organization=self.organization))
        pregnancy = self.flow_request("POST", "/api/pregnancies/", {
            "breeding_id": breeding["id"], "animal_id": breeding["animal_id"],
            "diagnosis_date": (today - timedelta(days=250)).isoformat(),
            "expected_birth": (today + timedelta(days=20)).isoformat(), "confirmed": True,
        })
        self.assertEqual(pregnancy["status"], "ACTIVE")
        return pregnancy

    def birth_http_payload(self, pregnancy, mother_id=None):
        return {
            "pregnancy_id": pregnancy["id"],
            "mother_id": mother_id or pregnancy["animal_id"],
            "calf_gender_id": str(self.female.pk),
            "birth_date": get_business_today(RequestContext(organization=self.organization)).isoformat(), "birth_weight": "30.00",
            "alive": True, "dystocia": False,
        }

    def assert_flow_rows_at_end(self, breeding, pregnancy=None, birth=None):
        # Final read-only ORM assertions catch hidden rows and extra identities
        # that public lists cannot establish absolutely.
        for model, expected in ((BreedingEvent, breeding), (Pregnancy, pregnancy), (Birth, birth)):
            expected_ids = {UUID(expected["id"])} if expected else set()
            self.assertEqual(set(model._base_manager.values_list("pk", flat=True)), expected_ids)
            if expected:
                self.assertEqual(model._base_manager.values_list("organization_id", flat=True).get(pk=expected["id"]),
                                 self.organization.pk)
        initial_ids = {row["id"] for row in self.initial_animals}
        expected_animal_ids = initial_ids | ({UUID(birth["calf_id"])} if birth else set())
        self.assertEqual(set(Animal._base_manager.values_list("pk", flat=True)), expected_animal_ids)
        self.assertEqual(list(Animal._base_manager.filter(pk__in=initial_ids).order_by("pk").values()),
                         self.initial_animals)
        if birth:
            self.assertEqual(Animal._base_manager.values_list("organization_id", flat=True).get(pk=birth["calf_id"]),
                             self.organization.pk)

    def test_http_cross_tenant_breeding_cannot_create_pregnancy(self):
        breeding = self.create_http_breeding()
        before = self.flow_request("GET", f"/api/breeding/{breeding['id']}")
        today = get_business_today(RequestContext(organization=self.organization))
        self.flow_request("POST", "/api/pregnancies/", {
            "breeding_id": breeding["id"], "animal_id": str(self.foreign_female.pk),
            "diagnosis_date": (today - timedelta(days=250)).isoformat(),
            "expected_birth": (today + timedelta(days=20)).isoformat(), "confirmed": True,
        }, user=self.foreign_user, expected_status=400)
        self.assertEqual(self.flow_request("GET", "/api/pregnancies/", user=self.foreign_user), [])
        self.assertEqual(self.flow_request("GET", f"/api/breeding/{breeding['id']}"), before)
        self.assert_flow_rows_at_end(breeding)

    def test_http_pregnancy_rejects_different_female_of_same_tenant(self):
        breeding = self.create_http_breeding()
        before = self.flow_request("GET", f"/api/breeding/{breeding['id']}")
        today = get_business_today(RequestContext(organization=self.organization))
        self.flow_request("POST", "/api/pregnancies/", {
            "breeding_id": breeding["id"], "animal_id": str(self.other_female.pk),
            "diagnosis_date": (today - timedelta(days=250)).isoformat(),
            "expected_birth": (today + timedelta(days=20)).isoformat(), "confirmed": True,
        }, expected_status=400)
        self.assertEqual(self.flow_request("GET", "/api/pregnancies/"), [])
        self.assertEqual(self.flow_request("GET", f"/api/breeding/{breeding['id']}"), before)
        self.assert_flow_rows_at_end(breeding)

    def test_http_aborted_pregnancy_cannot_create_birth_or_calf(self):
        breeding = self.create_http_breeding()
        pregnancy = self.create_http_pregnancy(breeding)
        aborted = self.flow_request("POST", f"/api/pregnancies/{pregnancy['id']}/abort")
        self.assertEqual(aborted["status"], "ABORTED")
        before = self.flow_request("GET", f"/api/pregnancies/{pregnancy['id']}")
        self.assertEqual(before["status"], "ABORTED")
        self.flow_request("POST", "/api/births/", self.birth_http_payload(pregnancy), expected_status=400)
        self.assertEqual(self.flow_request("GET", f"/api/pregnancies/{pregnancy['id']}"), before)
        self.assertEqual(self.flow_request("GET", "/api/births/"), [])
        self.assertEqual(self.flow_request("GET", f"/api/breeding/{breeding['id']}"), breeding)
        self.assert_flow_rows_at_end(breeding, pregnancy)

    def test_http_birth_rejects_different_mother_of_same_tenant(self):
        breeding = self.create_http_breeding()
        pregnancy = self.create_http_pregnancy(breeding)
        before = self.flow_request("GET", f"/api/pregnancies/{pregnancy['id']}")
        self.flow_request("POST", "/api/births/",
                          self.birth_http_payload(pregnancy, str(self.other_female.pk)), expected_status=400)
        self.assertEqual(self.flow_request("GET", f"/api/pregnancies/{pregnancy['id']}"), before)
        self.assertEqual(before["status"], "ACTIVE")
        self.assertEqual(self.flow_request("GET", "/api/births/"), [])
        self.assertEqual(self.flow_request("GET", f"/api/breeding/{breeding['id']}"), breeding)
        self.assert_flow_rows_at_end(breeding, pregnancy)

    def test_http_completed_pregnancy_rejects_second_birth_and_preserves_first_calf(self):
        breeding = self.create_http_breeding()
        pregnancy = self.create_http_pregnancy(breeding)
        payload = self.birth_http_payload(pregnancy)
        birth = self.flow_request("POST", "/api/births/", payload)
        before_birth = self.flow_request("GET", f"/api/births/{birth['id']}")
        before_calf = self.flow_request("GET", f"/api/animals/{birth['calf_id']}")
        before_pregnancy = self.flow_request("GET", f"/api/pregnancies/{pregnancy['id']}")
        self.assertEqual(before_pregnancy["status"], "FINISHED")
        self.flow_request("POST", "/api/births/", payload, expected_status=400)
        self.assertEqual(self.flow_request("GET", f"/api/pregnancies/{pregnancy['id']}"), before_pregnancy)
        self.assertEqual(self.flow_request("GET", f"/api/births/{birth['id']}"), before_birth)
        self.assertEqual(self.flow_request("GET", f"/api/animals/{birth['calf_id']}"), before_calf)
        self.assertEqual(self.flow_request("GET", f"/api/breeding/{breeding['id']}"), breeding)
        self.assertEqual([row["id"] for row in self.flow_request("GET", "/api/births/")], [birth["id"]])
        self.assert_flow_rows_at_end(breeding, pregnancy, birth)


class BirthInputTranslationHTTPTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixture = BirthAutomaticCalfRegressionTests
        fixture.setUpTestData.__func__(fixture)
        for name in ("organization", "female", "mother", "father", "breeding", "pregnancy"):
            setattr(cls, name, getattr(fixture, name))
        cls.user = User.objects.create_user(email="h5e@example.com")
        Membership.objects.create(user=cls.user, organization=cls.organization,
                                  role=Membership.Role.OPERATOR, is_default=True)

    snapshot = BirthAutomaticCalfRegressionTests.snapshot

    def data(self, **changes):
        payload = dict(pregnancy_id=str(self.pregnancy.pk), mother_id=str(self.mother.pk),
            calf_gender_id=str(self.female.pk), birth_date="2025-10-01",
            birth_weight="30.00", alive=False, dystocia=False)
        payload.update(changes)
        return payload

    def request(self, **changes):
        return self.client.post("/api/births/", data=self.data(**changes),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def assert_unchanged(self, before):
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(Birth._base_manager.count(), 0)
        self.assertEqual(Animal._base_manager.count(), 2)

    def assert_precision_rejected(self, value):
        before = self.snapshot()
        try:
            response = self.request(birth_weight=value)
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.json()["detail"])
        finally:
            self.assert_unchanged(before)

    def test_http_birth_max_digits_returns_400_without_side_effects(self):
        self.assert_precision_rejected("10000.00")

    def test_http_birth_decimal_places_returns_400_without_side_effects(self):
        self.assert_precision_rejected("1.001")

    def test_http_birth_max_whole_digits_returns_400_without_side_effects(self):
        self.assert_precision_rejected("10000")

    def test_http_existing_business_rules_remain_400(self):
        before = self.snapshot()
        cases = (dict(birth_weight="0"), dict(birth_weight="-1"),
                 dict(birth_date="2024-12-31"), dict(birth_date="2025-01-31"),
                 dict(birth_date=(timezone.localdate() + timedelta(days=1)).isoformat()),
                 dict(mother_id=str(self.father.pk)), dict(calf_gender_id=None),
                 dict(calf_id=str(self.father.pk), alive=False))
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(self.request(**changes).status_code, 400)
                self.assert_unchanged(before)

    def assert_validation_propagates(self, errors):
        before = self.snapshot()
        error = ValidationError(errors)
        with patch.object(Birth, "full_clean", side_effect=error):
            with self.assertRaises(ValidationError) as caught:
                self.request()
        self.assertIs(caught.exception, error)
        self.assert_unchanged(before)

    def test_http_unknown_birth_validation_error_propagates_original(self):
        self.assert_validation_propagates({"notes": ValidationError("unknown", code="unexpected")})

    def test_http_mixed_birth_validation_error_propagates_complete_original(self):
        self.assert_validation_propagates({
            "birth_weight": ValidationError("precision", code="max_digits"),
            "notes": ValidationError("unknown", code="unexpected"),
        })

    def test_http_known_code_on_internal_field_propagates(self):
        self.assert_validation_propagates({"pregnancy": ValidationError("internal", code="max_digits")})

    def test_http_unstructured_birth_validation_error_propagates(self):
        self.assert_validation_propagates("unexpected internal error")

    def test_http_unrelated_birth_integrity_error_propagates_and_rolls_back(self):
        before = self.snapshot()
        error = IntegrityError("unrelated database failure")
        # Fail after a real Birth INSERT to verify the service's complete rollback.
        real_save = Birth.save
        def save_then_fail(instance, *args, **kwargs):
            real_save(instance, *args, **kwargs)
            self.assertTrue(Birth._base_manager.filter(pk=instance.pk).exists())
            raise error
        with patch.object(Birth, "save", save_then_fail):
            with self.assertRaises(IntegrityError) as caught:
                self.request()
        self.assertIs(caught.exception, error)
        self.assert_unchanged(before)

    def test_http_invalid_birth_schema_remains_422(self):
        before = self.snapshot()
        for changes in (dict(birth_weight="not-decimal"), dict(pregnancy_id="not-uuid"),
                        dict(birth_date="not-date"), dict(alive="not-bool")):
            with self.subTest(changes=changes):
                self.assertEqual(self.request(**changes).status_code, 422)
                self.assert_unchanged(before)

    def test_http_inaccessible_pregnancy_keeps_existing_400(self):
        before = self.snapshot()
        self.assertEqual(self.request(pregnancy_id=str(uuid4())).status_code, 400)
        self.assert_unchanged(before)
        Pregnancy._base_manager.filter(pk=self.pregnancy.pk).update(is_active=False)
        before = self.snapshot()
        self.assertEqual(self.request().status_code, 400)
        self.assert_unchanged(before)
        foreign = Organization.objects.create(code="H5E_FOREIGN", name="Foreign")
        Pregnancy._base_manager.filter(pk=self.pregnancy.pk).update(is_active=True, organization=foreign)
        before = self.snapshot()
        self.assertEqual(self.request().status_code, 400)
        self.assert_unchanged(before)
        response = self.client.get(f"/api/births/{uuid4()}",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")
        self.assertEqual(response.status_code, 404)

    def test_http_valid_dead_birth_preserves_null_notes_and_finishes_pregnancy(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        birth = Birth._base_manager.get(pk=response.json()["id"])
        self.assertIsNone(birth.calf_id)
        self.assertIsNone(birth.notes)
        self.assertEqual(Animal._base_manager.count(), 2)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)

    def test_http_explicit_null_notes_remains_null(self):
        self.assertEqual(self.request(notes=None).status_code, 200)
        self.assertIsNone(Birth._base_manager.get().notes)

    def test_http_valid_alive_birth_creates_active_calf_and_finishes_pregnancy(self):
        response = self.request(alive=True, notes="Preserved")
        self.assertEqual(response.status_code, 200)
        birth = Birth._base_manager.get(pk=response.json()["id"])
        calf = Animal._base_manager.get(pk=birth.calf_id)
        self.assertEqual(calf.status.code, "ACTIVE")
        self.assertTrue(calf.is_active)
        self.assertEqual(calf.internal_id, "CRIA-00001")
        self.assertEqual(birth.notes, "Preserved")
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)
        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertEqual(Animal._base_manager.count(), 3)


class BirthPregnancyCollisionTests(TestCase):
    setUpTestData = classmethod(BirthInputTranslationHTTPTests.setUpTestData.__func__)
    data = BirthInputTranslationHTTPTests.data
    request = BirthInputTranslationHTTPTests.request
    snapshot = BirthAutomaticCalfRegressionTests.snapshot

    def setUp(self):
        payload = BirthCreateSchema(**self.data(alive=True))
        self.first = BirthService.create(RequestContext(organization=self.organization), payload)
        self.calf = self.first.calf
        self.before = self.snapshot()

    def assert_preserved(self):
        for instance in (self.first, self.calf, self.pregnancy):
            instance.refresh_from_db()
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(Birth._base_manager.count(), 1)
        self.assertEqual(Animal._base_manager.count(), 3)
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)
        self.assertFalse(connection.needs_rollback)

    def test_http_sequential_second_birth_remains_400(self):
        self.assertEqual(self.request(alive=True).status_code, 400)
        self.assert_preserved()

    def test_real_full_clean_pregnancy_unique_translates_with_original_cause(self):
        with patch.object(BirthService, "_validate_business_rules"):
            with self.assertRaises(BirthValidationError) as caught:
                BirthService.create(RequestContext(organization=self.organization), BirthCreateSchema(**self.data(alive=True)))
        self.assertIsInstance(caught.exception.__cause__, ValidationError)
        self.assertEqual(caught.exception.__cause__.error_dict["pregnancy"][0].code, "unique")
        self.assert_preserved()

    def test_http_full_clean_pregnancy_unique_returns_400(self):
        with patch.object(BirthService, "_validate_business_rules"):
            self.assertEqual(self.request(alive=True).status_code, 400)
        self.assert_preserved()

    def test_mixed_pregnancy_unique_and_unknown_propagates_complete_original(self):
        error = ValidationError({"pregnancy": ValidationError("duplicate", code="unique"),
                                 "notes": ValidationError("unexpected", code="unexpected")})
        with patch.object(BirthService, "_validate_business_rules"), patch.object(Birth, "full_clean", side_effect=error):
            with self.assertRaises(ValidationError) as caught:
                self.request(alive=True)
        self.assertIs(caught.exception, error)
        self.assert_preserved()

    def test_real_db_collision_translates_preserves_cause_and_connection(self):
        with patch.object(BirthService, "_validate_business_rules"), patch.object(Birth, "full_clean"):
            with self.assertRaises(BirthValidationError) as caught:
                BirthService.create(RequestContext(organization=self.organization), BirthCreateSchema(**self.data(alive=True)))
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.assertIsInstance(caught.exception.__cause__.__cause__, sqlite3.IntegrityError)
        self.assertEqual(str(caught.exception), "Esta gestación ya tiene un parto registrado.")
        self.assertEqual(str(caught.exception.__cause__.__cause__), "UNIQUE constraint failed: births.pregnancy_id")
        self.assert_preserved()

    def test_http_real_db_collision_returns_400(self):
        with patch.object(BirthService, "_validate_business_rules"), patch.object(Birth, "full_clean"):
            self.assertEqual(self.request(alive=True).status_code, 400)
        self.assert_preserved()

    def test_soft_deleted_birth_still_reserves_physical_pregnancy(self):
        self.first.delete()
        self.first.refresh_from_db()
        self.assertFalse(self.first.is_active)
        self.assertIsNotNone(self.first.deleted_at)
        self.before = self.snapshot()
        with patch.object(BirthService, "_validate_business_rules"):
            self.assertEqual(self.request(alive=True).status_code, 400)
        self.assert_preserved()

    def test_nonexact_unrelated_or_unverified_integrity_errors_propagate_original(self):
        import sqlite3
        from types import SimpleNamespace
        causes = [sqlite3.IntegrityError("UNIQUE constraint failed: births.pregnancy_id_extra"),
                  sqlite3.IntegrityError("UNIQUE constraint failed: births.pregnancy_id "),
                  sqlite3.IntegrityError("UNIQUE constraint failed: births.pregnancy_id, births.organization_id"),
                  Exception("UNIQUE constraint failed: births.pregnancy_id"),
                  sqlite3.IntegrityError("NOT NULL constraint failed: births.birth_weight")]
        for name in ("other_constraint", "births_pregnancy_id_key"):
            cause = Exception("PostgreSQL unique violation")
            cause.diag = SimpleNamespace(constraint_name=name)
            causes.append(cause)
        for cause in causes:
            with self.subTest(cause=str(cause), diag=getattr(cause, "diag", None)):
                error = IntegrityError("database failure")
                error.__cause__ = cause
                with patch.object(BirthService, "_validate_business_rules"), patch.object(Birth, "full_clean"), patch.object(Birth, "save", side_effect=error):
                    with self.assertRaises(IntegrityError) as caught:
                        self.request(alive=True)
                self.assertIs(caught.exception, error)
                self.assert_preserved()

    def test_real_unrelated_not_null_error_propagates_original_and_rolls_back(self):
        real_save = Birth.save
        database_errors = []

        def invalid_save(instance, *args, **kwargs):
            instance.alive = None
            try:
                return real_save(instance, *args, **kwargs)
            except IntegrityError as exc:
                database_errors.append(exc)
                raise

        with patch.object(BirthService, "_validate_business_rules"), patch.object(Birth, "full_clean"), patch.object(Birth, "save", invalid_save):
            with self.assertRaises(IntegrityError) as caught:
                self.request(alive=True)
        self.assertIs(caught.exception, database_errors[0])
        self.assertIsInstance(caught.exception.__cause__, sqlite3.IntegrityError)
        self.assertEqual(str(caught.exception.__cause__), "NOT NULL constraint failed: births.alive")
        self.assert_preserved()

class BirthTenantBusinessDateTests(TestCase):
    setUpTestData = classmethod(BirthInputTranslationHTTPTests.setUpTestData.__func__)
    data = BirthInputTranslationHTTPTests.data
    request = BirthInputTranslationHTTPTests.request
    snapshot = BirthAutomaticCalfRegressionTests.snapshot

    def setUp(self):
        self.organization.timezone = 'America/Mexico_City'
        self.organization.save(update_fields=['timezone'])

    def at(self, instant):
        from datetime import datetime
        return patch('apps.common.temporal.timezone.now', return_value=datetime.fromisoformat(instant))

    def assert_created(self, response, day):
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertEqual(set(result), {'id', 'pregnancy_id', 'mother_id', 'calf_id', 'calf_gender_id',
                                      'birth_date', 'birth_weight', 'alive', 'dystocia', 'notes'})
        birth = Birth._base_manager.get(pk=result['id'])
        self.assertEqual(birth.birth_date.isoformat(), day)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)
        if result['alive']:
            calf = Animal._base_manager.get(pk=result['calf_id'])
            self.assertEqual(calf.birth_date, birth.birth_date)
            self.assertEqual(calf.birth_weight, birth.birth_weight)
            self.assertFalse(hasattr(calf, '_birth_business_today'))
        else:
            self.assertIsNone(result['calf_id'])

    def test_mexico_0030_accepts_local_day_05_with_automatic_calf(self):
        with self.at('2026-10-06T00:30:00+00:00'):
            self.assert_created(self.request(alive=True, birth_date='2026-10-05'), '2026-10-05')

    def test_mexico_0030_rejects_utc_day_06_without_partial_state(self):
        before = self.snapshot()
        with self.at('2026-10-06T00:30:00+00:00'):
            self.assertEqual(self.request(alive=True, birth_date='2026-10-06').status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_mexico_before_midnight_rejects_06(self):
        before = self.snapshot()
        with self.at('2026-10-06T05:59:59+00:00'):
            self.assertEqual(self.request(alive=True, birth_date='2026-10-06').status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_mexico_midnight_accepts_06_with_automatic_calf(self):
        with self.at('2026-10-06T06:00:00+00:00'):
            self.assert_created(self.request(alive=True, birth_date='2026-10-06'), '2026-10-06')

    def test_tenant_ahead_of_utc_accepts_calf_date_in_utc_tomorrow(self):
        self.organization.timezone = 'Pacific/Kiritimati'
        self.organization.save(update_fields=['timezone'])
        with self.at('2026-10-05T12:30:00+00:00'):
            self.assert_created(self.request(alive=True, birth_date='2026-10-06'), '2026-10-06')

    def test_invalid_timezone_fails_closed_with_controlled_503(self):
        Organization._base_manager.filter(pk=self.organization.pk).update(timezone='Invalid/Timezone')
        before = self.snapshot()
        response = self.request(alive=True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'tenant_timezone_unavailable')
        self.assertEqual(self.snapshot(), before)

    def test_dead_birth_uses_tenant_day_and_creates_no_animal(self):
        with self.at('2026-10-06T00:30:00+00:00'):
            self.assert_created(self.request(birth_date='2026-10-05'), '2026-10-05')
        self.assertEqual(Animal._base_manager.count(), 2)

    def test_existing_calf_is_not_temporally_or_otherwise_modified(self):
        calf = Animal.objects.create(organization=self.organization, species=self.mother.species,
            breed=self.mother.breed, gender=self.female, status=self.mother.status, internal_id='EXISTING')
        before = Animal._base_manager.filter(pk=calf.pk).values().get()
        with self.at('2026-10-06T00:30:00+00:00'):
            response = self.request(alive=True, calf_id=str(calf.pk), calf_gender_id=None, birth_date='2026-10-05')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['calf_id'], str(calf.pk))
        self.assertEqual(Animal._base_manager.filter(pk=calf.pk).values().get(), before)

    def test_ordinary_animal_save_retains_utc_future_rejection(self):
        self.mother.birth_date = date(2026, 10, 6)
        with self.at('2026-10-05T12:30:00+00:00'):
            with self.assertRaises(ValidationError):
                self.mother.save()

    def test_birth_error_after_finish_rolls_back_every_write(self):
        before = self.snapshot()
        real_finish = BirthService._finish_pregnancy
        def fail_after_finish(pregnancy):
            real_finish(pregnancy)
            self.assertEqual(Pregnancy.objects.get(pk=pregnancy.pk).status, PregnancyStatus.FINISHED)
            raise RuntimeError('failure before commit')
        with patch.object(BirthService, '_finish_pregnancy', side_effect=fail_after_finish):
            with self.assertRaises(RuntimeError):
                self.request(alive=True)
        self.assertEqual(self.snapshot(), before)

class BirthDetailHTTPTests(TestCase):
    setUpTestData = classmethod(BirthInputTranslationHTTPTests.setUpTestData.__func__)
    data = BirthInputTranslationHTTPTests.data

    def setUp(self):
        self.birth = BirthService.create(RequestContext(organization=self.organization),
            BirthCreateSchema(**self.data(alive=True, notes='Detail note')))

    def get_detail(self, identifier=None, user=None):
        return self.client.get(f'/api/births/{identifier or self.birth.pk}',
            HTTP_AUTHORIZATION=f'Bearer {create_access_token(user or self.user)}')

    def test_each_read_role_gets_exact_active_detail_contract(self):
        for role in Membership.Role.values:
            with self.subTest(role=role):
                Membership.objects.filter(user=self.user).update(role=role)
                response = self.get_detail()
                self.assertEqual(response.status_code, 200)
                value = response.json()
                self.assertEqual(set(value), {'id', 'pregnancy_id', 'mother_id', 'calf_id', 'calf_gender_id',
                    'birth_date', 'birth_weight', 'alive', 'dystocia', 'notes'})
                self.assertEqual(value['id'], str(self.birth.pk))
                self.assertEqual(value['mother_id'], str(self.mother.pk))
                self.assertEqual(value['calf_id'], str(self.birth.calf_id))
                self.assertEqual(value['birth_weight'], '30.00')
                self.assertEqual(value['notes'], 'Detail note')

    def test_foreign_tenant_detail_returns_404(self):
        foreign = Organization.objects.create(code='DETAIL_FOREIGN', name='Foreign')
        user = User.objects.create_user(email='birth-detail-foreign@example.com')
        Membership.objects.create(user=user, organization=foreign, role=Membership.Role.VIEWER, is_default=True)
        self.assertEqual(self.get_detail(user=user).status_code, 404)
        self.assertEqual(Birth._base_manager.get(pk=self.birth.pk).notes, 'Detail note')

    def test_soft_deleted_birth_detail_returns_404(self):
        self.birth.delete()
        self.assertEqual(self.get_detail().status_code, 404)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)
        self.assertTrue(Animal._base_manager.filter(pk=self.birth.calf_id).exists())

    def test_inactive_historical_relations_remain_readable_to_viewer(self):
        for model, identifier in ((Animal, self.mother.pk), (Animal, self.birth.calf_id),
                                  (Pregnancy, self.pregnancy.pk), (BreedingEvent, self.breeding.pk), (Gender, self.female.pk)):
            model._base_manager.filter(pk=identifier).update(is_active=False)
        Membership.objects.filter(user=self.user).update(role=Membership.Role.VIEWER)
        response = self.get_detail()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['calf_id'], str(self.birth.calf_id))
        self.assertEqual(response.json()['calf_gender_id'], str(self.female.pk))

    def test_invalid_uuid_returns_422_without_mutation(self):
        response = self.get_detail('invalid-uuid')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Birth._base_manager.count(), 1)

    def test_inactive_membership_cannot_read_detail(self):
        Membership.objects.filter(user=self.user).update(is_active=False)
        self.assertEqual(self.get_detail().status_code, 403)
