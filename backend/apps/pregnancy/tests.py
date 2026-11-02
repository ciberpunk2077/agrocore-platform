from datetime import date, datetime, timedelta, timezone as datetime_timezone
import json
import sqlite3
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
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
from apps.common.temporal import get_business_today, TenantTimezoneUnavailable
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

        cls.female = Gender.objects.get(code="F")

        cls.male = Gender.objects.get(code="M")

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


class PregnancyAbortSafeTests(PregnancyTestBase):
    def setUp(self):
        self.user = User.objects.create_user(email="pregnancy-abort-safe@example.com")
        self.membership = Membership.objects.create(user=self.user, organization=self.organization,
            role=Membership.Role.VIEWER, is_default=True)
        self.pregnancy = PregnancyService.create(RequestContext(organization=self.organization), self.make_payload())

    def abort(self, identifier=None):
        return self.client.post(f"/api/pregnancies/{identifier or self.pregnancy.pk}/abort",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def writer(self, role=Membership.Role.ADMIN):
        self.membership.role = role
        self.membership.save(update_fields=["role"])

    def assert_writer(self, role):
        self.writer(role)
        before = Pregnancy._base_manager.get(pk=self.pregnancy.pk)
        response = self.abort()
        self.assertEqual(response.status_code, 200)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.ABORTED)
        self.assertTrue(self.pregnancy.is_active)
        self.assertIsNone(self.pregnancy.deleted_at)
        for field in ("organization_id", "animal_id", "breeding_id", "diagnosis_date", "expected_birth", "confirmed", "notes", "created_at"):
            self.assertEqual(getattr(self.pregnancy, field), getattr(before, field))
        self.assertEqual(response.json(), {
            "id": str(before.pk), "animal_id": str(before.animal_id), "breeding_id": str(before.breeding_id),
            "diagnosis_date": before.diagnosis_date.isoformat(), "expected_birth": before.expected_birth.isoformat(),
            "confirmed": before.confirmed, "notes": before.notes, "status": "ABORTED"})

    def test_owner_can_abort_active(self):
        self.assert_writer(Membership.Role.OWNER)

    def test_admin_can_abort_active(self):
        self.assert_writer(Membership.Role.ADMIN)

    def test_veterinarian_can_abort_active(self):
        self.assert_writer(Membership.Role.VETERINARIAN)

    def test_operator_can_abort_active(self):
        self.assert_writer(Membership.Role.OPERATOR)

    def test_viewer_denied_before_service(self):
        with patch("apps.pregnancy.api.endpoints.PregnancyService.abort") as service:
            self.assertEqual(self.abort().status_code, 403)
            service.assert_not_called()
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.ACTIVE)

    def test_foreign_and_missing_have_same_rejection(self):
        self.writer()
        foreign = PregnancyService.create(RequestContext(organization=self.other_organization), self.make_payload(
            animal_id=self.other_animal.pk, breeding_id=self.other_breeding.pk))
        response = self.abort(foreign.pk)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), self.abort(uuid4()).json())
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, PregnancyStatus.ACTIVE)

    def test_missing_rejected(self):
        self.writer()
        self.assertEqual(self.abort(uuid4()).status_code, 400)

    def test_soft_deleted_rejected(self):
        self.writer()
        self.pregnancy.delete()
        self.assertEqual(self.abort().status_code, 400)

    def test_already_aborted_rejected_without_change(self):
        self.writer()
        self.assertEqual(self.abort().status_code, 200)
        before = list(Pregnancy._base_manager.values())
        self.assertEqual(self.abort().status_code, 400)
        self.assertEqual(list(Pregnancy._base_manager.values()), before)

    def test_finished_rejected_without_overwrite(self):
        self.writer()
        self.pregnancy.status = PregnancyStatus.FINISHED
        self.pregnancy.save(update_fields=["status"])
        self.assertEqual(self.abort().status_code, 400)
        self.pregnancy.refresh_from_db()
        self.assertEqual(self.pregnancy.status, PregnancyStatus.FINISHED)

    def test_inactive_relations_do_not_prevent_historical_abort(self):
        self.animal.delete()
        self.breeding.delete()
        self.assert_writer(Membership.Role.ADMIN)

    def test_abort_does_not_require_valid_business_timezone(self):
        Organization.objects.filter(pk=self.organization.pk).update(timezone="Invalid/Zone")
        self.assert_writer(Membership.Role.ADMIN)


