from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.test import TestCase

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
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
from apps.common.exceptions.pregnancy import PregnancyValidationError
from apps.organizations.models import Organization
from apps.pregnancy.api.schemas import PregnancyCreateSchema
from apps.pregnancy.models import Pregnancy, PregnancyStatus
from apps.pregnancy.services import PregnancyService
from apps.pregnancy.selectors import PregnancySelector


class PregnancyTestBase(TestCase):

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


class PregnancyServiceValidationTests(PregnancyTestBase):
    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.today = date(2025, 3, 1)
        clock = patch(
            "apps.pregnancy.services.pregnancy_service.timezone.localdate",
            return_value=self.today,
        )
        clock.start()
        self.addCleanup(clock.stop)

    def assert_create_rejected(self, **overrides):
        before = list(Pregnancy._base_manager.values())
        with self.assertRaises(PregnancyValidationError):
            PregnancyService.create(self.context, self.make_payload(**overrides))
        self.assertEqual(list(Pregnancy._base_manager.values()), before)

    def assert_abort_rejected(self, pregnancy_id, context=None):
        before = list(Pregnancy._base_manager.values())
        with self.assertRaises(PregnancyValidationError):
            PregnancyService.abort(context or self.context, pregnancy_id)
        self.assertEqual(list(Pregnancy._base_manager.values()), before)

    def test_diagnosis_on_breeding_date_is_valid(self):
        pregnancy = PregnancyService.create(self.context, self.make_payload(
            diagnosis_date=self.breeding.date,
        ))
        pregnancy.refresh_from_db()
        self.assertEqual(pregnancy.diagnosis_date, self.breeding.date)

    def test_diagnosis_today_and_future_expected_birth_are_valid(self):
        pregnancy = PregnancyService.create(self.context, self.make_payload(
            diagnosis_date=self.today, expected_birth=self.today + timedelta(days=1),
        ))
        pregnancy.refresh_from_db()
        self.assertEqual(pregnancy.diagnosis_date, self.today)
        self.assertEqual(pregnancy.expected_birth, self.today + timedelta(days=1))

    def test_future_diagnosis_is_rejected_without_persistence(self):
        self.assert_create_rejected(diagnosis_date=self.today + timedelta(days=1))

    def test_expected_birth_equal_to_diagnosis_is_rejected(self):
        self.assert_create_rejected(diagnosis_date=self.today, expected_birth=self.today)

    def test_inactive_animal_is_rejected(self):
        self.animal.delete()
        self.assert_create_rejected()

    def test_inactive_breeding_is_rejected(self):
        self.breeding.delete()
        self.assert_create_rejected()

    def test_missing_relations_are_rejected(self):
        for field in ("animal_id", "breeding_id"):
            with self.subTest(field=field):
                self.assert_create_rejected(**{field: uuid4()})

    def test_soft_deleted_pregnancy_still_reserves_one_to_one_breeding(self):
        pregnancy = PregnancyService.create(self.context, self.make_payload())
        pregnancy.delete()
        self.assert_create_rejected()

    def test_abort_missing_pregnancy_is_rejected(self):
        self.assert_abort_rejected(uuid4())

    def test_abort_inactive_pregnancy_leaves_record_unchanged(self):
        pregnancy = PregnancyService.create(self.context, self.make_payload())
        pregnancy.delete()
        self.assert_abort_rejected(pregnancy.id)

    def test_abort_foreign_pregnancy_leaves_record_unchanged(self):
        pregnancy = PregnancyService.create(self.context, self.make_payload())
        self.assert_abort_rejected(
            pregnancy.id, RequestContext(organization=self.other_organization),
        )

    def test_abort_non_active_status_leaves_record_unchanged(self):
        pregnancy = PregnancyService.create(self.context, self.make_payload())
        for status in (PregnancyStatus.FINISHED, PregnancyStatus.ABORTED):
            with self.subTest(status=status):
                pregnancy.status = status
                pregnancy.save(update_fields=["status"])
                self.assert_abort_rejected(pregnancy.id)

    def test_model_validation_failure_is_a_domain_error_without_persistence(self):
        with patch.object(Pregnancy, "full_clean", side_effect=ValidationError("Invalid")):
            self.assert_create_rejected()

    def test_abort_model_validation_failure_does_not_persist_status(self):
        pregnancy = PregnancyService.create(self.context, self.make_payload())
        with patch.object(Pregnancy, "full_clean", side_effect=ValidationError("Invalid")):
            self.assert_abort_rejected(pregnancy.id)

    def test_database_failure_is_not_disguised_as_business_error(self):
        with patch.object(Pregnancy, "save", side_effect=OperationalError("Database unavailable")):
            with self.assertRaises(OperationalError):
                PregnancyService.create(self.context, self.make_payload())
        self.assertEqual(Pregnancy._base_manager.count(), 0)


