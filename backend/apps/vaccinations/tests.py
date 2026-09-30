from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

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
        gender = Gender.objects.create(code="VAC", name="Hembra")
        status = AnimalStatus.objects.create(code="VAC", name="Activo")
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
        self.today = timezone.localdate()

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
        gender = Gender.objects.create(code="HIST", name="Hembra")
        status = AnimalStatus.objects.create(code="HIST", name="Activo")
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
