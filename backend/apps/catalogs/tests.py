from copy import deepcopy
from unittest import TestCase as UnitTestCase
from uuid import UUID
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.services.jwt import create_access_token

from apps.catalogs.models import (
    AnimalStatus,
    Breed,
    BreedingType,
    FarmType,
    Gender,
    MovementType,
    ProductionType,
    Species,
    WeighingMethod,
)
from apps.catalogs.services import CatalogService


SEED_MODULE = "apps.catalogs.migrations.0016_seed_required_genders_and_animal_statuses"
SEED_TARGET = ("catalogs", "0016_seed_required_genders_and_animal_statuses")


class RequiredCatalogSeedTests(TestCase):
    def setUp(self):
        self.seed = import_module(SEED_MODULE).seed_required_catalogs
        self.apps = MigrationLoader(connection).project_state([SEED_TARGET]).apps
        self.gender = self.apps.get_model("catalogs", "Gender")
        self.status = self.apps.get_model("catalogs", "AnimalStatus")
        # Only the isolated Django test database is changed.
        self.gender._base_manager.all().delete()
        self.status._base_manager.all().delete()
        self.editor = SimpleNamespace(connection=connection)

    def forward(self):
        with transaction.atomic(using=connection.alias):
            self.seed(self.apps, self.editor)

    def snapshot(self, model):
        return list(model._base_manager.order_by("code").values())

    def test_seed_creates_exact_required_codes_and_preserves_other_catalogs(self):
        other_models = [self.apps.get_model("catalogs", name) for name in (
            "FarmType", "MovementType", "ProductionType", "Species", "Breed",
            "WeighingMethod", "BreedingType",
        )]
        before = [self.snapshot(model) for model in other_models]
        self.forward()
        self.assertEqual(dict(self.gender._base_manager.values_list("code", "name")),
                         {"F": "Hembra", "M": "Macho"})
        self.assertEqual(dict(self.status._base_manager.values_list("code", "name")),
                         {"ACTIVE": "Activo", "SOLD": "Vendido"})
        for model in (self.gender, self.status):
            for row in model._base_manager.all():
                self.assertTrue(row.is_active)
                self.assertIsNone(row.deleted_at)
                self.assertIsInstance(row.pk, UUID)
        self.assertEqual([self.snapshot(model) for model in other_models], before)

    def test_seed_is_idempotent_and_preserves_uuids_and_fields(self):
        self.forward()
        before = [self.snapshot(self.gender), self.snapshot(self.status)]
        self.forward()
        self.assertEqual([self.snapshot(self.gender), self.snapshot(self.status)], before)

    def test_seed_preserves_existing_customized_names(self):
        for model, code in ((self.gender, "F"), (self.status, "ACTIVE")):
            model._base_manager.create(code=code, name="Custom name")
        before = [self.snapshot(self.gender)[0], self.snapshot(self.status)[0]]
        self.forward()
        for model, code, original in ((self.gender, "F", before[0]), (self.status, "ACTIVE", before[1])):
            self.assertEqual(model._base_manager.filter(code=code).values().get(), original)

    def test_seed_preserves_inactive_and_soft_deleted_codes(self):
        from django.utils import timezone

        for model, codes in ((self.gender, ("F", "M")), (self.status, ("ACTIVE", "SOLD"))):
            for index, code in enumerate(codes):
                model._base_manager.create(code=code, name=f"Custom {code}", is_active=False,
                    deleted_at=timezone.now() if index else None)
        before = [self.snapshot(self.gender), self.snapshot(self.status)]
        self.forward()
        self.assertEqual([self.snapshot(self.gender), self.snapshot(self.status)], before)

    def test_name_conflicts_abort_before_any_seed_writes(self):
        # A late conflict also proves earlier candidates were not inserted.
        for model, code, name in ((self.gender, "F", "Hembra"), (self.status, "SOLD", "Vendido")):
            with self.subTest(model=model._meta.label):
                conflict = model._base_manager.create(code="X", name=name, is_active=False)
                before = [self.snapshot(self.gender), self.snapshot(self.status)]
                with self.assertRaises(RuntimeError) as raised:
                    self.seed(self.apps, self.editor)
                self.assertIn(f"{model._meta.label} code='{code}'", str(raised.exception))
                self.assertIn("code='X'", str(raised.exception))
                self.assertIn("Resuelva el conflicto", str(raised.exception))
                self.assertEqual([self.snapshot(self.gender), self.snapshot(self.status)], before)
                model._base_manager.filter(pk=conflict.pk).delete()

    def test_forward_uses_schema_editor_alias_for_both_models(self):
        # Routing contract checked without introducing a second settings database.
        with patch.object(self.gender._base_manager, "using", wraps=self.gender._base_manager.using) as gender_using:
            with patch.object(self.status._base_manager, "using", wraps=self.status._base_manager.using) as status_using:
                self.forward()
                for manager in (gender_using, status_using):
                    self.assertTrue(manager.called)
                    for call in manager.call_args_list:
                        self.assertEqual(call.args, (connection.alias,))


