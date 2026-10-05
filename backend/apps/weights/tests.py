from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from apps.animals.models import Animal
from apps.catalogs.models import AnimalStatus, Breed, Gender, Species, WeighingMethod
from apps.common.context.context import RequestContext
from apps.common.exceptions.weight import WeightValidationError
from apps.organizations.models import Organization
from apps.weights.api.schemas import WeightCreateSchema, WeightUpdateSchema
from apps.weights.calculators.adg_calculator import ADGCalculator
from apps.weights.models import Weight
from apps.weights.selectors.weight_selector import WeightSelector
from apps.weights.services.weight_service import WeightService
from apps.accounts.models import User, Membership
from apps.accounts.services.jwt import create_access_token


class WeightBusinessRulesTests(TestCase):
    today = date(2026, 5, 20)
    birth = date(2026, 5, 15)

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="WEIGHTS", name="Weights")
        cls.other_organization = Organization.objects.create(code="WEIGHTS_OTHER", name="Other weights")
        species = Species.objects.create(code="WEIGHTS", name="Weights species")
        breed = Breed.objects.create(species=species, code="WEIGHTS", name="Weights breed")
        gender = Gender.objects.create(code="WEIGHT_G", name="Weights fixture gender")
        status = AnimalStatus.objects.create(code="WEIGHTS", name="Weights status")
        fields = dict(species=species, breed=breed, gender=gender, status=status)
        cls.animal = Animal.objects.create(**fields, organization=cls.organization, internal_id="WEIGHTS", birth_date=cls.birth)
        cls.other_animal = Animal.objects.create(**fields, organization=cls.other_organization, internal_id="OTHER")
        cls.inactive_animal = Animal.objects.create(**fields, organization=cls.organization, internal_id="INACTIVE", is_active=False)
        cls.method = WeighingMethod.objects.create(code="WEIGHTS", name="Weights method")
        cls.other_method = WeighingMethod.objects.create(code="WEIGHTS_OTHER", name="Other weights method")

    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        clock = patch("django.utils.timezone.localdate", return_value=self.today)
        clock.start()
        self.addCleanup(clock.stop)

    def payload(self, schema=WeightCreateSchema, **changes):
        fields = dict(animal_id=self.animal.pk, weighing_method_id=self.method.pk,
                      date=self.birth, weight=Decimal("40.00"), notes="Original")
        fields.update(changes)
        return schema(**fields)

    def assert_rejected(self, changes, message=None):
        count = Weight._base_manager.count()
        with self.assertRaises(WeightValidationError) as error:
            WeightService.create(self.context, self.payload(**changes))
        if message:
            self.assertEqual(str(error.exception), message)
        self.assertEqual(Weight._base_manager.count(), count)
        original = WeightService.create(self.context, self.payload(date=self.today))
        before = Weight._base_manager.filter(pk=original.pk).values().get()
        update = dict(weight=Decimal("55.00"), notes="Changed", weighing_method_id=self.other_method.pk)
        update.update(changes)
        with self.assertRaises(WeightValidationError):
            WeightService.update(original, self.context, self.payload(WeightUpdateSchema, **update))
        self.assertEqual(Weight._base_manager.filter(pk=original.pk).values().get(), before)

    def test_future_date(self):
        self.assert_rejected(dict(date=self.today + timedelta(days=1)), "La fecha del pesaje no puede ser futura.")

    def test_zero_weight(self):
        self.assert_rejected(dict(weight=Decimal("0")), "El peso debe ser mayor que cero.")

    def test_negative_weight(self):
        self.assert_rejected(dict(weight=Decimal("-1")), "El peso debe ser mayor que cero.")

    def test_date_before_birth(self):
        self.assert_rejected(dict(date=self.birth - timedelta(days=1)), "La fecha del pesaje no puede ser anterior al nacimiento del animal.")

    def test_active_duplicate(self):
        WeightService.create(self.context, self.payload())
        self.assert_rejected({}, "Ya existe un pesaje registrado para este animal en esa fecha.")

    def test_other_tenant_animal(self):
        self.assert_rejected(dict(animal_id=self.other_animal.pk))

    def test_inactive_animal(self):
        self.assert_rejected(dict(animal_id=self.inactive_animal.pk))

    def test_birth_date_is_valid_and_update_excludes_itself(self):
        weight = WeightService.create(self.context, self.payload())
        WeightService.update(weight, self.context, self.payload(WeightUpdateSchema, weight=Decimal("45.00")))
        weight.refresh_from_db()
        self.assertEqual(weight.date, self.birth)
        self.assertEqual(weight.weight, Decimal("45.00"))
        self.assertEqual(Weight.objects.count(), 1)

    def test_without_birth_date(self):
        self.animal.birth_date = None
        self.animal.save()
        weight = WeightService.create(self.context, self.payload(date=date(2020, 1, 1)))
        WeightService.update(weight, self.context, self.payload(WeightUpdateSchema, date=date(2019, 1, 1)))
        weight.refresh_from_db()
        self.assertEqual(weight.date, date(2019, 1, 1))

    def test_inactive_duplicate_allows_create_and_update(self):
        inactive = WeightService.create(self.context, self.payload())
        WeightService.delete(inactive)
        weight = WeightService.create(self.context, self.payload())
        WeightService.update(weight, self.context, self.payload(WeightUpdateSchema))
        self.assertEqual(Weight.objects.filter(is_active=True).count(), 1)

    def test_update_validates_new_animal_birth_date(self):
        self.other_animal.organization = self.organization
        self.other_animal.birth_date = self.today
        self.other_animal.save()
        self.assert_rejected(dict(animal_id=self.other_animal.pk))

    def test_model_birth_date_validation(self):
        weight = Weight(organization=self.organization, animal=self.animal,
                        weighing_method=self.method, date=self.birth - timedelta(days=1), weight=Decimal("40.00"))
        with self.assertRaises(ValidationError) as error:
            weight.full_clean()
        self.assertIn("date", error.exception.message_dict)
        weight.date = self.birth
        weight.full_clean()

    def test_failed_full_clean_update_does_not_persist_partial_changes(self):
        weight = WeightService.create(self.context, self.payload())
        before = Weight._base_manager.filter(pk=weight.pk).values().get()
        with self.assertRaises(WeightValidationError) as caught:
            WeightService.update(weight, self.context, self.payload(WeightUpdateSchema, weight=Decimal("10000.00"), notes="Changed"))
        self.assertIsInstance(caught.exception.__cause__, ValidationError)
        weight.refresh_from_db()
        self.assertEqual(Weight._base_manager.filter(pk=weight.pk).values().get(), before)

    def test_selectors_isolate_tenant_and_inactive_weights(self):
        weight = WeightService.create(self.context, self.payload())
        other_context = RequestContext(organization=self.other_organization)
        self.assertIsNone(WeightSelector.get_by_id(other_context, weight.pk))
        self.assertFalse(WeightSelector.list(other_context).exists())
        self.assertFalse(WeightSelector.history(other_context, self.animal.pk).exists())
        WeightService.delete(weight)
        self.assertIsNone(WeightSelector.get_by_id(self.context, weight.pk))
        self.assertIsNone(WeightSelector.last_weight(self.context, self.animal.pk))


