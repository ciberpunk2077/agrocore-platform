import io
import json
import secrets
import shutil
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, OperationalError
from django.test import TransactionTestCase, override_settings

from apps.accounts.models import Membership, User
from apps.animals.models import Animal
from apps.catalogs.models import Species, Breed, Gender, AnimalStatus, FarmType
from apps.common.context.context import RequestContext
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization
from apps.organizations.demo.d2 import create_d2, DeliveryPending
from apps.organizations.demo.delivery import EncryptedTestDelivery
from apps.organizations.demo.d3 import create_d3, D3Error, D4_LABELS, PLAN, RESERVES, _all_snapshot


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing', PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class DemoD3Tests(TransactionTestCase):
    def setUp(self):
        self.protected = Organization.objects.create(name='Rancho los Hermanos', code='PROTECTED')
        user = User.objects.create_user(email='protected@example.invalid', password=secrets.token_urlsafe(32))
        Membership.objects.create(user=user, organization=self.protected, role='OWNER', is_default=True)
        # Explicit fixtures only in the disposable database, never repairs by D3.
        self.species = Species.objects.create(code='BOV', name='Test bovine')
        self.breed = Breed.objects.create(species=self.species, code='HOL', name='Test breed')
        self.female, _ = Gender.objects.get_or_create(code='F', defaults={'name': 'Hembra'})
        self.male, _ = Gender.objects.get_or_create(code='M', defaults={'name': 'Macho'})
        self.status, _ = AnimalStatus.objects.get_or_create(code='ACTIVE', defaults={'name': 'Activo'})
        farm_type, _ = FarmType.objects.get_or_create(code='RANCH', defaults={'name': 'Rancho'})
        farm = Farm.objects.create(organization=self.protected, code='OLD-F', name='Protected farm', farm_type=farm_type)
        lot = Lot.objects.create(organization=self.protected, farm=farm, code='OLD-L', name='Protected lot', capacity=10)
        Animal.objects.create(organization=self.protected, farm=farm, lot=lot, species=self.species, breed=self.breed, gender=self.female, status=self.status, internal_id='OLD-A')
        self.key = secrets.token_bytes(32)
        self.deliveries = []
        for _ in range(2):
            directory = settings.DEMO_D2_TEST_ROOT / f'delivery-{uuid4().hex}'
            directory.mkdir(); self.addCleanup(shutil.rmtree, directory)
            self.deliveries.append(EncryptedTestDelivery(directory, encryption_key=secrets.token_bytes(32)))
        self.d2, self.delivery = self.deliveries
        create_d2(self.protected.pk, self.d2, signing_key=self.key)
        self.before = _all_snapshot()
        self.parent_bytes = self.d2.final.read_bytes()
        self.org_ids = self.d2.load()['receipt']['payload']['inventory']['organizations']['ids']

    def create(self, **options):
        return create_d3(self.protected.pk, self.d2, self.delivery, signing_key=self.key, species_code='BOV', breed_code='HOL', **options)

    def farms(self): return Farm.objects.filter(organization_id__in=self.org_ids)
    def lots(self): return Lot.objects.filter(organization_id__in=self.org_ids)
    def animals(self): return Animal.objects.filter(organization_id__in=self.org_ids)

    def test_exact_global_and_tenant_quotas(self):
        self.assertEqual(self.create(), {'state': 'created-D3', 'farms': 12, 'lots': 39, 'animals': 293, 'reserved_calves': 32})
        self.assertEqual((self.farms().count(), self.lots().count(), self.animals().count()), (12, 39, 293))
        for index, (_, code, _, farms, lots, final) in enumerate(PLAN):
            self.assertEqual((self.farms().filter(organization__code=code).count(), self.lots().filter(organization__code=code).count(), self.animals().filter(organization__code=code).count()), (farms, lots, final - RESERVES[index]))

    def test_tenant_catalog_relationships_and_unique_codes(self):
        self.create()
        for animal in self.animals().select_related('farm', 'lot', 'breed', 'gender', 'status'):
            self.assertEqual(animal.organization_id, animal.farm.organization_id)
            self.assertEqual(animal.organization_id, animal.lot.organization_id)
            self.assertEqual(animal.farm_id, animal.lot.farm_id)
            self.assertEqual(animal.breed.species_id, animal.species_id)
            self.assertIn(animal.gender.code, ['F', 'M']); self.assertEqual(animal.status.code, 'ACTIVE')
        self.assertEqual(len(set(self.animals().values_list('organization_id', 'internal_id'))), 293)
        self.assertEqual(len(set(self.farms().values_list('organization_id', 'code'))), 12)
        self.assertEqual(len(set(self.lots().values_list('organization_id', 'code'))), 39)

    def test_genealogy_and_reproductive_cohorts(self):
        self.create()
        for animal in self.animals().select_related('mother__gender', 'father__gender'):
            for parent, gender in [(animal.mother, 'F'), (animal.father, 'M')]:
                if parent:
                    self.assertEqual(parent.organization_id, animal.organization_id)
                    self.assertEqual(parent.gender.code, gender)
                    self.assertLess(parent.birth_date, animal.birth_date)
        for reservation in self.delivery.load()['receipt']['payload']['reservations']:
            self.assertEqual(len(reservation['mother_uuids']), reservation['automatic_calves'])
            self.assertGreaterEqual(len(reservation['adult_female_uuids']), reservation['automatic_calves'] * 2 + 6)
            self.assertEqual(len(reservation['adult_male_uuids']), 2)
            self.assertGreaterEqual(len(reservation['existing_calf_uuids']), 2)
        cohorts = {json.loads(row.notes)['cohort'] for row in self.animals()}
        self.assertEqual(cohorts, {'adult-female', 'adult-male', 'juvenile', 'existing-calf'})

    def test_lot_capacity_includes_automatic_calf_reserve(self):
        self.create(); future = {}
        for reservation in self.delivery.load()['receipt']['payload']['reservations']:
            for mother in Animal.objects.filter(pk__in=reservation['mother_uuids']):
                future[mother.lot_id] = future.get(mother.lot_id, 0) + 1
        self.assertEqual(sum(future.values()), 32)
        for lot in self.lots():
            self.assertGreaterEqual(lot.capacity, self.animals().filter(lot=lot).count() + future.get(lot.pk, 0))

    def test_services_receive_owner_tenant_context_and_real_schemas(self):
        from apps.organizations.demo import d3
        original = d3.AnimalService.create
        calls = []
        def inspect(context, data):
            self.assertIsInstance(context, RequestContext)
            self.assertEqual(context.membership.role, 'OWNER')
            self.assertEqual(context.membership.organization_id, context.organization.pk)
            self.assertEqual(context.membership.user_id, context.user.pk)
            calls.append(data.internal_id)
            return original(context, data)
        with patch.object(d3.AnimalService, 'create', side_effect=inspect): self.create()
        self.assertEqual(len(calls), 293)

    def test_missing_catalog_does_not_write_or_repair(self):
        self.breed.is_active = False; self.breed.save()
        before = _all_snapshot()
        with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), before)
        self.assertFalse(self.delivery.pending.exists())

    def test_wrong_species_breed_relationship_rejected(self):
        other = Species.objects.create(code='OTHER', name='Other species')
        self.breed.species = other; self.breed.save()
        before = _all_snapshot()
        with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), before)

    def test_farm_lot_animal_collisions_never_adopted(self):
        self.create(); self.delivery.final.unlink()
        before = _all_snapshot()
        with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), before)

    def test_partial_farm_dataset_rejected(self):
        farm_type = FarmType.objects.get(code='RANCH')
        Farm.objects.create(organization_id=self.org_ids[0], code='D3-F01', name='Unknown farm', farm_type=farm_type)
        before = _all_snapshot()
        with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), before)

    def test_failures_in_each_service_roll_back_entire_d3(self):
        from apps.organizations.demo import d3
        for service, fail_at in [(d3.FarmService, 3), (d3.LotService, 8), (d3.AnimalService, 60)]:
            original = service.create; count = 0
            def fail(context, data):
                nonlocal count
                count += 1
                if count == fail_at: raise RuntimeError('private payload')
                return original(context, data)
            with patch.object(service, 'create', side_effect=fail):
                with self.assertRaises(D3Error) as caught: self.create()
            self.assertNotIn('private payload', str(caught.exception))
            self.assertEqual(_all_snapshot(), self.before)
            self.assertEqual(self.d2.final.read_bytes(), self.parent_bytes)

    def test_existing_records_and_d2_credentials_preserved(self):
        self.create(); after = _all_snapshot()
        for label, rows in self.before.items():
            for identifier, row in rows.items(): self.assertEqual(after[label][identifier], row)
        self.assertEqual(self.d2.final.read_bytes(), self.parent_bytes)
        for label in D4_LABELS: self.assertEqual(apps.get_model(label).objects.count(), 0)

    def test_repeat_and_dry_run_never_duplicate_or_regenerate_credentials(self):
        self.create(); before = _all_snapshot(); receipt = self.delivery.final.read_bytes()
        with patch('apps.organizations.demo.d2.secrets.token_urlsafe') as generate:
            self.assertEqual(self.create()['state'], 'recognized-D3')
            self.assertEqual(self.create(dry_run=True)['state'], 'recognized-D3')
            generate.assert_not_called()
        self.assertEqual(_all_snapshot(), before)
        self.assertEqual(self.delivery.final.read_bytes(), receipt)
        self.assertEqual(self.d2.final.read_bytes(), self.parent_bytes)

    def test_fresh_dry_run_is_readonly(self):
        with patch.object(self.delivery, 'stage') as stage:
            self.assertEqual(self.create(dry_run=True)['state'], 'fresh-D3-dry-run'); stage.assert_not_called()
        self.assertEqual(_all_snapshot(), self.before)
        self.assertFalse(self.delivery.final.exists())

    def test_altered_or_missing_records_rejected(self):
        self.create(); self.animals().filter(pk=self.animals().first().pk).update(name='Altered')
        before = _all_snapshot()
        with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), before)

    def test_cross_tenant_service_payload_rolls_back(self):
        from apps.organizations.demo import d3
        original = d3.LotService.create
        protected_farm = Farm.objects.get(organization=self.protected)
        def cross(context, data):
            return original(context, data.model_copy(update={'farm_id': protected_farm.pk}))
        with patch.object(d3.LotService, 'create', side_effect=cross):
            with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), self.before)

    def test_publication_recovery_preserves_same_receipt_and_credentials(self):
        with patch.object(self.delivery, 'publish', side_effect=OSError('test')):
            with self.assertRaises(DeliveryPending): self.create()
        before = _all_snapshot(); pending = self.delivery.pending.read_bytes()
        self.assertEqual(self.create()['state'], 'recognized-D3')
        self.assertEqual(self.delivery.final.read_bytes(), pending)
        self.assertEqual(_all_snapshot(), before)
        self.assertEqual(self.d2.final.read_bytes(), self.parent_bytes)

    def test_stage_and_commit_failure_roll_back(self):
        with patch.object(self.delivery, 'stage', side_effect=OSError('test')):
            with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), self.before)
        with patch.object(connections['default'], 'commit', side_effect=OperationalError('test')):
            with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), self.before)
        with self.assertRaises(D3Error): self.create()  # Unconfirmed receipt cannot adopt a rolled-back dataset.

    def test_command_remains_blocked(self):
        with self.assertRaises(CommandError): call_command('seed_demo_ranches', '--write', stdout=io.StringIO())
        self.assertEqual(_all_snapshot(), self.before)

    def test_same_delivery_directory_rejected(self):
        with self.assertRaises(D3Error): create_d3(self.protected.pk, self.d2, self.d2, signing_key=self.key, species_code='BOV', breed_code='HOL')
        self.assertEqual(_all_snapshot(), self.before)

    def test_each_required_catalog_must_be_active(self):
        for row in [self.species, self.breed, self.female, self.male, self.status, FarmType.objects.get(code='RANCH')]:
            row.is_active = False; row.save()
            before = _all_snapshot()
            with self.assertRaises(D3Error): self.create()
            self.assertEqual(_all_snapshot(), before)
            row.is_active = True; row.save()

    def test_manifest_contains_complete_uuid_and_relation_trace(self):
        self.create(); payload = self.delivery.load()['receipt']['payload']
        rows = payload['inventory']['animals']['rows']
        self.assertEqual(len(rows), 293)
        for row in rows:
            for field in ['id', 'organization_id', 'farm_id', 'lot_id', 'species_id', 'breed_id', 'gender_id', 'status_id']:
                self.assertTrue(row[field])
        self.assertEqual(payload['catalogs']['breed'], str(self.breed.pk))
        self.assertEqual(sum(item['automatic_calves'] for item in payload['reservations']), 32)

    def test_missing_record_rejected_without_repair(self):
        self.create(); self.animals().last().delete()
        before = _all_snapshot()
        with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), before)

    def test_catalog_deactivated_after_creation_rejected(self):
        self.create(); self.status.is_active = False; self.status.save()
        before = _all_snapshot()
        with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), before)

    def test_staging_mutation_of_protected_animal_rolls_back(self):
        def mutate(_bundle):
            Animal.objects.filter(organization=self.protected).update(name='Changed')
        with patch.object(self.delivery, 'stage', side_effect=mutate):
            with self.assertRaises(D3Error): self.create()
        self.assertEqual(_all_snapshot(), self.before)

    def test_wrong_receipt_key_rejected_without_changes(self):
        self.create(); before = _all_snapshot()
        with self.assertRaises(ValueError): create_d3(self.protected.pk, self.d2, self.delivery, signing_key=secrets.token_bytes(32), species_code='BOV', breed_code='HOL')
        self.assertEqual(_all_snapshot(), before)
