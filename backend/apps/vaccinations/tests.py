from datetime import date, datetime, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.animals.models import Animal
from apps.catalogs.models import AnimalStatus, Breed, Gender, Species
from apps.common.context.context import RequestContext
from apps.common.exceptions.vaccination import VaccinationValidationError
from apps.organizations.models import Organization
from apps.vaccinations.api.schemas import VaccinationCreateSchema, VaccinationUpdateSchema
from apps.vaccinations.models import Vaccination
from apps.vaccinations.services import VaccinationService


class VaccinationCreateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="VAC", name="Vaccinations")
        cls.other_organization = Organization.objects.create(code="OTHER", name="Other")
        species = Species.objects.create(code="VAC", name="Bovino")
        breed = Breed.objects.create(code="VAC", name="Raza", species=species)
        gender = Gender.objects.create(code="VAC", name="Vaccination create fixture gender")
        status = AnimalStatus.objects.create(code="VAC", name="Vaccination create fixture status")
        animal_fields = dict(species=species, breed=breed, gender=gender, status=status)
        cls.animal = Animal.objects.create(
            organization=cls.organization, internal_id="VAC-1", **animal_fields,
        )
        cls.foreign_animal = Animal.objects.create(
            organization=cls.other_organization, internal_id="VAC-2", **animal_fields,
        )
        cls.inactive_animal = Animal.objects.create(
            organization=cls.organization, internal_id="VAC-3", is_active=False,
            **animal_fields,
        )

    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.today = timezone.localdate(timezone=ZoneInfo("America/Mexico_City"))

    def payload(self, **overrides):
        data = {
            "animal_id": self.animal.id,
            "vaccine_name": "Vacuna de prueba",
            "application_date": self.today,
            "dose": Decimal("1.50"),
            "batch": "",
            "veterinarian": "",
            "notes": "",
        }
        data.update(overrides)
        return VaccinationCreateSchema(**data)

    def assert_rejected_without_persistence(self, payload, message):
        before = set(Vaccination._base_manager.values_list("id", flat=True))
        with self.assertRaisesMessage(VaccinationValidationError, message):
            VaccinationService.create(self.context, payload)
        self.assertEqual(
            set(Vaccination._base_manager.values_list("id", flat=True)), before,
        )

    def test_valid_vaccination_is_created(self):
        vaccination = VaccinationService.create(self.context, self.payload())
        vaccination.refresh_from_db()
        self.assertEqual(Vaccination.objects.count(), 1)
        self.assertEqual(vaccination.organization_id, self.organization.id)
        self.assertEqual(vaccination.animal_id, self.animal.id)
        self.assertEqual(vaccination.application_date, self.today)
        self.assertEqual(vaccination.dose, Decimal("1.50"))
        self.assertIsNone(vaccination.next_application_date)

    def test_future_application_date_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(application_date=self.today + timedelta(days=1)),
            "La fecha de aplicación no puede ser futura.",
        )

    def test_zero_dose_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(dose=Decimal("0")), "La dosis debe ser mayor que cero.",
        )

    def test_negative_dose_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(dose=Decimal("-1")), "La dosis debe ser mayor que cero.",
        )

    def test_same_next_application_date_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(next_application_date=self.today),
            "La próxima fecha de aplicación debe ser posterior a la fecha de aplicación.",
        )

    def test_earlier_next_application_date_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(next_application_date=self.today - timedelta(days=1)),
            "La próxima fecha de aplicación debe ser posterior a la fecha de aplicación.",
        )

    def test_later_next_application_date_is_accepted(self):
        next_date = self.today + timedelta(days=1)
        vaccination = VaccinationService.create(
            self.context, self.payload(next_application_date=next_date),
        )
        vaccination.refresh_from_db()
        self.assertEqual(vaccination.next_application_date, next_date)
        self.assertEqual(Vaccination.objects.count(), 1)

    def test_animal_from_another_organization_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(animal_id=self.foreign_animal.id), "El animal no existe.",
        )

    def test_inactive_animal_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(animal_id=self.inactive_animal.id), "El animal no existe.",
        )

    def test_missing_animal_is_rejected(self):
        self.assert_rejected_without_persistence(
            self.payload(animal_id=uuid4()), "El animal no existe.",
        )

    def test_create_optional_text_fields(self):
        cases = (
            ("omitted", {}),
            ("null", dict(batch=None, veterinarian=None, notes=None)),
            ("text", dict(batch=" Lote 123 ", veterinarian="Dra. Pérez", notes="Nota\nsegunda línea")),
            ("empty", dict(batch="", veterinarian="", notes="")),
        )
        for label, fields in cases:
            with self.subTest(case=label):
                payload = VaccinationCreateSchema(
                    animal_id=self.animal.id,
                    vaccine_name="Vacuna de prueba",
                    application_date=self.today,
                    dose=Decimal("1.50"),
                    next_application_date=None,
                    **fields,
                )
                vaccination = VaccinationService.create(self.context, payload)
                vaccination.refresh_from_db()
                for field in ("batch", "veterinarian", "notes"):
                    self.assertEqual(getattr(vaccination, field), fields.get(field) or "")
                self.assertIsNone(vaccination.next_application_date)

    def test_update_optional_text_fields(self):
        cases = (
            ("omitted", {}),
            ("null", dict(batch=None, veterinarian=None, notes=None)),
            ("text", dict(batch=" Lote 456 ", veterinarian="Dr. López", notes="Nueva\nnota")),
            ("empty", dict(batch="", veterinarian="", notes="")),
        )
        for label, fields in cases:
            with self.subTest(case=label):
                vaccination = VaccinationService.create(
                    self.context,
                    self.payload(
                        batch="Original", veterinarian="Original", notes="Original",
                        next_application_date=self.today + timedelta(days=1),
                    ),
                )
                payload = VaccinationUpdateSchema(
                    animal_id=self.animal.id,
                    vaccine_name="Vacuna de prueba",
                    application_date=self.today,
                    dose=Decimal("1.50"),
                    next_application_date=None,
                    **fields,
                )
                VaccinationService.update(vaccination, self.context, payload)
                vaccination.refresh_from_db()
                for field in ("batch", "veterinarian", "notes"):
                    self.assertEqual(getattr(vaccination, field), fields.get(field) or "")
                self.assertIsNone(vaccination.next_application_date)


class VaccinationHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="HIST", name="History")
        cls.other_organization = Organization.objects.create(code="OTHER", name="Other")
        cls.user = User.objects.create_user(email="history@example.com")
        cls.other_user = User.objects.create_user(email="other-history@example.com")
        for user, organization in (
            (cls.user, cls.organization), (cls.other_user, cls.other_organization),
        ):
            Membership.objects.create(
                user=user, organization=organization,
                role=Membership.Role.VIEWER, is_default=True,
            )
        species = Species.objects.create(code="HIST", name="Bovino")
        breed = Breed.objects.create(code="HIST", name="Raza", species=species)
        gender = Gender.objects.create(code="HIST", name="Vaccination history fixture gender")
        status = AnimalStatus.objects.create(code="HIST", name="Vaccination history fixture status")
        fields = dict(species=species, breed=breed, gender=gender, status=status)
        cls.animal = Animal.objects.create(
            organization=cls.organization, internal_id="HIST-1", **fields,
        )
        cls.other_animal = Animal.objects.create(
            organization=cls.organization, internal_id="HIST-2", **fields,
        )
        cls.foreign_animal = Animal.objects.create(
            organization=cls.other_organization, internal_id="HIST-3", **fields,
        )

    def vaccination(self, animal, days_ago=0):
        return Vaccination.objects.create(
            organization=animal.organization, animal=animal,
            vaccine_name="Vacuna de prueba", dose=Decimal("1.50"),
            application_date=timezone.localdate() - timedelta(days=days_ago),
        )

    def history(self, animal_id, user=None):
        response = self.client.get(
            f"/api/vaccinations/animal/{animal_id}/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user or self.user)}",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_history_filters_records_and_orders_by_application_date(self):
        oldest = self.vaccination(self.animal, days_ago=10)
        newest = self.vaccination(self.animal)
        middle = self.vaccination(self.animal, days_ago=5)
        deleted = self.vaccination(self.animal)
        deleted.delete()
        self.vaccination(self.other_animal)
        self.vaccination(self.foreign_animal)

        result = self.history(self.animal.id)
        self.assertEqual([item["id"] for item in result], [
            str(newest.id), str(middle.id), str(oldest.id),
        ])
        for item in result:
            self.assertEqual(item["animal_id"], str(self.animal.id))
            self.assertTrue(item["is_active"])

    def test_empty_missing_and_foreign_animals_return_empty_history(self):
        foreign = self.vaccination(self.foreign_animal)
        for animal_id in (self.animal.id, uuid4(), self.foreign_animal.id):
            with self.subTest(animal_id=animal_id):
                self.assertEqual(self.history(animal_id), [])
        result = self.history(self.foreign_animal.id, user=self.other_user)
        self.assertEqual([item["id"] for item in result], [str(foreign.id)])

    def test_inactive_animal_keeps_its_active_history(self):
        vaccination = self.vaccination(self.animal)
        self.animal.delete()
        result = self.history(self.animal.id)
        self.assertEqual([item["id"] for item in result], [str(vaccination.id)])

    def test_history_rejects_invalid_uuid(self):
        response = self.client.get(
            "/api/vaccinations/animal/not-a-uuid/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}",
        )
        self.assertEqual(response.status_code, 422)

    def test_history_openapi_contract(self):
        from config.api import api

        schema = api.get_openapi_schema()
        path = "/api/vaccinations/animal/{animal_id}/history"
        self.assertIn(path, schema["paths"])
        self.assertEqual(set(schema["paths"][path]), {"get"})
        operation = schema["paths"][path]["get"]
        parameter = next(p for p in operation["parameters"] if p["name"] == "animal_id")
        self.assertEqual(parameter["in"], "path")
        self.assertTrue(parameter["required"])
        self.assertEqual(parameter["schema"]["format"], "uuid")
        response = operation["responses"][200]["content"]["application/json"]["schema"]
        self.assertEqual(response["type"], "array")
        self.assertEqual(response["items"]["$ref"], "#/components/schemas/VaccinationResponseSchema")


class VaccinationErrorTranslationHTTPTests(TestCase):
    setUpTestData = classmethod(VaccinationCreateTests.setUpTestData.__func__)

    def setUp(self):
        VaccinationCreateTests.setUp(self)
        user = User.objects.create_user(email="h5d@example.com")
        Membership.objects.create(user=user, organization=self.organization,
                                  role=Membership.Role.OPERATOR, is_default=True)
        self.authorization = f"Bearer {create_access_token(user)}"

    def data(self, **changes):
        result = dict(animal_id=str(self.animal.pk), vaccine_name="Original",
                      application_date=self.today.isoformat(), dose="1.50",
                      batch="Batch", veterinarian="Vet", notes="Notes")
        result.update(changes)
        return result

    def request(self, method="post", vaccination=None, data=None, **changes):
        path = "/api/vaccinations/" if method == "post" else f"/api/vaccinations/{vaccination.pk}"
        return getattr(self.client, method)(path, data=self.data(**changes) if data is None else data,
            content_type="application/json", HTTP_AUTHORIZATION=self.authorization)

    def original(self):
        return VaccinationService.create(self.context, VaccinationCreateSchema(**self.data()))

    invalid_fields = (
        dict(vaccine_name=""), dict(vaccine_name="x" * 151), dict(batch="x" * 51),
        dict(veterinarian="x" * 151), dict(dose="1000000.00"),
        dict(dose="1.001"), dict(dose="1000000"),
    )

    def test_http_post_model_field_errors_return_400(self):
        for changes in self.invalid_fields:
            with self.subTest(changes=changes):
                response = self.request(**changes)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()["detail"])
                self.assertEqual(Vaccination._base_manager.count(), 0)

    def test_http_put_model_field_errors_return_400_and_preserve_all_fields(self):
        vaccination = self.original()
        before = Vaccination._base_manager.filter(pk=vaccination.pk).values().get()
        for changes in self.invalid_fields:
            with self.subTest(changes=changes):
                data = self.data(notes="Changed", application_date=(self.today - timedelta(days=1)).isoformat())
                data.update(changes)
                response = self.request("put", vaccination, data=data)
                self.assertEqual(response.status_code, 400)
                vaccination.refresh_from_db()
                self.assertEqual(Vaccination._base_manager.filter(pk=vaccination.pk).values().get(), before)

    def test_http_existing_temporal_and_dose_rules_return_400(self):
        vaccination = self.original()
        before = Vaccination._base_manager.filter(pk=vaccination.pk).values().get()
        cases = (dict(dose="0"), dict(dose="-1"),
                 dict(application_date=(self.today + timedelta(days=1)).isoformat()),
                 dict(next_application_date=self.today.isoformat()),
                 dict(next_application_date=(self.today - timedelta(days=1)).isoformat()))
        for method in ("post", "put"):
            for changes in cases:
                with self.subTest(method=method, changes=changes):
                    self.assertEqual(self.request(method, vaccination, **changes).status_code, 400)
                    vaccination.refresh_from_db()
                    self.assertEqual(Vaccination._base_manager.filter(pk=vaccination.pk).values().get(), before)
                    self.assertEqual(Vaccination._base_manager.count(), 1)

    def test_http_date_before_birth_is_rejected(self):
        self.animal.birth_date = self.today
        self.animal.save()
        vaccination = self.original()
        for method in ("post", "put"):
            with self.subTest(method=method):
                self.assertEqual(self.request(method, vaccination,
                    application_date=(self.today - timedelta(days=1)).isoformat()).status_code, 400)

    def test_http_optional_texts_omitted_and_null_remain_normalized(self):
        vaccination = self.original()
        for method in ("post", "put"):
            for omitted in (True, False):
                with self.subTest(method=method, omitted=omitted):
                    data = self.data()
                    for field in ("batch", "veterinarian", "notes"):
                        if omitted:
                            del data[field]
                        else:
                            data[field] = None
                    response = self.request(method, vaccination, data=data)
                    self.assertEqual(response.status_code, 200)
                    saved = Vaccination._base_manager.get(pk=response.json()["id"])
                    for field in ("batch", "veterinarian", "notes"):
                        self.assertEqual(getattr(saved, field), "")

    def assert_validation_propagates(self, errors):
        vaccination = self.original()
        before = list(Vaccination._base_manager.values())
        for method in ("post", "put"):
            with self.subTest(method=method, errors=errors):
                error = ValidationError(errors)
                with patch.object(Vaccination, "full_clean", side_effect=error):
                    with self.assertRaises(ValidationError) as caught:
                        self.request(method, vaccination)
                self.assertIs(caught.exception, error)
                vaccination.refresh_from_db()
                self.assertEqual(list(Vaccination._base_manager.values()), before)

    def test_http_unknown_validation_error_propagates_original(self):
        self.assert_validation_propagates({"notes": ValidationError("unknown", code="unexpected")})

    def test_http_mixed_validation_error_propagates_original(self):
        self.assert_validation_propagates({
            "vaccine_name": ValidationError("blank", code="blank"),
            "notes": ValidationError("unknown", code="unexpected"),
        })

    def test_http_known_code_on_internal_field_propagates(self):
        self.assert_validation_propagates({"organization": ValidationError("internal", code="max_length")})

    def test_http_unstructured_validation_error_propagates(self):
        self.assert_validation_propagates("unexpected internal error")

    def test_http_unrelated_integrity_error_propagates_original(self):
        vaccination = self.original()
        before = list(Vaccination._base_manager.values())
        for method in ("post", "put"):
            with self.subTest(method=method):
                error = IntegrityError("unrelated database failure")
                with patch.object(Vaccination, "save", side_effect=error):
                    with self.assertRaises(IntegrityError) as caught:
                        self.request(method, vaccination)
                self.assertIs(caught.exception, error)
                vaccination.refresh_from_db()
                self.assertEqual(list(Vaccination._base_manager.values()), before)

    def test_http_invalid_schema_returns_422(self):
        vaccination = self.original()
        for method in ("post", "put"):
            for changes in (dict(dose="not-decimal"), dict(animal_id="not-uuid"),
                            dict(application_date="not-date"), dict(next_application_date="not-date")):
                with self.subTest(method=method, changes=changes):
                    self.assertEqual(self.request(method, vaccination, **changes).status_code, 422)

    def test_http_inaccessible_resources_return_404(self):
        foreign = Vaccination.objects.create(organization=self.other_organization,
            animal=self.foreign_animal, vaccine_name="Foreign", application_date=self.today, dose=Decimal("1.50"))
        inactive = self.original()
        inactive.delete()
        for pk in (uuid4(), foreign.pk, inactive.pk):
            for method in ("get", "put"):
                with self.subTest(method=method, pk=pk):
                    response = getattr(self.client, method)(f"/api/vaccinations/{pk}",
                        data=self.data(), content_type="application/json", HTTP_AUTHORIZATION=self.authorization)
                    self.assertEqual(response.status_code, 404)

    def test_http_unavailable_animal_keeps_existing_400(self):
        vaccination = self.original()
        for method in ("post", "put"):
            for pk in (uuid4(), self.foreign_animal.pk, self.inactive_animal.pk):
                with self.subTest(method=method, animal=pk):
                    self.assertEqual(self.request(method, vaccination, animal_id=str(pk)).status_code, 400)