class WeightActiveIntegrityTests(TestCase):
    today = WeightBusinessRulesTests.today
    birth = WeightBusinessRulesTests.birth
    setUp = WeightBusinessRulesTests.setUp
    payload = WeightBusinessRulesTests.payload

    @classmethod
    def setUpTestData(cls):
        WeightBusinessRulesTests.setUpTestData.__func__(cls)
        cls.second_animal = Animal.objects.create(
            organization=cls.organization, species=cls.animal.species, breed=cls.animal.breed,
            gender=cls.animal.gender, status=cls.animal.status, internal_id="SECOND",
        )

    def create(self, **changes):
        return WeightService.create(self.context, self.payload(**changes))

    def test_same_animal_different_date_is_allowed(self):
        self.create()
        self.create(date=self.today)
        self.assertEqual(Weight.objects.count(), 2)

    def test_same_date_different_animal_is_allowed(self):
        self.create()
        self.create(animal_id=self.second_animal.pk)
        self.assertEqual(Weight.objects.count(), 2)

    def test_database_rejects_duplicate_with_different_organization(self):
        self.create()
        with self.assertRaises(IntegrityError) as caught:
            with transaction.atomic():
                Weight.objects.create(organization=self.other_organization, animal=self.animal,
                                      weighing_method=self.method, date=self.birth, weight=Decimal("45.00"))
        print("H3_SQLITE_DIAGNOSTIC", str(caught.exception), caught.exception.args,
              type(caught.exception.__cause__).__name__, str(caught.exception.__cause__))
        self.assertEqual(Weight._base_manager.count(), 1)

    def test_create_real_collision_is_translated(self):
        self.create()
        with patch.object(WeightService, "_validate_business_rules"), patch.object(Weight, "full_clean"):
            with self.assertRaises(WeightValidationError) as caught:
                self.create()
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.assertEqual(Weight._base_manager.count(), 1)

    def test_update_real_collision_is_translated_and_rolls_back(self):
        self.create()
        second = self.create(date=self.today)
        before = Weight._base_manager.filter(pk=second.pk).values().get()
        with patch.object(WeightService, "_validate_business_rules"), patch.object(Weight, "full_clean"):
            with self.assertRaises(WeightValidationError) as caught:
                WeightService.update(second, self.context, self.payload(WeightUpdateSchema, notes="Changed"))
        self.assertIsInstance(caught.exception.__cause__, IntegrityError)
        self.assertEqual(Weight._base_manager.filter(pk=second.pk).values().get(), before)
        second.refresh_from_db()
        self.assertEqual(second.date, self.today)

    def test_full_clean_duplicate_is_translated_selectively(self):
        self.create()
        with patch.object(WeightService, "_validate_business_rules"):
            with self.assertRaises(WeightValidationError) as caught:
                self.create()
        self.assertIsInstance(caught.exception.__cause__, ValidationError)
        self.assertEqual(caught.exception.__cause__.error_dict["__all__"][0].code, "active_weight_duplicate")
        self.assertEqual(Weight.objects.count(), 1)

    def test_unrelated_real_integrity_error_propagates(self):
        # Inject NULL after payload normalization, preserving the real DB failure.
        def invalid_notes(weight):
            weight.notes = None

        with patch.object(Weight, "full_clean", invalid_notes):
            with self.assertRaises(IntegrityError):
                self.create(notes=None)
        self.assertEqual(Weight._base_manager.count(), 0)

    def test_restore_conflict_is_rejected_by_database(self):
        first = self.create()
        WeightService.delete(first)
        second = self.create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                first.restore()
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertIsNotNone(first.deleted_at)
        self.assertEqual(Weight.objects.get().pk, second.pk)

    def test_http_create_real_collision_returns_400(self):
        self.create()
        self.assert_http_collision("post", "/api/weights/")
        self.assertEqual(Weight._base_manager.count(), 1)

    def test_http_update_real_collision_returns_400(self):
        self.create()
        second = self.create(date=self.today)
        self.assert_http_collision("put", f"/api/weights/{second.pk}")
        second.refresh_from_db()
        self.assertEqual(second.date, self.today)

    def assert_http_collision(self, method, path):
        user = User.objects.create_user(email="h3@example.com")
        Membership.objects.create(user=user, organization=self.organization,
                                  role=Membership.Role.OPERATOR, is_default=True)
        data = dict(animal_id=str(self.animal.pk), weighing_method_id=str(self.method.pk),
                    date=self.birth.isoformat(), weight="45.00", notes="HTTP")
        with patch.object(WeightService, "_validate_business_rules"), patch.object(Weight, "full_clean"):
            response = getattr(self.client, method)(path, data=data, content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Ya existe un pesaje registrado para este animal en esa fecha."})


class ADGCalculatorTests(SimpleTestCase):
    def weight(self, day, value):
        return SimpleNamespace(date=date(2026, 5, day), weight=Decimal(value))

    def test_without_previous_weight(self):
        self.assertIsNone(ADGCalculator.calculate(None, self.weight(20, "110")))

    def test_nonpositive_days(self):
        for day in (19, 20):
            with self.subTest(day=day):
                self.assertIsNone(ADGCalculator.calculate(self.weight(20, "100"), self.weight(day, "110")))

    def test_normal_calculation(self):
        self.assertEqual(
            ADGCalculator.calculate(self.weight(17, "100.00"), self.weight(20, "110.00")),
            dict(previous_weight=Decimal("100.00"), current_weight=Decimal("110.00"),
                 gain=Decimal("10.00"), days=3, adg=Decimal("3.333")),
        )


class WeightPayloadHTTPTests(TestCase):
    today = WeightBusinessRulesTests.today
    birth = WeightBusinessRulesTests.birth
    setUpTestData = classmethod(WeightBusinessRulesTests.setUpTestData.__func__)

    def setUp(self):
        WeightBusinessRulesTests.setUp(self)
        user = User.objects.create_user(email="h5c@example.com")
        Membership.objects.create(user=user, organization=self.organization,
                                  role=Membership.Role.OPERATOR, is_default=True)
        self.authorization = f"Bearer {create_access_token(user)}"

    def data(self, **changes):
        result = dict(animal_id=str(self.animal.pk), weighing_method_id=str(self.method.pk),
                      date=self.birth.isoformat(), weight="40.00", notes="Original")
        result.update(changes)
        return result

    def request(self, method="post", path="/api/weights/", **changes):
        # Roll back unexpected database failures before making state assertions.
        with transaction.atomic():
            return getattr(self.client, method)(path, data=self.data(**changes),
                content_type="application/json", HTTP_AUTHORIZATION=self.authorization)

    def original(self):
        return WeightService.create(self.context, WeightCreateSchema(**self.data()))

    def test_http_post_decimal_limits_return_400(self):
        for value in ("10000.00", "1.001", "10000"):
            with self.subTest(weight=value):
                response = self.request(weight=value)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()["detail"])
                self.assertEqual(Weight._base_manager.count(), 0)

    def test_http_put_decimal_limits_return_400_and_preserve_all_fields(self):
        weight = self.original()
        before = Weight._base_manager.filter(pk=weight.pk).values().get()
        for value in ("10000.00", "1.001", "10000"):
            with self.subTest(weight=value):
                response = self.request("put", f"/api/weights/{weight.pk}", weight=value,
                    date=self.today.isoformat(), notes="Changed", weighing_method_id=str(self.other_method.pk))
                self.assertEqual(response.status_code, 400)
                weight.refresh_from_db()
                self.assertEqual(Weight._base_manager.filter(pk=weight.pk).values().get(), before)

    def test_http_post_notes_omitted_saves_empty_string(self):
        data = self.data()
        del data["notes"]
        with transaction.atomic():
            response = self.client.post("/api/weights/", data=data, content_type="application/json",
                HTTP_AUTHORIZATION=self.authorization)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Weight._base_manager.get().notes, "")

    def test_http_post_notes_null_saves_empty_string(self):
        self.assertEqual(self.request(notes=None).status_code, 200)
        self.assertEqual(Weight._base_manager.get().notes, "")

    def test_http_put_notes_null_saves_empty_string(self):
        weight = self.original()
        self.assertEqual(self.request("put", f"/api/weights/{weight.pk}", notes=None).status_code, 200)
        weight.refresh_from_db()
        self.assertEqual(weight.notes, "")

    def test_http_unknown_validation_errors_propagate_original(self):
        known = ValidationError("precision", code="max_digits")
        duplicate = ValidationError("duplicate", code="active_weight_duplicate")
        unknown = ValidationError("unexpected", code="unexpected")
        for errors in ({"notes": unknown}, {"weight": [known, unknown]},
                       {"__all__": duplicate, "notes": unknown},
                       {"organization": known}):
            with self.subTest(errors=errors):
                error = ValidationError(errors)
                with patch.object(Weight, "full_clean", side_effect=error):
                    with self.assertRaises(ValidationError) as caught:
                        self.request()
                self.assertIs(caught.exception, error)
                self.assertEqual(Weight._base_manager.count(), 0)

    def test_http_unrelated_integrity_error_propagates_original(self):
        error = IntegrityError("unrelated database failure")
        with patch.object(Weight, "save", side_effect=error):
            with self.assertRaises(IntegrityError) as caught:
                self.request()
        self.assertIs(caught.exception, error)
        self.assertEqual(Weight._base_manager.count(), 0)

    def test_http_invalid_schema_returns_422(self):
        for changes in ({"weight": "not-decimal"}, {"animal_id": "not-uuid"}, {"date": "not-date"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.request(**changes).status_code, 422)
        self.assertEqual(Weight._base_manager.count(), 0)

    def test_http_existing_business_rules_return_400(self):
        for changes in ({"weight": "0"}, {"weight": "-1"},
                        {"date": (self.today + timedelta(days=1)).isoformat()},
                        {"date": (self.birth - timedelta(days=1)).isoformat()},
                        {"animal_id": str(self.other_animal.pk)}):
            with self.subTest(changes=changes):
                self.assertEqual(self.request(**changes).status_code, 400)
        self.assertEqual(Weight._base_manager.count(), 0)