class PregnancyHistoryTests(PregnancyTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = User.objects.create_user(email="pregnancy-history@example.com")
        cls.other_user = User.objects.create_user(email="other-pregnancy-history@example.com")
        for user, organization in (
            (cls.user, cls.organization), (cls.other_user, cls.other_organization),
        ):
            Membership.objects.create(
                user=user, organization=organization,
                role=Membership.Role.VIEWER, is_default=True,
            )

    def saved_pregnancy(self, **overrides):
        organization = overrides.pop("organization", self.organization)
        animal = overrides.pop("animal", self.animal)
        breeding = self.make_breeding(organization, animal, date(2025, 1, 1))
        fields = dict(
            organization=organization, animal=animal, breeding=breeding,
            diagnosis_date=date(2025, 2, 1), expected_birth=date(2025, 10, 1),
        )
        fields.update(overrides)
        return Pregnancy.objects.create(**fields)

    def history(self, animal_id, user=None):
        response = self.client.get(
            f"/api/pregnancies/animal/{animal_id}/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user or self.user)}",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_history_filters_animal_active_records_and_orders_descending(self):
        oldest = self.saved_pregnancy(diagnosis_date=date(2025, 1, 1))
        newest = self.saved_pregnancy(diagnosis_date=date(2025, 3, 1))
        middle = self.saved_pregnancy(diagnosis_date=date(2025, 2, 1))
        deleted = self.saved_pregnancy()
        deleted.delete()
        self.saved_pregnancy(animal=self.second_animal)
        self.saved_pregnancy(organization=self.other_organization, animal=self.other_animal)
        result = self.history(self.animal.id)
        self.assertEqual([item["id"] for item in result], [str(newest.id), str(middle.id), str(oldest.id)])
        self.assertTrue(all(item["animal_id"] == str(self.animal.id) for item in result))
        with self.assertNumQueries(1):
            pregnancies = list(PregnancySelector.history(
                RequestContext(organization=self.organization), self.animal.id,
            ))
        self.assertEqual([item.id for item in pregnancies], [newest.id, middle.id, oldest.id])

    def test_history_explicitly_filters_organization(self):
        own = self.saved_pregnancy()
        # Even inconsistent legacy rows must not cross the tenant boundary.
        foreign = self.saved_pregnancy()
        Pregnancy.objects.filter(pk=foreign.pk).update(organization=self.other_organization)
        self.assertEqual([item["id"] for item in self.history(self.animal.id)], [str(own.id)])

    def test_empty_missing_and_foreign_animals_return_empty_history(self):
        foreign = self.saved_pregnancy(organization=self.other_organization, animal=self.other_animal)
        for animal_id in (self.animal.id, uuid4(), self.other_animal.id):
            with self.subTest(animal_id=animal_id):
                self.assertEqual(self.history(animal_id), [])
        self.assertEqual(
            [item["id"] for item in self.history(self.other_animal.id, self.other_user)],
            [str(foreign.id)],
        )

    def test_inactive_animal_keeps_active_history(self):
        pregnancy = self.saved_pregnancy()
        self.animal.delete()
        self.assertEqual([item["id"] for item in self.history(self.animal.id)], [str(pregnancy.id)])

    def test_history_includes_finished_and_aborted_active_records(self):
        finished = self.saved_pregnancy(status=PregnancyStatus.FINISHED, diagnosis_date=date(2025, 3, 1))
        aborted = self.saved_pregnancy(status=PregnancyStatus.ABORTED)
        self.assertEqual([item["id"] for item in self.history(self.animal.id)], [str(finished.id), str(aborted.id)])

    def test_invalid_uuid_returns_422(self):
        response = self.client.get(
            "/api/pregnancies/animal/not-a-uuid/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}",
        )
        self.assertEqual(response.status_code, 422)

    def test_openapi_history_contract(self):
        from config.api import api

        paths = api.get_openapi_schema()["paths"]
        path = "/api/pregnancies/animal/{animal_id}/history"
        self.assertIn(path, paths)
        self.assertEqual(set(paths[path]), {"get"})
        operation = paths[path]["get"]
        parameter = next(p for p in operation["parameters"] if p["name"] == "animal_id")
        self.assertEqual(parameter["in"], "path")
        self.assertTrue(parameter["required"])
        self.assertEqual(parameter["schema"]["format"], "uuid")
        response = operation["responses"][200]["content"]["application/json"]["schema"]
        self.assertEqual(response["type"], "array")
        self.assertEqual(response["items"]["$ref"], "#/components/schemas/PregnancyResponseSchema")

    def test_create_business_error_uses_existing_api_handler(self):
        Membership.objects.filter(user=self.user).update(role=Membership.Role.OPERATOR)
        payload = self.make_payload(confirmed=False).model_dump(mode="json")
        response = self.client.post(
            "/api/pregnancies/", data=payload, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Solo se puede registrar una gestación confirmada.")
        self.assertEqual(Pregnancy._base_manager.count(), 0)

    def test_abort_missing_or_foreign_pregnancy_returns_same_error(self):
        Membership.objects.filter(user=self.user).update(role=Membership.Role.OPERATOR)
        foreign = self.saved_pregnancy(organization=self.other_organization, animal=self.other_animal)
        before = list(Pregnancy._base_manager.values())
        for pregnancy_id in (uuid4(), foreign.id):
            with self.subTest(pregnancy_id=pregnancy_id):
                response = self.client.post(
                    f"/api/pregnancies/{pregnancy_id}/abort",
                    HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], "La gestación no existe.")
        self.assertEqual(list(Pregnancy._base_manager.values()), before)


class PregnancyServiceCharacterizationTests(PregnancyTestBase):

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

        with self.assertRaises(PregnancyValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_breeding_from_other_organization(self):
        payload = self.make_payload(
            breeding_id=self.other_breeding.pk,
        )

        with self.assertRaises(PregnancyValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_animal_different_from_breeding_animal(self):
        payload = self.make_payload(
            animal_id=self.second_animal.pk,
        )

        with self.assertRaises(PregnancyValidationError):
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

        with self.assertRaises(PregnancyValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                self.make_payload(),
            )

        self.assertEqual(Pregnancy.objects.count(), 1)



    def test_create_rejects_unconfirmed_pregnancy(self):
        payload = self.make_payload(
            confirmed=False,
        )

        with self.assertRaises(PregnancyValidationError):
            PregnancyService.create(
                RequestContext(organization=self.organization),
                payload,
            )

        self.assertEqual(Pregnancy.objects.count(), 0)

    def test_create_rejects_diagnosis_before_breeding_date(self):
        payload = self.make_payload(
            diagnosis_date=date(2024, 12, 1),
        )

        with self.assertRaises(PregnancyValidationError):
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

        with self.assertRaises(PregnancyValidationError):
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

        with self.assertRaises(PregnancyValidationError):
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

        with self.assertRaises(PregnancyValidationError):
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

        with self.assertRaises(PregnancyValidationError):
            PregnancyService.abort(
                RequestContext(organization=self.organization),
                pregnancy.pk,
            )

        pregnancy.refresh_from_db()

        self.assertEqual(
            pregnancy.status,
            PregnancyStatus.ABORTED,
        )