class RequiredCatalogMigrationTests(UnitTestCase):
    def setUp(self):
        # A fresh in-memory database keeps executor/reverse/rollback writes out
        # of the shared test database and avoids TransactionTestCase's flush.
        self.db_alias = "catalog_seed_migrations"
        self.assertNotIn(self.db_alias, connections.databases)
        config = deepcopy(connection.settings_dict)
        config.update(ENGINE="django.db.backends.sqlite3", NAME=":memory:")
        connections.databases[self.db_alias] = config
        self.addCleanup(self.close_isolated_database)
        self.connection = connections[self.db_alias]
        self.executor = MigrationExecutor(self.connection)
        self.leaves = self.executor.loader.graph.leaf_nodes()
        baseline = ("catalogs", "0015_seed_production_types")
        targets = [leaf for leaf in self.leaves if leaf != SEED_TARGET] + [baseline]
        self.executor.migrate(targets)
        self.apps = self.executor.loader.project_state(targets).apps
        self.gender = self.apps.get_model("catalogs", "Gender")
        self.status = self.apps.get_model("catalogs", "AnimalStatus")

    def close_isolated_database(self):
        connections[self.db_alias].close()
        del connections[self.db_alias]
        connections.databases.pop(self.db_alias)

    def test_real_migration_applies_records_seeds_and_reverse_preserves_rows(self):
        MigrationExecutor(self.connection).migrate(self.leaves)
        self.assertIn(SEED_TARGET, MigrationRecorder(self.connection).applied_migrations())
        before = [list(model._base_manager.using(self.db_alias).order_by("code").values()) for model in (self.gender, self.status)]
        self.assertEqual(dict(self.gender._base_manager.using(self.db_alias).values_list("code", "name")), {"F": "Hembra", "M": "Macho"})
        self.assertEqual(dict(self.status._base_manager.using(self.db_alias).values_list("code", "name")), {"ACTIVE": "Activo", "SOLD": "Vendido"})
        MigrationExecutor(self.connection).migrate([("catalogs", "0015_seed_production_types")])
        self.assertNotIn(SEED_TARGET, MigrationRecorder(self.connection).applied_migrations())
        self.assertEqual([list(model._base_manager.using(self.db_alias).order_by("code").values()) for model in (self.gender, self.status)], before)

    def test_real_migration_failure_rolls_back_and_is_not_recorded(self):
        # Run the real seed, then fail before the RunPython operation completes.
        # This checks the executor transaction after actual database writes.
        executor = MigrationExecutor(self.connection)
        operation = executor.loader.get_migration(*SEED_TARGET).operations[0]
        forward = operation.code

        def fail_after_seeding(apps, editor):
            forward(apps, editor)
            self.assertEqual(self.gender._base_manager.using(self.db_alias).count(), 2)
            self.assertEqual(self.status._base_manager.using(self.db_alias).count(), 2)
            raise RuntimeError("Injected failure after seed writes")

        with patch.object(operation, "code", side_effect=fail_after_seeding):
            with self.assertRaisesRegex(RuntimeError, "Injected failure after seed writes"):
                executor.migrate([SEED_TARGET])
        self.assertEqual(self.gender._base_manager.using(self.db_alias).count(), 0)
        self.assertEqual(self.status._base_manager.using(self.db_alias).count(), 0)
        self.assertNotIn(SEED_TARGET, MigrationRecorder(self.connection).applied_migrations())


class RequiredCatalogMigratedStateTests(TestCase):
    def test_clean_test_database_migrations_provide_required_codes(self):
        self.assertEqual(dict(Gender._base_manager.values_list("code", "name")), {"F": "Hembra", "M": "Macho"})
        self.assertEqual(dict(AnimalStatus._base_manager.values_list("code", "name")), {"ACTIVE": "Activo", "SOLD": "Vendido"})
        self.assertIn(SEED_TARGET, MigrationRecorder(connection).applied_migrations())


class ProductionTypeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.production_type = ProductionType.objects.create(
            code="TEST_PRODUCTION", name="Test production", default_unit="kg",
            description="Test description",
        )

    def test_create_preserves_fields_and_audit_defaults(self):
        self.production_type.full_clean()
        self.production_type.refresh_from_db()
        self.assertIsInstance(self.production_type.pk, UUID)
        self.assertEqual(self.production_type.code, "TEST_PRODUCTION")
        self.assertEqual(self.production_type.name, "Test production")
        self.assertEqual(self.production_type.default_unit, "kg")
        self.assertEqual(self.production_type.description, "Test description")
        self.assertEqual(str(self.production_type), "Test production")
        self.assertTrue(self.production_type.is_active)
        self.assertIsNone(self.production_type.deleted_at)
        self.assertIsNotNone(self.production_type.created_at)
        self.assertIsNotNone(self.production_type.updated_at)

    def test_code_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductionType.objects.create(code=self.production_type.code,
                                          name="Different name", default_unit="L")

    def test_name_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductionType.objects.create(code="DIFFERENT", name=self.production_type.name,
                                          default_unit="L")

    def test_default_unit_is_required(self):
        for fields in ({}, {"default_unit": ""}, {"default_unit": None}):
            with self.subTest(fields=fields):
                production_type = ProductionType(code="REQUIRED", name="Required", **fields)
                with self.assertRaises(ValidationError) as error:
                    production_type.full_clean()
                self.assertIn("default_unit", error.exception.message_dict)

    def test_description_can_be_empty(self):
        production_type = ProductionType(code="EMPTY", name="Empty description", default_unit="L")
        production_type.full_clean()
        production_type.save()
        production_type.refresh_from_db()
        self.assertEqual(production_type.description, "")

    def test_service_excludes_inactive_and_soft_deleted_types(self):
        inactive = ProductionType.objects.create(code="INACTIVE", name="Inactive", default_unit="kg", is_active=False)
        deleted = ProductionType.objects.create(code="DELETED", name="Deleted", default_unit="L")
        deleted.delete()
        results = list(CatalogService.get_production_types())
        self.assertIn(self.production_type, results)
        self.assertNotIn(inactive, results)
        self.assertNotIn(deleted, results)
        self.assertTrue(ProductionType._base_manager.filter(pk=deleted.pk, is_active=False).exists())

    def test_service_orders_by_name(self):
        ProductionType.objects.create(code="Z", name="Z production", default_unit="kg")
        ProductionType.objects.create(code="A", name="A production", default_unit="L")
        names = list(CatalogService.get_production_types().values_list("name", flat=True))
        self.assertEqual(names, sorted(names))

    def test_migrations_seed_milk_and_wool_without_meat(self):
        self.assertEqual(
            dict(ProductionType.objects.filter(code__in=["MILK", "WOOL"]).values_list("code", "name")),
            {"MILK": "Leche", "WOOL": "Lana"},
        )
        self.assertEqual(
            dict(ProductionType.objects.filter(code__in=["MILK", "WOOL"]).values_list("code", "default_unit")),
            {"MILK": "L", "WOOL": "kg"},
        )
        self.assertFalse(ProductionType._base_manager.filter(code="MEAT").exists())


class ProductionTypeAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="production-catalog@example.com")
        cls.production_type = ProductionType.objects.create(
            code="API_PRODUCTION", name="API production", default_unit="L", description="API description",
        )

    def request_catalog(self):
        return self.client.get("/api/catalogs/production-types",
                               HTTP_AUTHORIZATION=f"Bearer {create_access_token(self.user)}")

    def test_endpoint_returns_schema_and_name_order(self):
        response = self.request_catalog()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item["name"] for item in data], sorted(item["name"] for item in data))
        item = next(item for item in data if item["code"] == self.production_type.code)
        self.assertEqual(item, {"id": str(self.production_type.pk), "code": "API_PRODUCTION",
                                "name": "API production", "default_unit": "L", "description": "API description"})
        for item in data:
            self.assertEqual(set(item), {"id", "code", "name", "default_unit", "description"})
            UUID(item["id"])

    def test_endpoint_excludes_inactive_and_soft_deleted_types(self):
        inactive = ProductionType.objects.create(code="API_INACTIVE", name="API inactive", default_unit="kg", is_active=False)
        self.production_type.delete()
        response = self.request_catalog()
        self.assertEqual(response.status_code, 200)
        codes = {item["code"] for item in response.json()}
        self.assertNotIn(inactive.code, codes)
        self.assertNotIn(self.production_type.code, codes)

    def test_openapi_route_and_response_contract(self):
        from config.api import api

        schema = api.get_openapi_schema()
        operations = schema["paths"]["/api/catalogs/production-types"]
        self.assertEqual(set(operations), {"get"})
        response = operations["get"]["responses"][200]["content"]["application/json"]["schema"]
        self.assertEqual(response["type"], "array")
        self.assertEqual(response["items"]["$ref"], "#/components/schemas/ProductionTypeSchema")
        self.assertEqual(set(schema["components"]["schemas"]["ProductionTypeSchema"]["properties"]),
                         {"id", "code", "name", "default_unit", "description"})


class CatalogServiceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.species_a = Species.objects.create(
            code="CAT_SPECIES_A",
            name="Catalog Species A",
        )

        cls.species_b = Species.objects.create(
            code="CAT_SPECIES_B",
            name="Catalog Species B",
        )

        cls.breed_a1 = Breed.objects.create(
            species=cls.species_a,
            code="CAT_BREED_A1",
            name="Catalog Breed A1",
        )

        cls.breed_a2 = Breed.objects.create(
            species=cls.species_a,
            code="CAT_BREED_A2",
            name="Catalog Breed A2",
        )

        cls.breed_b1 = Breed.objects.create(
            species=cls.species_b,
            code="CAT_BREED_B1",
            name="Catalog Breed B1",
        )

        cls.gender = Gender.objects.create(
            code="CAT_GENDER",
            name="Catalog Gender",
        )

        cls.animal_status = AnimalStatus.objects.create(
            code="CAT_STATUS",
            name="Catalog Status",
        )

        cls.movement_type = MovementType.objects.create(
            code="CAT_MOVEMENT",
            name="Catalog Movement",
        )

        cls.breeding_type = BreedingType.objects.create(
            code="CAT_BREEDING",
            name="Catalog Breeding",
        )

        cls.weighing_method = WeighingMethod.objects.create(
            code="CAT_WEIGHING",
            name="Catalog Weighing",
        )

        cls.farm_type = FarmType.objects.create(
            code="CAT_FARM",
            name="Catalog Farm",
            description="Catalog test farm type",
        )

        cls.inactive_species = Species.objects.create(
            code="CAT_SPECIES_INACTIVE",
            name="Catalog Species Inactive",
            is_active=False,
        )

    def test_get_farm_types_returns_only_active_records(self):
        results = CatalogService.get_farm_types()

        self.assertIn(self.farm_type, results)

    def test_get_species_returns_only_active_records(self):
        results = CatalogService.get_species()

        self.assertIn(self.species_a, results)
        self.assertIn(self.species_b, results)
        self.assertNotIn(self.inactive_species, results)

    def test_get_breeds_returns_all_active_breeds(self):
        results = CatalogService.get_breeds()

        self.assertIn(self.breed_a1, results)
        self.assertIn(self.breed_a2, results)
        self.assertIn(self.breed_b1, results)

    def test_get_breeds_can_filter_by_species(self):
        results = CatalogService.get_breeds(
            species_id=self.species_a.pk,
        )

        self.assertEqual(
            set(results),
            {
                self.breed_a1,
                self.breed_a2,
            },
        )

    def test_get_genders_returns_active_records(self):
        results = CatalogService.get_genders()

        self.assertIn(self.gender, results)

    def test_get_animal_statuses_returns_active_records(self):
        results = CatalogService.get_animal_statuses()

        self.assertIn(self.animal_status, results)

    def test_get_movement_types_returns_active_records(self):
        results = CatalogService.get_movement_types()

        self.assertIn(self.movement_type, results)

    def test_get_breeding_types_returns_active_records(self):
        results = CatalogService.get_breeding_types()

        self.assertIn(self.breeding_type, results)

    def test_get_weighing_methods_returns_active_records(self):
        results = CatalogService.get_weighing_methods()

        self.assertIn(self.weighing_method, results)