class VaccinationCivilDateHTTPTests(TestCase):
    setUpTestData = classmethod(VaccinationCreateTests.setUpTestData.__func__)
    data = VaccinationErrorTranslationHTTPTests.data
    request = VaccinationErrorTranslationHTTPTests.request
    original = VaccinationErrorTranslationHTTPTests.original

    def setUp(self):
        self.clock = patch("django.utils.timezone.now", return_value=
            datetime(2026, 10, 5, 1, tzinfo=datetime_timezone.utc))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        VaccinationErrorTranslationHTTPTests.setUp(self)
        self.today = date(2026, 10, 4)

    def test_create_accepts_mexico_today_when_utc_is_tomorrow(self):
        response = self.request(application_date="2026-10-04")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vaccination._base_manager.get().application_date, date(2026, 10, 4))

    def test_create_rejects_utc_today_without_persistence(self):
        response = self.request(application_date="2026-10-05")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "La fecha de aplicación no puede ser futura."})
        self.assertEqual(Vaccination._base_manager.count(), 0)

    def test_update_rejects_utc_today_and_preserves_every_field(self):
        vaccination = self.original()
        before = Vaccination._base_manager.filter(pk=vaccination.pk).values().get()
        response = self.request("put", vaccination, application_date="2026-10-05",
                                vaccine_name="Changed", dose="2.50", batch="Changed",
                                veterinarian="Changed", notes="Changed")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vaccination._base_manager.filter(pk=vaccination.pk).values().get(), before)

    def test_create_accepts_new_day_at_mexico_midnight(self):
        with patch("django.utils.timezone.now", return_value=
                   datetime(2026, 10, 5, 6, tzinfo=datetime_timezone.utc)):
            self.assertEqual(self.request(application_date="2026-10-05").status_code, 200)