class PregnancyDetailTests(PregnancyTestBase):
    def setUp(self):
        self.user = User.objects.create_user(email="pregnancy-detail@example.com")
        self.membership = Membership.objects.create(user=self.user, organization=self.organization,
            role=Membership.Role.VIEWER, is_default=True)
        self.pregnancy = PregnancyService.create(RequestContext(organization=self.organization), self.make_payload())

    def detail(self, identifier=None):
        return self.client.get(f"/api/pregnancies/{identifier or self.pregnancy.pk}",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def assert_role(self, role):
        self.membership.role = role
        self.membership.save(update_fields=["role"])
        self.assertEqual(self.detail().status_code, 200)

    def test_owner_detail(self):
        self.assert_role(Membership.Role.OWNER)

    def test_admin_detail(self):
        self.assert_role(Membership.Role.ADMIN)

    def test_veterinarian_detail(self):
        self.assert_role(Membership.Role.VETERINARIAN)

    def test_operator_detail(self):
        self.assert_role(Membership.Role.OPERATOR)

    def test_viewer_detail(self):
        self.assert_role(Membership.Role.VIEWER)

    def test_foreign_tenant_returns_same_404_as_missing(self):
        foreign = PregnancyService.create(RequestContext(organization=self.other_organization), self.make_payload(
            animal_id=self.other_animal.pk, breeding_id=self.other_breeding.pk))
        response = self.detail(foreign.pk)
        self.assertEqual(response.status_code, 404)
        missing = self.detail(uuid4())
        self.assertEqual(response.json(), missing.json())

    def test_missing_returns_404(self):
        self.assertEqual(self.detail(uuid4()).status_code, 404)

    def test_soft_deleted_returns_404(self):
        self.pregnancy.delete()
        self.assertEqual(self.detail().status_code, 404)

    def test_exact_response_schema_and_relation_identities(self):
        response = self.detail()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "id": str(self.pregnancy.pk), "animal_id": str(self.animal.pk), "breeding_id": str(self.breeding.pk),
            "diagnosis_date": "2025-02-01", "expected_birth": "2025-10-01", "confirmed": True,
            "notes": "Pregnancy characterization test", "status": "ACTIVE"})

    def test_inactive_relations_remain_readable(self):
        self.animal.delete()
        self.breeding.delete()
        self.assertEqual(self.detail().status_code, 200)
        self.assertEqual(self.detail().json()["breeding_id"], str(self.breeding.pk))

    def test_malformed_uuid_returns_422(self):
        self.assertEqual(self.detail("invalid").status_code, 422)

    def test_missing_auth_returns_401(self):
        self.assertEqual(self.client.get(f"/api/pregnancies/{self.pregnancy.pk}").status_code, 401)


