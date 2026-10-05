from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.animals.models import Animal
from apps.catalogs.models import AnimalStatus, Breed, Gender, ProductionType, Species
from apps.organizations.models import Organization
from apps.common.context.context import RequestContext
from apps.common.exceptions.production import ProductionValidationError
from apps.production.models import ProductionRecord
from apps.production.selectors import ProductionSelector
from apps.production.services import ProductionService


@override_settings(TIME_ZONE="UTC")
class ProductionRecordModelTests(TestCase):
    now = datetime(2026, 5, 20, 12, tzinfo=datetime_timezone.utc)
    birth_date = date(2026, 5, 15)

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="PRODUCTION", name="Production")
        cls.other_organization = Organization.objects.create(code="PRODUCTION_OTHER", name="Other production")
        species = Species.objects.create(code="PRODUCTION", name="Production species")
        breed = Breed.objects.create(species=species, code="PRODUCTION", name="Production breed")
        gender = Gender.objects.create(code="PROD_G", name="Production fixture gender")
        status = AnimalStatus.objects.create(code="PRODUCTION", name="Production status")
        cls.animal = Animal.objects.create(
            organization=cls.organization, species=species, breed=breed,
            gender=gender, status=status, internal_id="PRODUCTION", birth_date=cls.birth_date,
        )
        cls.production_type = ProductionType.objects.create(
            code="TEST_PRODUCTION", name="Test production", default_unit="L",
        )

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def record(self, **changes):
        fields = dict(organization=self.organization, animal=self.animal,
                      production_type=self.production_type, recorded_at=self.now - timedelta(days=1),
                      quantity=Decimal("12.345"), unit="L", notes="Production notes")
        fields.update(changes)
        return ProductionRecord(**fields)

    def assert_invalid(self, field, **changes):
        record = self.record(**changes)
        for operation in (record.full_clean, record.save):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(ValidationError) as error:
                    operation()
                self.assertIn(field, error.exception.message_dict)
        self.assertFalse(ProductionRecord._base_manager.filter(pk=record.pk).exists())

    def test_valid_record_full_clean_and_save(self):
        record = self.record()
        record.full_clean()
        record.save()
        record.refresh_from_db()
        self.assertEqual(record.organization_id, self.organization.pk)
        self.assertEqual(record.animal_id, self.animal.pk)
        self.assertEqual(record.production_type_id, self.production_type.pk)
        self.assertEqual(record.recorded_at, self.now - timedelta(days=1))
        self.assertEqual(record.quantity, Decimal("12.345"))
        self.assertEqual(record.unit, "L")
        self.assertEqual(record.notes, "Production notes")
        self.assertTrue(record.is_active)
        self.assertIsNotNone(record.created_at)
        self.assertIsNotNone(record.updated_at)
        self.assertIsInstance(str(record), str)

    def test_positive_quantity_boundaries(self):
        for quantity in (Decimal("0.001"), Decimal("999999999.999")):
            with self.subTest(quantity=quantity):
                record = self.record(quantity=quantity)
                record.save()
                record.refresh_from_db()
                self.assertEqual(record.quantity, quantity)

    def test_nonpositive_quantity_is_rejected(self):
        for quantity in (Decimal("0"), Decimal("-0.001")):
            with self.subTest(quantity=quantity):
                self.assert_invalid("quantity", quantity=quantity)

    def test_database_constraint_rejects_nonpositive_quantity(self):
        record = self.record()
        record.save()
        for quantity in (Decimal("0"), Decimal("-1")):
            with self.subTest(quantity=quantity):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    ProductionRecord.objects.filter(pk=record.pk).update(quantity=quantity)
                record.refresh_from_db()
                self.assertEqual(record.quantity, Decimal("12.345"))

    def test_quantity_precision_and_scale(self):
        for quantity in (Decimal("1000000000.000"), Decimal("0.0001")):
            with self.subTest(quantity=quantity):
                self.assert_invalid("quantity", quantity=quantity)

    def test_future_timestamp_is_rejected(self):
        self.assert_invalid("recorded_at", recorded_at=self.now + timedelta(microseconds=1))

    def test_naive_timestamp_is_rejected(self):
        self.assert_invalid("recorded_at", recorded_at=self.now.replace(tzinfo=None))

    def test_current_timestamp_is_valid(self):
        self.record(recorded_at=self.now).save()

    def test_timestamp_before_birth_is_rejected(self):
        self.assert_invalid("recorded_at", recorded_at=datetime(2026, 5, 14, 23, 59, tzinfo=datetime_timezone.utc))

    def test_timestamp_on_or_after_birth_is_valid(self):
        for day in (15, 16):
            with self.subTest(day=day):
                self.record(recorded_at=datetime(2026, 5, day, tzinfo=datetime_timezone.utc)).save()

    def test_birth_comparison_uses_project_timezone(self):
        # May 14 at -06:00 is May 15 in the project's configured UTC timezone.
        timestamp = datetime(2026, 5, 14, 20, tzinfo=datetime_timezone(timedelta(hours=-6)))
        self.record(recorded_at=timestamp).save()
        # May 15 at +06:00 is still May 14 in UTC.
        timestamp = datetime(2026, 5, 15, 1, tzinfo=datetime_timezone(timedelta(hours=6)))
        self.assert_invalid("recorded_at", recorded_at=timestamp)

    def test_animal_without_birth_date_accepts_earlier_timestamp(self):
        self.animal.birth_date = None
        self.animal.save()
        self.record(recorded_at=datetime(2020, 1, 1, tzinfo=datetime_timezone.utc)).save()

    def test_other_organization_is_rejected(self):
        self.assert_invalid("animal", organization=self.other_organization)

    def test_active_record_rejects_inactive_animal(self):
        self.animal.delete()
        self.assert_invalid("animal")

    def test_active_record_rejects_inactive_production_type(self):
        self.production_type.delete()
        self.assert_invalid("production_type")

    def test_required_unit_without_automatic_default(self):
        for unit in ("", None, "x" * 21):
            with self.subTest(unit=unit):
                self.assert_invalid("unit", unit=unit)
        record = self.record()
        record.unit = ""
        with self.assertRaises(ValidationError):
            record.save()
        self.assertEqual(record.unit, "")

    def test_unit_is_historical_and_notes_can_be_empty(self):
        record = self.record(unit="kg", notes="")
        record.save()
        self.production_type.default_unit = "g"
        self.production_type.save()
        record.refresh_from_db()
        self.assertEqual(record.unit, "kg")
        self.assertEqual(record.notes, "")
        self.assert_invalid("notes", notes=None)

    def test_missing_and_invalid_relations_raise_validation_error(self):
        for field in ("organization", "animal", "production_type"):
            for changes in ({field: None}, {f"{field}_id": uuid4()}):
                with self.subTest(field=field, changes=changes):
                    self.assert_invalid(field, **changes)

    def test_invalid_scalar_fields_raise_validation_error(self):
        for field, value in (("recorded_at", None), ("recorded_at", "invalid"),
                             ("quantity", None), ("quantity", "invalid")):
            with self.subTest(field=field, value=value):
                self.assert_invalid(field, **{field: value})

    def test_multiple_records_same_day_and_timestamp_are_allowed(self):
        records = [self.record(), self.record(), self.record(recorded_at=self.now - timedelta(days=1, hours=1))]
        for record in records:
            record.save()
        self.assertEqual(ProductionRecord.objects.filter(animal=self.animal).count(), 3)

    def test_invalid_update_preserves_all_persisted_fields(self):
        record = self.record()
        record.save()
        before = ProductionRecord._base_manager.filter(pk=record.pk).values().get()
        record.quantity = Decimal("0")
        record.notes = "Changed"
        record.unit = "kg"
        with self.assertRaises(ValidationError):
            record.save()
        self.assertEqual(ProductionRecord._base_manager.filter(pk=record.pk).values().get(), before)

    def test_soft_delete_preserves_row_and_excludes_from_manager(self):
        record = self.record()
        record.save()
        record.delete()
        persisted = ProductionRecord._base_manager.get(pk=record.pk)
        self.assertFalse(persisted.is_active)
        self.assertIsNotNone(persisted.deleted_at)
        self.assertFalse(ProductionRecord.objects.filter(pk=record.pk).exists())


    def test_soft_delete_after_relations_deactivated(self):
        record = self.record()
        record.save()
        self.animal.delete()
        self.production_type.delete()
        # Reload relations so validation observes their persisted inactive state.
        record = ProductionRecord.objects.get(pk=record.pk)
        record.delete()
        persisted = ProductionRecord._base_manager.get(pk=record.pk)
        self.assertFalse(persisted.is_active)
        self.assertIsNotNone(persisted.deleted_at)
        self.assertFalse(ProductionRecord.objects.filter(pk=record.pk).exists())