class VaccinationDeleteHTTPTests(TestCase):
    setUpTestData = classmethod(VaccinationCreateTests.setUpTestData.__func__)

    def setUp(self):
        self.user = User.objects.create_user(email="vaccination-delete@example.com")
        self.membership = Membership.objects.create(user=self.user, organization=self.organization,
            role=Membership.Role.OPERATOR, is_default=True)
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {create_access_token(self.user)}"}
        self.record = Vaccination.objects.create(organization=self.organization, animal=self.animal,
            vaccine_name="Delete fixture", application_date=date(2026, 1, 1), dose=Decimal("2.00"),
            batch=" Batch ", veterinarian="Vet", notes="Notes")

    def rows(self):
        return list(Vaccination._base_manager.order_by("id").values())

    def delete(self, identifier=None, headers=None):
        return self.client.delete(f"/api/vaccinations/{identifier or self.record.pk}",
            **(self.headers if headers is None else headers))

    def rejected(self, status, identifier=None, headers=None):
        before = self.rows()
        response = self.delete(identifier, headers)
        self.assertEqual(response.status_code, status)
        self.assertEqual(self.rows(), before)
        return response

    def test_success_contract_soft_delete_and_read_exclusion(self):
        before = self.rows()[0]
        response = self.delete()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        persisted = Vaccination._base_manager.get(pk=self.record.pk)
        self.assertFalse(persisted.is_active)
        self.assertIsNotNone(persisted.deleted_at)
        self.assertGreaterEqual(persisted.updated_at, before["updated_at"])
        after = self.rows()[0]
        for field in before.keys() - {"is_active", "deleted_at", "updated_at"}:
            self.assertEqual(after[field], before[field])
        self.assertEqual(Vaccination._base_manager.count(), 1)
        self.assertFalse(Vaccination.objects.filter(pk=self.record.pk).exists())
        for path in ("/api/vaccinations/", f"/api/vaccinations/animal/{self.animal.pk}/history"):
            result = self.client.get(path, **self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), [])
        detail = self.client.get(f"/api/vaccinations/{self.record.pk}", **self.headers)
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(detail.json(), {"detail": "Vacunación no encontrada."})

    def test_sequential_repeat_is_404_without_new_mutation(self):
        self.assertEqual(self.delete().status_code, 200)
        self.rejected(404)

    def test_missing_uuid_is_404_without_mutation(self):
        self.rejected(404, uuid4())

    def test_invalid_uuid_is_422_without_mutation(self):
        self.rejected(422, "not-a-uuid")

    def test_foreign_tenant_is_404_and_service_is_not_called(self):
        foreign = Vaccination.objects.create(organization=self.other_organization, animal=self.foreign_animal,
            vaccine_name="Foreign", application_date=date(2026, 1, 1), dose=Decimal("1"))
        with patch("apps.vaccinations.api.endpoints.VaccinationService.delete") as service:
            self.rejected(404, foreign.pk)
            service.assert_not_called()

    def test_already_inactive_is_404_without_mutation(self):
        self.record.delete()
        self.rejected(404)

    def test_inactive_animal_does_not_prevent_delete(self):
        self.animal.delete()
        self.assertEqual(self.delete().status_code, 200)
        self.assertFalse(Vaccination._base_manager.get(pk=self.record.pk).is_active)

    def test_all_four_writer_roles_can_delete(self):
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.VETERINARIAN, Membership.Role.OPERATOR):
            with self.subTest(role=role):
                self.membership.role = role
                self.membership.save(update_fields=["role"])
                record = Vaccination.objects.create(organization=self.organization, animal=self.animal,
                    vaccine_name=role, application_date=date(2026, 1, 1), dose=Decimal("1"))
                response = self.delete(record.pk)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"success": True})
                self.assertFalse(Vaccination._base_manager.get(pk=record.pk).is_active)

    def test_viewer_denied_before_selector_and_without_mutation(self):
        self.membership.role = Membership.Role.VIEWER
        self.membership.save(update_fields=["role"])
        with patch("apps.vaccinations.api.endpoints.VaccinationSelector.get_by_id") as selector:
            self.rejected(403)
            selector.assert_not_called()

    def test_missing_or_invalid_bearer_is_401_without_mutation(self):
        for headers in ({}, {"HTTP_AUTHORIZATION": "Bearer invalid"}):
            with self.subTest(headers=headers):
                self.rejected(401, headers=headers)

    def test_missing_membership_is_403_without_mutation(self):
        self.membership.delete()
        self.rejected(403)

    def test_missing_default_context_is_403_without_mutation(self):
        self.membership.is_default = False
        self.membership.save(update_fields=["is_default"])
        self.rejected(403)

    def test_inactive_organization_is_403_without_mutation(self):
        self.organization.delete()
        self.rejected(403)