class PregnancyBusinessDateTests(PregnancyTestBase):
    def setUp(self):
        self.context = RequestContext(organization=self.organization)

    def at(self, value):
        return patch("apps.common.temporal.timezone.now", return_value=datetime.fromisoformat(value).astimezone(datetime_timezone.utc))

    def test_mexico_allows_diagnosis_on_business_today_after_utc_midnight(self):
        with self.at("2026-10-06T00:30:00+00:00"):
            self.assertEqual(get_business_today(self.context), date(2026, 10, 5))
            pregnancy = PregnancyService.create(self.context, self.make_payload(
                diagnosis_date=date(2026, 10, 5), expected_birth=date(2027, 1, 1)))
        self.assertEqual(pregnancy.diagnosis_date, date(2026, 10, 5))

    def test_mexico_rejects_utc_day_that_is_future_for_tenant(self):
        with self.at("2026-10-06T00:30:00+00:00"):
            with self.assertRaisesMessage(PregnancyValidationError, "La fecha de diagnóstico no puede ser futura."):
                PregnancyService.create(self.context, self.make_payload(
                    diagnosis_date=date(2026, 10, 6), expected_birth=date(2027, 1, 1)))
        self.assertFalse(Pregnancy._base_manager.exists())

    def test_before_mexico_midnight_rejects_next_diagnosis_day(self):
        with self.at("2026-10-06T05:59:59+00:00"):
            self.assertEqual(get_business_today(self.context), date(2026, 10, 5))
            with self.assertRaises(PregnancyValidationError):
                PregnancyService.create(self.context, self.make_payload(
                    diagnosis_date=date(2026, 10, 6), expected_birth=date(2027, 1, 1)))

    def test_at_mexico_midnight_allows_new_diagnosis_day(self):
        with self.at("2026-10-06T06:00:00+00:00"):
            self.assertEqual(get_business_today(self.context), date(2026, 10, 6))
            pregnancy = PregnancyService.create(self.context, self.make_payload(
                diagnosis_date=date(2026, 10, 6), expected_birth=date(2027, 1, 1)))
        self.assertEqual(pregnancy.diagnosis_date, date(2026, 10, 6))

    def test_utc_organization_uses_its_own_business_date(self):
        self.organization.timezone = "UTC"
        with self.at("2026-10-06T00:30:00+00:00"):
            self.assertEqual(get_business_today(self.context), date(2026, 10, 6))
            PregnancyService.create(self.context, self.make_payload(
                diagnosis_date=date(2026, 10, 6), expected_birth=date(2027, 1, 1)))

    def test_invalid_organization_timezone_fails_closed(self):
        self.organization.timezone = "Invalid/Zone"
        with self.at("2026-10-06T00:30:00+00:00"):
            with self.assertRaises(TenantTimezoneUnavailable):
                PregnancyService.create(self.context, self.make_payload())
        self.assertFalse(Pregnancy._base_manager.exists())

    def test_before_utc_midnight_keeps_mexico_business_day(self):
        with self.at("2026-10-05T23:59:59+00:00"):
            self.assertEqual(get_business_today(self.context), date(2026, 10, 5))
            PregnancyService.create(self.context, self.make_payload(
                diagnosis_date=date(2026, 10, 5), expected_birth=date(2027, 1, 1)))

    def test_read_is_allowed_for_every_membership_role(self):
        user = User.objects.create_user(email="pregnancy-read-roles@example.com")
        membership = Membership.objects.create(user=user, organization=self.organization,
            role=Membership.Role.VIEWER, is_default=True)
        with self.at("2026-10-06T00:30:00+00:00"):
            pregnancy = PregnancyService.create(self.context, self.make_payload())
        for role in Membership.Role.values:
            with self.subTest(role=role):
                membership.role = role
                membership.save(update_fields=["role"])
                headers = {"HTTP_AUTHORIZATION": f"Bearer {create_access_token(user)}"}
                response = self.client.get(f"/api/pregnancies/animal/{self.animal.pk}/history", **headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()[0]["id"], str(pregnancy.pk))

    def test_create_writer_roles_and_viewer_denial_preserve_contract(self):
        user = User.objects.create_user(email="pregnancy-create-roles@example.com")
        membership = Membership.objects.create(user=user, organization=self.organization,
            role=Membership.Role.VIEWER, is_default=True)
        for role in Membership.Role.values:
            with self.subTest(role=role):
                membership.role = role
                membership.save(update_fields=["role"])
                animal = self.make_animal(self.organization, self.female, f"PREG_ROLE_{role}")
                breeding = self.make_breeding(self.organization, animal, date(2025, 1, 1))
                payload = self.make_payload(animal_id=animal.pk, breeding_id=breeding.pk)
                before = Pregnancy._base_manager.count()
                with self.at("2026-10-06T00:30:00+00:00"):
                    response = self.client.post("/api/pregnancies/", data=payload.model_dump_json(),
                        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
                self.assertEqual(response.status_code, 403 if role == Membership.Role.VIEWER else 200)
                self.assertEqual(Pregnancy._base_manager.count(), before + (role != Membership.Role.VIEWER))


class PregnancyActiveIntegrityTests(PregnancyTestBase):
    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.next_breeding = self.make_breeding(
            self.organization, self.animal, date(2025, 1, 2),
        )

    def create_first(self):
        return PregnancyService.create(self.context, self.make_payload())

    def create_next(self):
        return PregnancyService.create(
            self.context, self.make_payload(breeding_id=self.next_breeding.pk),
        )

    def test_second_active_for_same_animal_is_rejected(self):
        self.create_first()
        with self.assertRaisesMessage(PregnancyValidationError, "El animal ya tiene una gestación activa."):
            self.create_next()
        self.assertEqual(Pregnancy.objects.filter(animal=self.animal, status="ACTIVE").count(), 1)

    def test_finished_allows_new_active(self):
        first = self.create_first()
        first.status = PregnancyStatus.FINISHED
        first.save(update_fields=["status"])
        self.assertEqual(self.create_next().status, PregnancyStatus.ACTIVE)

    def test_aborted_allows_new_active(self):
        first = self.create_first()
        PregnancyService.abort(self.context, first.pk)
        self.assertEqual(self.create_next().status, PregnancyStatus.ACTIVE)

    def test_soft_deleted_active_allows_new_active(self):
        self.create_first().delete()
        self.assertEqual(self.create_next().status, PregnancyStatus.ACTIVE)

    def test_database_rejects_second_active_even_with_foreign_organization(self):
        self.create_first()
        with self.assertRaises(IntegrityError) as caught:
            with transaction.atomic():
                Pregnancy.objects.create(
                    organization=self.other_organization, animal=self.animal,
                    breeding=self.next_breeding, diagnosis_date=date(2025, 2, 1),
                    expected_birth=date(2025, 10, 1),
                )
        self.assertIn("pregnancies.animal_id", str(caught.exception))
        self.assertEqual(Pregnancy._base_manager.count(), 1)

    def test_create_real_database_collision_is_translated(self):
        self.create_first()
        # Bypass checks, not the INSERT or the database error.
        with patch.object(PregnancyService, "_validate_relations"), patch.object(Pregnancy, "full_clean"):
            with self.assertRaises(PregnancyValidationError) as caught:
                self.create_next()
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.assertEqual(str(caught.exception.__cause__.__cause__), "UNIQUE constraint failed: pregnancies.animal_id")
        self.assertEqual(Pregnancy._base_manager.count(), 1)

    def test_unrelated_integrity_error_propagates(self):
        self.create_first()
        # A real NOT NULL violation remains unrelated to business uniqueness.
        real_save = Pregnancy.save
        def invalid_save(instance, *args, **kwargs):
            instance.notes = None
            instance.confirmed = None
            return real_save(instance, *args, **kwargs)
        with patch.object(PregnancyService, "_validate_relations"), patch.object(Pregnancy, "full_clean"), patch.object(Pregnancy, "save", invalid_save):
            with self.assertRaises(IntegrityError) as caught:
                self.create_next()
        self.assertIn("NOT NULL constraint failed: pregnancies.confirmed", str(caught.exception))
        self.assertEqual(Pregnancy._base_manager.count(), 1)

    def test_full_clean_active_constraint_is_translated_specifically(self):
        self.create_first()
        with patch.object(PregnancyService, "_validate_relations"):
            with self.assertRaisesMessage(PregnancyValidationError, PregnancyService._active_message) as caught:
                self.create_next()
        self.assertIsInstance(caught.exception.__cause__, ValidationError)
        self.assertEqual(Pregnancy._base_manager.count(), 1)

    def test_http_second_active_returns_400(self):
        self.create_first()
        user = User.objects.create_user(email="h1-active@example.com")
        Membership.objects.create(
            user=user, organization=self.organization,
            role=Membership.Role.OPERATOR, is_default=True,
        )
        payload = json.loads(self.make_payload(breeding_id=self.next_breeding.pk).model_dump_json())
        response = self.client.post(
            "/api/pregnancies/", data=json.dumps(payload), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "El animal ya tiene una gestación activa."})
        self.assertEqual(Pregnancy.objects.filter(animal=self.animal, status="ACTIVE").count(), 1)

    def test_restore_conflict_is_rejected_by_database(self):
        first = self.create_first()
        first.delete()
        second = self.create_next()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                first.restore()
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertIsNotNone(first.deleted_at)
        self.assertEqual(Pregnancy.objects.get(animal=self.animal).pk, second.pk)