@override_settings(TIME_ZONE="UTC")
class ProductionServiceSelectorTests(TestCase):
    now = datetime(2026, 5, 20, 12, tzinfo=datetime_timezone.utc)

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="PROD_SERVICE", name="Production service")
        cls.foreign_organization = Organization.objects.create(code="PROD_FOREIGN", name="Foreign production")
        species = Species.objects.create(code="PROD_SERVICE", name="Production service species")
        breed = Breed.objects.create(species=species, code="PROD_SERVICE", name="Production service breed")
        gender = Gender.objects.create(code="PRODS_G", name="Production service fixture gender")
        status = AnimalStatus.objects.create(code="PROD_SERVICE", name="Production service status")
        fields = dict(species=species, breed=breed, gender=gender, status=status, birth_date=date(2026, 5, 15))
        cls.animal = Animal.objects.create(**fields, organization=cls.organization, internal_id="LOCAL")
        cls.other_animal = Animal.objects.create(**fields, organization=cls.organization, internal_id="OTHER")
        cls.foreign_animal = Animal.objects.create(**fields, organization=cls.foreign_organization, internal_id="FOREIGN")
        cls.milk = ProductionType.objects.get(code="MILK")
        cls.wool = ProductionType.objects.get(code="WOOL")

    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.foreign_context = RequestContext(organization=self.foreign_organization)
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def data(self, **changes):
        fields = dict(animal_id=self.animal.pk, production_type_id=self.milk.pk,
                      recorded_at=self.now - timedelta(days=1), quantity=Decimal("12.345"), notes="Original")
        fields.update(changes)
        return SimpleNamespace(**fields)

    def create(self, **changes):
        return ProductionService.create(self.context, self.data(**changes))

    def foreign_record(self):
        return ProductionService.create(self.foreign_context, self.data(animal_id=self.foreign_animal.pk))

    def assert_create_rejected(self, **changes):
        before = list(ProductionRecord._base_manager.order_by("pk").values())
        with self.assertRaises(ProductionValidationError):
            self.create(**changes)
        self.assertEqual(list(ProductionRecord._base_manager.order_by("pk").values()), before)

    def assert_update_rejected(self, record=None, **changes):
        record = record or self.create()
        before = ProductionRecord._base_manager.filter(pk=record.pk).values().get()
        data = dict(notes="Changed", quantity=Decimal("25.000"), production_type_id=self.wool.pk)
        data.update(changes)
        with self.assertRaises(ProductionValidationError):
            ProductionService.update(self.context, record, self.data(**data))
        self.assertEqual(ProductionRecord._base_manager.filter(pk=record.pk).values().get(), before)
        for field in ("animal_id", "production_type_id", "organization_id", "quantity", "unit", "notes", "recorded_at", "is_active"):
            self.assertEqual(getattr(record, field), before[field])

    def test_create_valid_uses_context_and_catalog_unit(self):
        record = self.create(organization=self.foreign_organization, unit="CLIENT_UNIT")
        record.refresh_from_db()
        self.assertEqual(record.organization_id, self.organization.pk)
        self.assertEqual(record.animal_id, self.animal.pk)
        self.assertEqual(record.unit, "L")
        self.assertEqual(record.quantity, Decimal("12.345"))
        self.assertEqual(record.notes, "Original")

    def test_create_notes_none_omitted_and_text(self):
        for notes in (None, "", " Text\nsecond line "):
            with self.subTest(notes=notes):
                record = self.create(notes=notes)
                record.refresh_from_db()
                self.assertEqual(record.notes, "" if notes is None else notes)
        data = self.data()
        del data.notes
        self.assertEqual(ProductionService.create(self.context, data).notes, "")

    def test_create_rejects_foreign_or_missing_animal(self):
        for animal_id in (self.foreign_animal.pk, uuid4()):
            with self.subTest(animal_id=animal_id):
                self.assert_create_rejected(animal_id=animal_id)

    def test_create_rejects_inactive_animal(self):
        self.animal.delete()
        self.assert_create_rejected()

    def test_create_rejects_missing_or_inactive_type(self):
        self.milk.delete()
        for type_id in (self.milk.pk, uuid4()):
            with self.subTest(type_id=type_id):
                self.assert_create_rejected(production_type_id=type_id)

    def test_create_rejects_invalid_quantity_and_timestamps(self):
        for changes in (dict(quantity=Decimal("0")), dict(quantity=Decimal("-1")),
                        dict(quantity=Decimal("0.0001")),
                        dict(recorded_at=self.now + timedelta(seconds=1)),
                        dict(recorded_at=self.now.replace(tzinfo=None)),
                        dict(recorded_at=datetime(2026, 5, 14, tzinfo=datetime_timezone.utc))):
            with self.subTest(changes=changes):
                self.assert_create_rejected(**changes)

    def test_service_requires_organization_context(self):
        with self.assertRaises(ProductionValidationError):
            ProductionService.create(RequestContext(), self.data())
        self.assertEqual(ProductionRecord.objects.count(), 0)

    def test_update_valid_replaces_fields_and_recalculates_unit(self):
        record = self.create()
        result = ProductionService.update(self.context, record, self.data(
            animal_id=self.other_animal.pk, production_type_id=self.wool.pk,
            recorded_at=self.now, quantity=Decimal("2.500"), notes="Updated",
            organization=self.foreign_organization, unit="CLIENT_UNIT"))
        self.assertIs(result, record)
        record.refresh_from_db()
        self.assertEqual(record.organization_id, self.organization.pk)
        self.assertEqual(record.animal_id, self.other_animal.pk)
        self.assertEqual(record.production_type_id, self.wool.pk)
        self.assertEqual(record.unit, "kg")
        self.assertEqual(record.recorded_at, self.now)
        self.assertEqual(record.quantity, Decimal("2.500"))
        self.assertEqual(record.notes, "Updated")

    def test_update_notes_none_and_omitted_clear_previous_text(self):
        record = self.create()
        ProductionService.update(self.context, record, self.data(notes=None))
        record.refresh_from_db()
        self.assertEqual(record.notes, "")
        data = self.data()
        del data.notes
        ProductionService.update(self.context, record, data)
        record.refresh_from_db()
        self.assertEqual(record.notes, "")

    def test_update_rejects_foreign_or_missing_animal(self):
        record = self.create()
        for animal_id in (self.foreign_animal.pk, uuid4()):
            with self.subTest(animal_id=animal_id):
                self.assert_update_rejected(record, animal_id=animal_id)

    def test_update_rejects_inactive_animal(self):
        record = self.create()
        self.other_animal.delete()
        self.assert_update_rejected(record, animal_id=self.other_animal.pk)

    def test_update_rejects_inactive_or_missing_type(self):
        record = self.create()
        self.wool.delete()
        for type_id in (self.wool.pk, uuid4()):
            with self.subTest(type_id=type_id):
                self.assert_update_rejected(record, production_type_id=type_id)

    def test_update_invalid_domain_values_preserve_database_and_object(self):
        record = self.create()
        for changes in (dict(quantity=Decimal("0")), dict(quantity=Decimal("-1")),
                        dict(recorded_at=self.now + timedelta(seconds=1)),
                        dict(recorded_at=self.now.replace(tzinfo=None)),
                        dict(recorded_at=datetime(2026, 5, 14, tzinfo=datetime_timezone.utc))):
            with self.subTest(changes=changes):
                self.assert_update_rejected(record, **changes)

    def test_update_rejects_foreign_record(self):
        self.assert_update_rejected(self.foreign_record())

    def test_update_rejects_deleted_record(self):
        record = self.create()
        record.delete()
        self.assert_update_rejected(record)

    def test_unit_snapshot_and_new_default_and_update_same_type(self):
        original = self.create()
        self.milk.default_unit = "mL"
        self.milk.save()
        original.refresh_from_db()
        self.assertEqual(original.unit, "L")
        self.assertEqual(self.create().unit, "mL")
        ProductionService.update(self.context, original, self.data())
        original.refresh_from_db()
        self.assertEqual(original.unit, "mL")

    def test_stale_instance_cannot_update_or_delete_a_deleted_record(self):
        stale = self.create()
        current = ProductionRecord.objects.get(pk=stale.pk)
        ProductionService.delete(self.context, current)
        before = ProductionRecord._base_manager.filter(pk=stale.pk).values().get()
        for operation in (
            lambda: ProductionService.update(self.context, stale, self.data()),
            lambda: ProductionService.delete(self.context, stale),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(ProductionValidationError):
                    operation()
                self.assertEqual(ProductionRecord._base_manager.filter(pk=stale.pk).values().get(), before)

    def test_update_and_delete_require_organization_context(self):
        record = self.create()
        before = ProductionRecord._base_manager.filter(pk=record.pk).values().get()
        with self.assertRaises(ProductionValidationError):
            ProductionService.update(RequestContext(), record, self.data())
        with self.assertRaises(ProductionValidationError):
            ProductionService.delete(RequestContext(), record)
        self.assertEqual(ProductionRecord._base_manager.filter(pk=record.pk).values().get(), before)

    def test_delete_soft_deletes_without_removing_row(self):
        record = self.create()
        result = ProductionService.delete(self.context, record)
        self.assertIs(result, record)
        persisted = ProductionRecord._base_manager.get(pk=record.pk)
        self.assertFalse(persisted.is_active)
        self.assertIsNotNone(persisted.deleted_at)
        self.assertFalse(ProductionRecord.objects.filter(pk=record.pk).exists())

    def test_delete_rejects_foreign_or_deleted_record(self):
        foreign = self.foreign_record()
        deleted = self.create()
        deleted.delete()
        for record in (foreign, deleted):
            with self.subTest(record=record.pk):
                before = ProductionRecord._base_manager.filter(pk=record.pk).values().get()
                with self.assertRaises(ProductionValidationError):
                    ProductionService.delete(self.context, record)
                self.assertEqual(ProductionRecord._base_manager.filter(pk=record.pk).values().get(), before)

    def test_delete_with_inactive_animal_or_type(self):
        record = self.create()
        self.animal.delete()
        record = ProductionRecord.objects.get(pk=record.pk)
        ProductionService.delete(self.context, record)
        self.assertFalse(ProductionRecord._base_manager.get(pk=record.pk).is_active)
        record = self.create(animal_id=self.other_animal.pk)
        self.milk.delete()
        record = ProductionRecord.objects.get(pk=record.pk)
        ProductionService.delete(self.context, record)
        self.assertFalse(ProductionRecord._base_manager.get(pk=record.pk).is_active)

    def test_selector_list_filters_tenant_and_deleted_records(self):
        local = self.create()
        self.foreign_record()
        deleted = self.create()
        deleted.delete()
        self.assertEqual(list(ProductionSelector.list(self.context)), [local])

    def test_selector_get_by_id_returns_only_accessible_active_record(self):
        local = self.create()
        foreign = self.foreign_record()
        deleted = self.create()
        deleted.delete()
        self.assertEqual(ProductionSelector.get_by_id(self.context, local.pk), local)
        for record_id in (foreign.pk, deleted.pk, uuid4()):
            with self.subTest(record_id=record_id):
                self.assertIsNone(ProductionSelector.get_by_id(self.context, record_id))

    def test_selector_history_filters_animal_tenant_and_deleted_records(self):
        local = self.create()
        self.create(animal_id=self.other_animal.pk)
        self.foreign_record()
        deleted = self.create()
        deleted.delete()
        self.assertEqual(list(ProductionSelector.history(self.context, self.animal.pk)), [local])
        self.assertEqual(list(ProductionSelector.history(self.context, self.foreign_animal.pk)), [])
        self.assertEqual(list(ProductionSelector.history(self.foreign_context, self.animal.pk)), [])

    def test_selector_ordering_includes_timestamp_creation_and_id(self):
        old = self.create(recorded_at=self.now - timedelta(days=2))
        first = self.create()
        second = self.create()
        # Different creation instants with equal business timestamps.
        ProductionRecord.objects.filter(pk=first.pk).update(created_at=self.now - timedelta(hours=1))
        newest = self.create(recorded_at=self.now)
        expected = [newest.pk, second.pk, first.pk, old.pk]
        for queryset in (ProductionSelector.list(self.context), ProductionSelector.history(self.context, self.animal.pk)):
            self.assertEqual(list(queryset.values_list("pk", flat=True)), expected)
        ProductionRecord.objects.filter(pk=first.pk).update(created_at=self.now)
        expected = [newest.pk, *sorted([first.pk, second.pk], reverse=True), old.pk]
        self.assertEqual(list(ProductionSelector.history(self.context, self.animal.pk).values_list("pk", flat=True)), expected)

    def test_selector_preserves_history_with_inactive_animal_and_type(self):
        record = self.create()
        self.animal.delete()
        self.assertEqual(list(ProductionSelector.history(self.context, self.animal.pk)), [record])
        self.milk.delete()
        self.assertEqual(list(ProductionSelector.history(self.context, self.animal.pk)), [record])

    def test_selectors_load_related_objects_without_n_plus_one(self):
        self.create()
        self.create()
        for queryset in (ProductionSelector.list(self.context), ProductionSelector.history(self.context, self.animal.pk)):
            with self.assertNumQueries(1):
                self.assertEqual([(record.animal.pk, record.production_type.pk) for record in queryset],
                                 [(self.animal.pk, self.milk.pk)] * 2)


@override_settings(TIME_ZONE="UTC")
class ProductionAPITests(TestCase):
    now = datetime(2026, 5, 20, 12, tzinfo=datetime_timezone.utc)

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="PROD_API", name="Production API")
        cls.foreign_organization = Organization.objects.create(code="PROD_API_OTHER", name="Foreign production API")
        species = Species.objects.create(code="PROD_API", name="Production API species")
        breed = Breed.objects.create(species=species, code="PROD_API", name="Production API breed")
        gender = Gender.objects.create(code="PRODA_G", name="Production API fixture gender")
        status = AnimalStatus.objects.create(code="PROD_API", name="Production API status")
        fields = dict(species=species, breed=breed, gender=gender, status=status, birth_date=date(2026, 5, 15))
        cls.animal = Animal.objects.create(**fields, organization=cls.organization, internal_id="LOCAL")
        cls.other_animal = Animal.objects.create(**fields, organization=cls.organization, internal_id="OTHER")
        cls.foreign_animal = Animal.objects.create(**fields, organization=cls.foreign_organization, internal_id="FOREIGN")
        cls.milk = ProductionType.objects.get(code="MILK")
        cls.wool = ProductionType.objects.get(code="WOOL")
        cls.user = User.objects.create_user(email="production-api@example.com")
        cls.membership = Membership.objects.create(user=cls.user, organization=cls.organization,
                                                   role=Membership.Role.OWNER, is_default=True)
        cls.foreign_user = User.objects.create_user(email="production-api-other@example.com")
        Membership.objects.create(user=cls.foreign_user, organization=cls.foreign_organization,
                                  role=Membership.Role.OWNER, is_default=True)

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def payload(self, **changes):
        fields = dict(animal_id=str(self.animal.pk), production_type_id=str(self.milk.pk),
                      recorded_at=(self.now - timedelta(days=1)).isoformat(), quantity="12.345", notes="Original")
        fields.update(changes)
        return fields

    def record(self, animal=None, **changes):
        animal = animal or self.animal
        fields = dict(organization=animal.organization, animal=animal, production_type=self.milk,
                      recorded_at=self.now - timedelta(days=1), quantity=Decimal("12.345"), unit="L", notes="Original")
        fields.update(changes)
        record = ProductionRecord(**fields)
        record.save()
        return record

    def request(self, method, path="/api/production/", data=None, user=None):
        return getattr(self.client, method)(path, data=data, content_type="application/json",
                                           HTTP_AUTHORIZATION=f"Bearer {create_access_token(user or self.user)}")

    def assert_response(self, data, record):
        self.assertEqual(set(data), {"id", "animal_id", "production_type_id", "recorded_at", "quantity", "unit", "notes", "is_active"})
        self.assertEqual(data["id"], str(record.pk))
        self.assertEqual(data["animal_id"], str(record.animal_id))
        self.assertEqual(data["production_type_id"], str(record.production_type_id))
        self.assertEqual(datetime.fromisoformat(data["recorded_at"].replace("Z", "+00:00")), record.recorded_at)
        self.assertEqual(Decimal(str(data["quantity"])), record.quantity)
        self.assertEqual(data["unit"], record.unit)
        self.assertEqual(data["notes"], record.notes)
        self.assertEqual(data["is_active"], record.is_active)

    def assert_datetime_boundary_rejected(self, method, timestamp):
        record = self.record() if method == "put" else None
        snapshot = ProductionRecord._base_manager.filter(pk=record.pk).values().get() if record else None
        count = ProductionRecord._base_manager.count()
        path = f"/api/production/{record.pk}" if record else "/api/production/"
        response = self.request(method, path, self.payload(
            recorded_at=timestamp, animal_id=str(self.other_animal.pk),
            production_type_id=str(self.wool.pk), quantity="2.500", notes="Boundary update",
        ))
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(ProductionRecord._base_manager.count(), count)
        if record:
            record.refresh_from_db()
            self.assertEqual(ProductionRecord._base_manager.filter(pk=record.pk).values().get(), snapshot)
        # The count and snapshot queries also prove the connection remains usable.

    def test_post_datetime_lower_boundary_plus_one(self):
        self.assert_datetime_boundary_rejected("post", "0001-01-01T00:00:00+01:00")

    def test_put_datetime_lower_boundary_plus_one(self):
        self.assert_datetime_boundary_rejected("put", "0001-01-01T00:00:00+01:00")

    def test_post_datetime_lower_boundary_plus_fourteen(self):
        self.assert_datetime_boundary_rejected("post", "0001-01-01T00:00:00+14:00")

    def test_put_datetime_lower_boundary_plus_fourteen(self):
        self.assert_datetime_boundary_rejected("put", "0001-01-01T00:00:00+14:00")

    def test_post_datetime_upper_boundary_minus_fourteen(self):
        self.assert_datetime_boundary_rejected("post", "9999-12-31T23:59:59-14:00")

    def test_put_datetime_upper_boundary_minus_fourteen(self):
        self.assert_datetime_boundary_rejected("put", "9999-12-31T23:59:59-14:00")

    def test_datetime_boundary_depends_on_active_timezone_offset(self):
        timestamp = datetime(1, 1, 1, tzinfo=datetime_timezone.utc)
        with timezone.override(datetime_timezone.utc):
            self.assertEqual(timezone.localdate(timestamp), date(1, 1, 1))
        with timezone.override(datetime_timezone(timedelta(hours=-1))):
            with self.assertRaises(OverflowError):
                timezone.localdate(timestamp)
            for method in ("post", "put"):
                with self.subTest(method=method, timezone=timezone.get_current_timezone_name()):
                    self.assert_datetime_boundary_rejected(method, timestamp.isoformat())

    def test_safe_extreme_datetime_preserves_existing_date_rules(self):
        self.animal.birth_date = None
        self.animal.save()
        response = self.request("post", data=self.payload(recorded_at="0001-01-01T00:00:00Z"))
        self.assertEqual(response.status_code, 200, response.content)
        future = self.request("post", data=self.payload(recorded_at="9999-12-31T23:59:59Z"))
        self.assertEqual(future.status_code, 400, future.content)
        self.assertEqual(ProductionRecord._base_manager.count(), 1)

    def test_ordinary_aware_datetime_still_accepts_post_and_put(self):
        response = self.request("post", data=self.payload(notes=None))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notes"], "")
        response = self.request("put", f"/api/production/{response.json()['id']}", self.payload())
        self.assertEqual(response.status_code, 200)

    def test_model_datetime_boundary_has_specific_field_and_code(self):
        record = ProductionRecord(organization=self.organization, animal=self.animal,
                                  production_type=self.milk, unit="L", quantity=Decimal("1"),
                                  recorded_at=datetime.fromisoformat("0001-01-01T00:00:00+01:00"))
        with self.assertRaises(ValidationError) as caught:
            record.full_clean()
        self.assertEqual(set(caught.exception.error_dict), {"recorded_at"})
        self.assertEqual([error.code for error in caught.exception.error_dict["recorded_at"]],
                         ["recorded_at_timezone_overflow"])
        # full_clean() aggregates errors and replaces the outer exception.
        with self.assertRaises(ValidationError) as direct:
            record.clean()
        self.assertIsInstance(direct.exception.__cause__, OverflowError)

    def test_unexpected_overflow_outside_datetime_conversion_propagates(self):
        record = self.record()
        snapshot = ProductionRecord._base_manager.filter(pk=record.pk).values().get()
        for method, path in (("post", "/api/production/"), ("put", f"/api/production/{record.pk}")):
            with self.subTest(method=method):
                with patch.object(ProductionRecord, "save", side_effect=OverflowError("internal overflow")):
                    with self.assertRaisesRegex(OverflowError, "internal overflow"):
                        self.request(method, path, self.payload())
                self.assertEqual(ProductionRecord._base_manager.count(), 1)
                record.refresh_from_db()
                self.assertEqual(ProductionRecord._base_manager.filter(pk=record.pk).values().get(), snapshot)

    def test_openapi_routes_input_and_response_contracts(self):
        from config.api import api

        schema = api.get_openapi_schema()
        expected = {"/api/production/": {"get", "post"},
                    "/api/production/{record_id}": {"get", "put", "delete"},
                    "/api/production/history/{animal_id}": {"get"}}
        for path, methods in expected.items():
            self.assertEqual(set(schema["paths"][path]), methods)
        components = schema["components"]["schemas"]
        for name in ("ProductionCreateSchema", "ProductionUpdateSchema"):
            self.assertEqual(set(components[name]["properties"]),
                             {"animal_id", "production_type_id", "recorded_at", "quantity", "notes"})
            self.assertFalse(components[name]["additionalProperties"])
            self.assertEqual(components[name]["properties"]["recorded_at"]["format"], "date-time")
            self.assertEqual(set(components[name]["required"]), {"animal_id", "production_type_id", "recorded_at", "quantity"})
        for path, method, name in (("/api/production/", "post", "ProductionCreateSchema"),
                                   ("/api/production/{record_id}", "put", "ProductionUpdateSchema")):
            body = schema["paths"][path][method]["requestBody"]["content"]["application/json"]["schema"]
            self.assertEqual(body["$ref"], f"#/components/schemas/{name}")
        for path, method in (("/api/production/", "get"), ("/api/production/history/{animal_id}", "get")):
            response = schema["paths"][path][method]["responses"][200]["content"]["application/json"]["schema"]
            self.assertEqual(response["type"], "array")
            self.assertEqual(response["items"]["$ref"], "#/components/schemas/ProductionResponseSchema")
        for path, method in (("/api/production/", "post"), ("/api/production/{record_id}", "get"),
                              ("/api/production/{record_id}", "put")):
            response = schema["paths"][path][method]["responses"][200]["content"]["application/json"]["schema"]
            self.assertEqual(response["$ref"], "#/components/schemas/ProductionResponseSchema")

    def test_list_filters_tenant_soft_delete_and_orders(self):
        older = self.record(recorded_at=self.now - timedelta(days=2))
        newer = self.record(recorded_at=self.now)
        self.record(self.foreign_animal)
        deleted = self.record()
        deleted.delete()
        response = self.request("get")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [str(newer.pk), str(older.pk)])
        for item, record in zip(response.json(), (newer, older)):
            self.assert_response(item, record)

    def test_detail_contract_and_inaccessible_records(self):
        own = self.record()
        response = self.request("get", f"/api/production/{own.pk}")
        self.assertEqual(response.status_code, 200)
        self.assert_response(response.json(), own)
        foreign = self.record(self.foreign_animal)
        deleted = self.record()
        deleted.delete()
        for record_id in (foreign.pk, deleted.pk, uuid4()):
            with self.subTest(record_id=record_id):
                response = self.request("get", f"/api/production/{record_id}")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Registro de producción no encontrado."})

    def test_history_route_filters_animal_tenant_deleted_and_orders(self):
        older = self.record(recorded_at=self.now - timedelta(days=2))
        newer = self.record(recorded_at=self.now)
        self.record(self.other_animal)
        self.record(self.foreign_animal)
        deleted = self.record()
        deleted.delete()
        response = self.request("get", f"/api/production/history/{self.animal.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [str(newer.pk), str(older.pk)])

    def test_history_empty_missing_and_foreign_animal(self):
        foreign = self.record(self.foreign_animal)
        for animal_id in (self.animal.pk, self.foreign_animal.pk, uuid4()):
            with self.subTest(animal_id=animal_id):
                response = self.request("get", f"/api/production/history/{animal_id}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])
        response = self.request("get", f"/api/production/history/{self.foreign_animal.pk}", user=self.foreign_user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [str(foreign.pk)])

    def test_history_remains_visible_with_inactive_relations(self):
        record = self.record()
        self.animal.delete()
        self.milk.delete()
        response = self.request("get", f"/api/production/history/{self.animal.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()], [str(record.pk)])

    def test_create_valid_context_unit_and_null_notes(self):
        response = self.request("post", data=self.payload(notes=None))
        self.assertEqual(response.status_code, 200)
        record = ProductionRecord.objects.get(pk=response.json()["id"])
        self.assertEqual(record.organization_id, self.organization.pk)
        self.assertEqual(record.unit, self.milk.default_unit)
        self.assertEqual(record.notes, "")
        self.assert_response(response.json(), record)

    def test_create_rejects_domain_errors_without_persistence(self):
        for changes in (dict(animal_id=str(self.foreign_animal.pk)), dict(production_type_id=str(uuid4())),
                        dict(quantity="0"), dict(quantity="-1"),
                        dict(recorded_at=(self.now + timedelta(seconds=1)).isoformat()),
                        dict(recorded_at="2026-05-14T12:00:00Z")):
            with self.subTest(changes=changes):
                count = ProductionRecord._base_manager.count()
                response = self.request("post", data=self.payload(**changes))
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.json()["detail"], str)
                self.assertEqual(ProductionRecord._base_manager.count(), count)

    def test_create_rejects_inactive_relations(self):
        self.other_animal.delete()
        response = self.request("post", data=self.payload(animal_id=str(self.other_animal.pk)))
        self.assertEqual(response.status_code, 400)
        self.milk.delete()
        self.assertEqual(self.request("post", data=self.payload()).status_code, 400)
        self.assertEqual(ProductionRecord._base_manager.count(), 0)

    def test_naive_timestamp_rejected_before_service_for_post_and_put(self):
        record = self.record()
        for method, path, operation in (("post", "/api/production/", "create"),
                                         ("put", f"/api/production/{record.pk}", "update")):
            with self.subTest(method=method):
                with patch(f"apps.production.api.endpoints.ProductionService.{operation}") as service:
                    response = self.request(method, path, self.payload(recorded_at="2026-05-19T12:00:00"))
                    self.assertEqual(response.status_code, 422)
                    service.assert_not_called()

    def test_create_and_update_forbid_client_controlled_fields(self):
        record = self.record()
        for method, path in (("post", "/api/production/"), ("put", f"/api/production/{record.pk}")):
            for field, value in (("unit", "kg"), ("organization", str(self.foreign_organization.pk)),
                                 ("is_active", False), ("created_at", self.now.isoformat()),
                                 ("updated_at", self.now.isoformat()), ("deleted_at", None)):
                with self.subTest(method=method, field=field):
                    self.assertEqual(self.request(method, path, self.payload(**{field: value})).status_code, 422)
        record.refresh_from_db()
        self.assertEqual(record.unit, "L")
        self.assertTrue(record.is_active)

    def test_put_requires_all_editable_required_fields(self):
        record = self.record()
        for field in ("animal_id", "production_type_id", "recorded_at", "quantity"):
            with self.subTest(field=field):
                payload = self.payload()
                del payload[field]
                self.assertEqual(self.request("put", f"/api/production/{record.pk}", payload).status_code, 422)

    def test_update_valid_recalculates_unit_and_keeps_organization(self):
        record = self.record()
        response = self.request("put", f"/api/production/{record.pk}", self.payload(
            animal_id=str(self.other_animal.pk), production_type_id=str(self.wool.pk), quantity="2.500", notes=None))
        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.organization_id, self.organization.pk)
        self.assertEqual(record.unit, "kg")
        self.assertEqual(record.notes, "")
        self.assert_response(response.json(), record)

    def test_put_persists_quantity_and_notes_with_same_animal_and_production_type(self):
        record = self.record(quantity=Decimal("12.500"), notes="Initial production")
        animal_id = record.animal_id
        production_type_id = record.production_type_id
        expected_unit = record.production_type.default_unit
        path = f"/api/production/{record.pk}"
        payload = self.payload(
            animal_id=str(animal_id), production_type_id=str(production_type_id),
            recorded_at=record.recorded_at.isoformat(),
            quantity="13.250", notes="Updated production",
        )

        response = self.request("put", path, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quantity"], "13.250")
        self.assertEqual(response.json()["notes"], "Updated production")
        self.assertEqual(response.json()["unit"], expected_unit)

        record.refresh_from_db()
        self.assertEqual(record.quantity, Decimal("13.250"))
        self.assertEqual(record.notes, "Updated production")
        self.assertEqual(record.unit, expected_unit)
        self.assertEqual(record.animal_id, animal_id)
        self.assertEqual(record.production_type_id, production_type_id)

        response = self.request("get", path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["quantity"], "13.250")
        self.assertEqual(response.json()["notes"], "Updated production")
        self.assertEqual(response.json()["unit"], expected_unit)

    def test_update_invalid_payload_preserves_persisted_fields(self):
        record = self.record()
        before = ProductionRecord._base_manager.filter(pk=record.pk).values().get()
        for changes in (dict(quantity="0"), dict(recorded_at=(self.now + timedelta(seconds=1)).isoformat()),
                        dict(animal_id=str(self.foreign_animal.pk))):
            with self.subTest(changes=changes):
                payload = self.payload(production_type_id=str(self.wool.pk), notes="Changed")
                payload.update(changes)
                self.assertEqual(self.request("put", f"/api/production/{record.pk}", payload).status_code, 400)
                self.assertEqual(ProductionRecord._base_manager.filter(pk=record.pk).values().get(), before)

    def test_update_and_delete_inaccessible_record_return_404(self):
        foreign = self.record(self.foreign_animal)
        deleted = self.record()
        deleted.delete()
        for record_id in (foreign.pk, deleted.pk, uuid4()):
            for method in ("put", "delete"):
                with self.subTest(method=method, record_id=record_id):
                    response = self.request(method, f"/api/production/{record_id}", self.payload() if method == "put" else None)
                    self.assertEqual(response.status_code, 404)
        self.assertTrue(ProductionRecord.objects.filter(pk=foreign.pk).exists())

    def test_delete_contract_and_soft_delete_with_inactive_relations(self):
        record = self.record()
        self.animal.delete()
        self.milk.delete()
        response = self.request("delete", f"/api/production/{record.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        persisted = ProductionRecord._base_manager.get(pk=record.pk)
        self.assertFalse(persisted.is_active)
        self.assertIsNotNone(persisted.deleted_at)
        self.assertEqual(self.request("get", f"/api/production/{record.pk}").status_code, 404)

    def test_viewer_reads_but_cannot_write(self):
        record = self.record()
        self.membership.role = Membership.Role.VIEWER
        self.membership.save()
        for path in ("/api/production/", f"/api/production/{record.pk}", f"/api/production/history/{self.animal.pk}"):
            self.assertEqual(self.request("get", path).status_code, 200)
        for method, path, operation in (("post", "/api/production/", "create"),
                                         ("put", f"/api/production/{record.pk}", "update"),
                                         ("delete", f"/api/production/{record.pk}", "delete")):
            with self.subTest(method=method):
                with patch(f"apps.production.api.endpoints.ProductionService.{operation}") as service:
                    self.assertEqual(self.request(method, path, self.payload() if method != "delete" else None).status_code, 403)
                    service.assert_not_called()

    def test_all_existing_writer_roles_can_create_update_delete(self):
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.VETERINARIAN, Membership.Role.OPERATOR):
            with self.subTest(role=role):
                self.membership.role = role
                self.membership.save()
                response = self.request("post", data=self.payload())
                self.assertEqual(response.status_code, 200)
                path = f"/api/production/{response.json()['id']}"
                self.assertEqual(self.request("put", path, self.payload(quantity="20.000")).status_code, 200)
                self.assertEqual(self.request("delete", path).status_code, 200)

    def test_router_requires_authentication_and_active_tenant_membership(self):
        self.assertEqual(self.client.get("/api/production/").status_code, 401)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.request("get").status_code, 403)

    def test_invalid_path_uuids_are_rejected(self):
        for path in ("/api/production/not-a-uuid", "/api/production/history/not-a-uuid"):
            with self.subTest(path=path):
                self.assertEqual(self.request("get", path).status_code, 422)