class VaccinationBirthDateHTTPTests(VaccinationCivilDateHTTPTests):
    def setUp(self):
        super().setUp()
        self.animal.birth_date = date(2026, 9, 15)
        self.animal.save()

    def test_create_before_birth_returns_400_without_persistence(self):
        response = self.request(application_date="2026-09-14")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "La fecha de aplicación no puede ser anterior al nacimiento del animal."})
        self.assertEqual(Vaccination._base_manager.count(), 0)

    def test_create_on_birth_date_is_allowed(self):
        self.assertEqual(self.request(application_date="2026-09-15").status_code, 200)

    def test_create_after_birth_date_is_allowed(self):
        self.assertEqual(self.request(application_date="2026-09-16").status_code, 200)

    def test_create_without_birth_date_has_no_birth_minimum(self):
        self.animal.birth_date = None
        self.animal.save()
        self.assertEqual(self.request(application_date="2026-09-14").status_code, 200)

    def test_update_before_birth_preserves_every_field(self):
        vaccination = self.original()
        before = Vaccination._base_manager.filter(pk=vaccination.pk).values().get()
        response = self.request("put", vaccination, application_date="2026-09-14",
                                vaccine_name="Changed", dose="2.50", batch="Changed",
                                veterinarian="Changed", notes="Changed")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Vaccination._base_manager.filter(pk=vaccination.pk).values().get(), before)