class PregnancyServiceValidationTests(PregnancyTestBase):
    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.today = date(2025, 3, 1)
        clock = patch(
            "apps.pregnancy.services.pregnancy_service.get_business_today",
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
        oldest = self.saved_pregnancy(diagnosis_date=date(2025, 1, 1), status=PregnancyStatus.FINISHED)
        newest = self.saved_pregnancy(diagnosis_date=date(2025, 3, 1), status=PregnancyStatus.FINISHED)
        middle = self.saved_pregnancy(diagnosis_date=date(2025, 2, 1), status=PregnancyStatus.ABORTED)
        deleted = self.saved_pregnancy(status=PregnancyStatus.FINISHED)
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
        foreign = self.saved_pregnancy(status=PregnancyStatus.FINISHED)
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


class PregnancyBreedingCollisionTests(PregnancyTestBase):
    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        user = User.objects.create_user(email="h5f-pregnancy@example.com")
        Membership.objects.create(user=user, organization=self.organization,
                                  role=Membership.Role.OPERATOR, is_default=True)
        self.authorization = f"Bearer {create_access_token(user)}"
        self.first = PregnancyService.create(self.context, self.make_payload())
        # Keep the same legitimate animal/breeding relation; isolate OneToOne from H1.
        PregnancyService.abort(self.context, self.first.pk)
        self.first.refresh_from_db()
        self.before = list(Pregnancy._base_manager.order_by("pk").values())

    def request(self):
        return self.client.post("/api/pregnancies/", data=json.loads(self.make_payload().model_dump_json()),
            content_type="application/json", HTTP_AUTHORIZATION=self.authorization)

    def assert_preserved(self):
        self.first.refresh_from_db()
        self.assertEqual(list(Pregnancy._base_manager.order_by("pk").values()), self.before)
        self.assertEqual(Pregnancy._base_manager.count(), 1)
        self.assertFalse(transaction.get_connection().needs_rollback)

    def test_http_sequential_breeding_reuse_remains_400(self):
        self.assertEqual(self.request().status_code, 400)
        self.assert_preserved()

    def test_http_soft_deleted_pregnancy_reserves_breeding(self):
        self.first.delete()
        self.first.refresh_from_db()
        self.assertFalse(self.first.is_active)
        self.assertIsNotNone(self.first.deleted_at)
        self.before = list(Pregnancy._base_manager.order_by("pk").values())
        self.assertEqual(self.request().status_code, 400)
        self.assert_preserved()

    def test_real_breeding_collision_translates_preserves_cause_and_connection(self):
        with patch.object(PregnancyService, "_validate_relations"), patch.object(Pregnancy, "full_clean"):
            with self.assertRaises(PregnancyValidationError) as caught:
                PregnancyService.create(self.context, self.make_payload())
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.assertIsInstance(caught.exception.__cause__.__cause__, sqlite3.IntegrityError)
        self.assertEqual(str(caught.exception), PregnancyService._breeding_message)
        self.assertEqual(str(caught.exception.__cause__.__cause__), "UNIQUE constraint failed: pregnancies.breeding_id")
        self.assert_preserved()

    def test_http_real_breeding_collision_returns_400(self):
        with patch.object(PregnancyService, "_validate_relations"), patch.object(Pregnancy, "full_clean"):
            self.assertEqual(self.request().status_code, 400)
        self.assert_preserved()

    def test_nonexact_or_unverified_diagnostics_propagate_original(self):
        import sqlite3
        from types import SimpleNamespace
        causes = [
            sqlite3.IntegrityError("UNIQUE constraint failed: pregnancies.breeding_id_extra"),
            sqlite3.IntegrityError("UNIQUE constraint failed: pregnancies.breeding_id "),
            sqlite3.IntegrityError("UNIQUE constraint failed: pregnancies.breeding_id, pregnancies.organization_id"),
            Exception("UNIQUE constraint failed: pregnancies.breeding_id"),
        ]
        for name in ("other_constraint", "pregnancies_breeding_id_key"):
            cause = Exception("PostgreSQL unique violation")
            cause.diag = SimpleNamespace(constraint_name=name)
            causes.append(cause)
        for cause in causes:
            with self.subTest(cause=str(cause), diag=getattr(cause, "diag", None)):
                error = IntegrityError("unique violation")
                error.__cause__ = cause
                with patch.object(PregnancyService, "_validate_relations"), patch.object(Pregnancy, "full_clean"), patch.object(Pregnancy, "save", side_effect=error):
                    with self.assertRaises(IntegrityError) as caught:
                        self.request()
                self.assertIs(caught.exception, error)
                self.assert_preserved()
