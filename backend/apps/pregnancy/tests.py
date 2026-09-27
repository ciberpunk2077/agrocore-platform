from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.animals.models import Animal
from apps.breeding.models import BreedingEvent
from apps.catalogs.models import (
    AnimalStatus,
    Breed,
    BreedingType,
    Gender,
    Species,
)
from apps.common.context.context import RequestContext
from apps.organizations.models import Organization
from apps.pregnancy.api.schemas import PregnancyCreateSchema
from apps.pregnancy.models import Pregnancy, PregnancyStatus
from apps.pregnancy.services import PregnancyService


class PregnancyServiceCharacterizationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.organization = Organization.objects.create(
            code="PREG_TEST",
            name="Pregnancy test organization",
        )

        cls.other_organization = Organization.objects.create(
            code="PREG_OTHER",
            name="Other pregnancy organization",
        )

        cls.species = Species.objects.create(
            code="PREG_SPECIES",
            name="Pregnancy test species",
        )

        cls.breed = Breed.objects.create(
            species=cls.species,
            code="PREG_BREED",
            name="Pregnancy test breed",
        )

        cls.female = Gender.objects.create(
            code="F",
            name="Pregnancy test female",
        )

        cls.male = Gender.objects.create(
            code="M",
            name="Pregnancy test male",
        )

        cls.status = AnimalStatus.objects.create(
            code="PREG_ACTIVE",
            name="Pregnancy test active",
        )

        cls.breeding_type = BreedingType.objects.create(
            code="PREG_TYPE",
            name="Pregnancy test breeding type",
        )

        cls.animal = cls.make_animal(
            cls.organization,
            cls.female,
            "PREG_FEMALE",
        )

        cls.other_animal = cls.make_animal(
            cls.other_organization,
            cls.female,
            "PREG_OTHER_FEMALE",
        )

        cls.second_animal = cls.make_animal(
            cls.organization,
            cls.female,
            "PREG_SECOND_FEMALE",
        )

        cls.breeding = cls.make_breeding(
            cls.organization,
            cls.animal,
            date(2025, 1, 1),
        )

        cls.other_breeding = cls.make_breeding(
            cls.other_organization,
            cls.other_animal,
            date(2025, 1, 1),
        )

    @classmethod
    def make_animal(cls, organization, gender, internal_id):
        return Animal.objects.create(
            organization=organization,
            species=cls.species,
            breed=cls.breed,
            gender=gender,
            status=cls.status,
            internal_id=internal_id,
            is_active=True,
        )

    @classmethod
    def make_breeding(cls, organization, animal, breeding_date):
        event = BreedingEvent(
            organization=organization,
            animal=animal,
            male=None,
            breeding_type=cls.breeding_type,
            date=breeding_date,
            expected_birth=date(2025, 10, 1),
        )

        event.full_clean()
        event.save()

        return event

    def make_payload(self, **overrides):
        fields = {
            "breeding_id": self.breeding.pk,
            "animal_id": self.animal.pk,
            "diagnosis_date": date(2025, 2, 1),
            "expected_birth": date(2025, 10, 1),
            "confirmed": True,
            "notes": "Pregnancy characterization test",
        }

        fields.update(overrides)

        return PregnancyCreateSchema(**fields)

    def test_create_valid_pregnancy(self):
        pregnancy = PregnancyService.create(
            RequestContext(organization=self.organization),
            self.make_payload(),
        )

        pregnancy.refresh_from_db()

        self.assertEqual(
            pregnancy.organization_id,
            self.organization.pk,
        )
        self.assertEqual(
            pregnancy.animal_id,
            self.animal.pk,
        )
        self.assertEqual(
            pregnancy.breeding_id,
            self.breeding.pk,
        )
        self.assertTrue(pregnancy.confirmed)
        self.assertEqual(
            pregnancy.status,
            PregnancyStatus.ACTIVE,
        )

    def test_create_rejects_animal_from_other_organization(self):
        payload = self.make_payload(
            animal_id=self.other_animal.pk,
        )

        with self.assertRaises(ValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_breeding_from_other_organization(self):
        payload = self.make_payload(
            breeding_id=self.other_breeding.pk,
            animal_id=self.other_animal.pk,
        )

        with self.assertRaises(ValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_animal_different_from_breeding_animal(self):
        payload = self.make_payload(
            animal_id=self.second_animal.pk,
        )

        with self.assertRaises(ValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_second_active_pregnancy_for_same_breeding(self):
        PregnancyService.create(
            RequestContext(organization=self.organization),
            self.make_payload(),
        )

        with self.assertRaises(ValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                self.make_payload(),
            )

        self.assertEqual(Pregnancy.objects.count(), 1)



    def test_create_rejects_unconfirmed_pregnancy(self):
        payload = self.make_payload(
            confirmed=False,
        )

        with self.assertRaises(ValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_diagnosis_before_breeding_date(self):
        payload = self.make_payload(
            diagnosis_date=date(2024, 12, 1),
        )

        with self.assertRaises(ValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_expected_birth_not_after_diagnosis(self):
        payload = self.make_payload(
            diagnosis_date=date(2025, 2, 1),
            expected_birth=date(2025, 1, 15),
        )

        with self.assertRaises(ValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)


    def test_abort_active_pregnancy(self):
        pregnancy = PregnancyService.create(
            RequestContext(organization=self.organization),
            self.make_payload(),
        )

        result = PregnancyService.abort(
            RequestContext(organization=self.organization),
            pregnancy.pk,
        )

        pregnancy.refresh_from_db()

        self.assertEqual(
            pregnancy.status,
            PregnancyStatus.ABORTED,
        )
        self.assertEqual(
            result.pk,
            pregnancy.pk,
        )

    def test_abort_rejects_finished_pregnancy(self):
        pregnancy = PregnancyService.create(
            RequestContext(organization=self.organization),
            self.make_payload(),
        )

        pregnancy.status = PregnancyStatus.FINISHED
        pregnancy.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            PregnancyService.abort(
                RequestContext(organization=self.organization),
                pregnancy.pk,
            )

        pregnancy.refresh_from_db()

        self.assertEqual(
            pregnancy.status,
            PregnancyStatus.FINISHED,
        )

    def test_abort_rejects_pregnancy_from_other_organization(self):
        pregnancy = Pregnancy.objects.create(
            organization=self.other_organization,
            breeding=self.other_breeding,
            animal=self.other_animal,
            diagnosis_date=date(2025, 2, 1),
            expected_birth=date(2025, 10, 1),
            confirmed=True,
            status=PregnancyStatus.ACTIVE,
        )

        with self.assertRaises(ValidationError):
            PregnancyService.abort(
                RequestContext(organization=self.organization),
                pregnancy.pk,
            )

        pregnancy.refresh_from_db()

        self.assertEqual(
            pregnancy.status,
            PregnancyStatus.ACTIVE,
        )


    def test_abort_rejects_already_aborted_pregnancy(self):
        pregnancy = PregnancyService.create(
            RequestContext(organization=self.organization),
            self.make_payload(),
        )

        PregnancyService.abort(
            RequestContext(organization=self.organization),
            pregnancy.pk,
        )

        with self.assertRaises(ValidationError):
            PregnancyService.abort(
                RequestContext(organization=self.organization),
                pregnancy.pk,
            )

        pregnancy.refresh_from_db()

        self.assertEqual(
            pregnancy.status,
            PregnancyStatus.ABORTED,
        )