from datetime import timedelta
from decimal import Decimal
import io
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
from django.utils import timezone

from apps.accounts.models import User, Membership
from apps.animals.models import Animal
from apps.catalogs.models import Species, Breed, Gender, AnimalStatus, FarmType, WeighingMethod, BreedingType, MovementType, ProductionType
from apps.common.context.context import RequestContext
from apps.common.temporal import get_business_today
from apps.dashboard.selectors.dashboard_selector import DashboardSelector
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization
from apps.organizations.demo.d2 import create_d2, DeliveryPending
from apps.organizations.demo.d3 import create_d3, owner_context, RESERVES
from apps.organizations.demo.delivery import EncryptedTestDelivery
from apps.organizations.demo.d4 import create_d4, D4Error, QUOTAS, PLAN, D4_LABELS, _snapshot
from apps.weights.api.schemas import WeightCreateSchema
from apps.weights.services.weight_service import WeightService


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing', PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class DemoD4Tests(TransactionTestCase):
    def setUp(self):
        self.protected = Organization.objects.create(name='Rancho los Hermanos', code='PROTECTED')
        user = User.objects.create_user(email='protected@example.invalid', password=secrets.token_urlsafe(32))
        membership = Membership.objects.create(user=user, organization=self.protected, role='OWNER', is_default=True)
        species = Species.objects.create(code='BOV', name='Explicit bovine test fixture')
        breed = Breed.objects.create(species=species, code='HOL', name='Explicit test breed')
        for model, code, values in [
            (Gender, 'F', {'name': 'Hembra'}), (Gender, 'M', {'name': 'Macho'}),
            (AnimalStatus, 'ACTIVE', {'name': 'Activo'}), (AnimalStatus, 'SOLD', {'name': 'Vendido'}),
            (FarmType, 'RANCH', {'name': 'Rancho'}),
            (MovementType, 'TRANSFER', {'name': 'Traslado'}), (MovementType, 'SALE', {'name': 'Venta'}),
            (ProductionType, 'MILK', {'name': 'Leche', 'default_unit': 'L'}),
            (WeighingMethod, 'SCALE', {'name': 'Explicit scale fixture'}),
            (BreedingType, 'NAT', {'name': 'Explicit natural breeding fixture'}),
        ]:
            model.objects.get_or_create(code=code, defaults=values)
        farm = Farm.objects.create(organization=self.protected, farm_type=FarmType.objects.get(code='RANCH'), code='OLD-F', name='Protected farm')
        lot = Lot.objects.create(organization=self.protected, farm=farm, code='OLD-L', name='Protected lot', capacity=5)
        animal = Animal.objects.create(organization=self.protected, farm=farm, lot=lot, species=species, breed=breed,
            gender=Gender.objects.get(code='F'), status=AnimalStatus.objects.get(code='ACTIVE'), internal_id='OLD-A', birth_date=timezone.localdate() - timedelta(days=1600))
        WeightService.create(RequestContext(user, self.protected, membership), WeightCreateSchema(animal_id=animal.pk,
            weighing_method_id=WeighingMethod.objects.get(code='SCALE').pk, date=timezone.localdate() - timedelta(days=10), weight=Decimal('123.45')))
        self.key = secrets.token_bytes(32)
        deliveries = []
        for _ in range(3):
            directory = settings.DEMO_D2_TEST_ROOT / f'delivery-{uuid4().hex}'
            directory.mkdir(); self.addCleanup(shutil.rmtree, directory)
            deliveries.append(EncryptedTestDelivery(directory, encryption_key=secrets.token_bytes(32)))
        self.d2, self.d3, self.delivery = deliveries
        create_d2(self.protected.pk, self.d2, signing_key=self.key)
        create_d3(self.protected.pk, self.d2, self.d3, signing_key=self.key, species_code='BOV', breed_code='HOL')
        self.org_ids = self.d2.load()['receipt']['payload']['inventory']['organizations']['ids']
        self.before = _snapshot()
        self.parent_bytes = (self.d2.final.read_bytes(), self.d3.final.read_bytes())

    def create(self, **options):
        return create_d4(self.protected.pk, self.d2, self.d3, self.delivery, signing_key=self.key,
            species_code='BOV', breed_code='HOL', weighing_method_code='SCALE', breeding_type_code='NAT', **options)

    def records(self, label):
        return apps.get_model(label).objects.filter(organization_id__in=self.org_ids)

    def test_exact_quotas_and_final_animals(self):
        self.assertEqual(self.create(), {'state': 'created-D4', 'animals': 325, 'automatic_calves': 32})
        self.assertEqual(self.records('animals.Animal').count(), 325)
        self.assertEqual([self.records(label).count() for label in D4_LABELS], [62, 39, 14, 70, 70, 49, 34])
        for index, (_, code, _, _, _, final) in enumerate(PLAN):
            org = Organization.objects.get(code=code)
            w, v, sales, existing, upcoming, production = QUOTAS[index]
            births = RESERVES[index] + existing + 1
            self.assertEqual(self.records('animals.Animal').filter(organization=org).count(), final)
            self.assertEqual([self.records(label).filter(organization=org).count() for label in D4_LABELS],
                [w, v, sales + 1, births + upcoming + 2, births + upcoming + 2, births, production])

    def test_birth_pregnancy_calf_chain_and_capacity(self):
        self.create(); payload = self.delivery.load()['receipt']['payload']
        automatic = set(payload['automatic_calf_uuids'])
        self.assertEqual(len(automatic), 32)
        self.assertEqual(len({row.pregnancy_id for row in self.records('births.Birth')}), 49)
        self.assertEqual(self.records('births.Birth').filter(alive=False, calf__isnull=True).count(), 5)
        self.assertEqual(self.records('births.Birth').filter(alive=True).exclude(calf_id__in=automatic).count(), 12)
        for birth in self.records('births.Birth').select_related('pregnancy__breeding', 'mother', 'calf'):
            self.assertEqual(birth.pregnancy.status, 'FINISHED')
            self.assertEqual(birth.pregnancy.animal_id, birth.mother_id)
            self.assertLessEqual(birth.pregnancy.breeding.date, birth.pregnancy.diagnosis_date)
            self.assertLessEqual(birth.pregnancy.diagnosis_date, birth.birth_date)
            if str(birth.calf_id) in automatic:
                self.assertEqual(birth.calf.organization_id, birth.mother.organization_id)
                self.assertEqual(birth.calf.mother_id, birth.mother_id)
                self.assertEqual(birth.calf.father_id, birth.pregnancy.breeding.male_id)
                self.assertEqual((birth.calf.farm_id, birth.calf.lot_id), (birth.mother.farm_id, birth.mother.lot_id))
                self.assertEqual(birth.calf.birth_date, birth.birth_date)
        for lot in Lot.objects.filter(organization_id__in=self.org_ids):
            self.assertLessEqual(self.records('animals.Animal').filter(lot=lot).count(), lot.capacity)

    def test_dashboard_uses_real_latest_weights_and_forecasts(self):
        self.create()
        for index, (_, code, _, _, _, total) in enumerate(PLAN):
            context = owner_context(Organization.objects.get(code=code))
            summary = DashboardSelector.summary(context)
            w, _, sales, existing, inside, _ = QUOTAS[index]
            self.assertEqual(summary['total_animals'], total)
            self.assertEqual(summary['active_animals'], total - sales)
            self.assertEqual(summary['pregnancies'], inside + 1)
            self.assertEqual(summary['upcoming_births'], inside)
            self.assertEqual(len(DashboardSelector.upcoming_births(context)), inside)
            today = get_business_today(context)
            forecasts = self.records('pregnancy.Pregnancy').filter(organization=context.organization, status='ACTIVE')
            self.assertTrue(forecasts.filter(expected_birth=today + timedelta(days=31)).exists())
            if inside:
                self.assertTrue(forecasts.filter(expected_birth=today).exists())
                self.assertTrue(forecasts.filter(expected_birth=today + timedelta(days=30)).exists())
            self.assertEqual(summary['births_this_month'], RESERVES[index] + existing + 1)
            if w == 0:
                self.assertIsNone(summary['average_weight'])
                self.assertEqual(DashboardSelector.upcoming_births(context), [])
            else:
                expected = Decimal(420 + index * 25) + Decimal(3) * Decimal(w // 2 - 1) / Decimal(2)
                self.assertAlmostEqual(summary['average_weight'], expected, places=6)
            self.assertTrue(self.records('animals.Animal').filter(organization=context.organization, weights__isnull=True).exists())

    def test_chronology_tenant_roles_units_and_vaccination_variants(self):
        self.create()
        for label in D4_LABELS:
            for row in self.records(label):
                animal = getattr(row, 'animal', None) or getattr(row, 'mother', None)
                self.assertEqual(row.organization_id, animal.organization_id)
        for row in self.records('weights.Weight'):
            self.assertGreater(row.weight, 0); self.assertGreaterEqual(row.date, row.animal.birth_date)
        self.assertEqual(len(set(self.records('weights.Weight').values_list('animal_id', 'date'))), 62)
        for row in self.records('production.ProductionRecord'):
            self.assertEqual(row.unit, 'L'); self.assertEqual(row.production_type.code, 'MILK')
            self.assertEqual(row.animal.species.code, 'BOV')
            self.assertIsNotNone(row.recorded_at.tzinfo); self.assertLessEqual(row.recorded_at, timezone.now())
        for org in Organization.objects.filter(pk__in=self.org_ids):
            today = get_business_today(owner_context(org)); vaccines = self.records('vaccinations.Vaccination').filter(organization=org)
            self.assertTrue(vaccines.filter(next_application_date__lt=today).exists())
            self.assertTrue(vaccines.filter(next_application_date=today).exists())
            self.assertTrue(vaccines.filter(next_application_date__gt=today).exists())
            self.assertTrue(vaccines.filter(next_application_date__isnull=True).exists())
        for row in self.records('animal_movements.AnimalMovement').filter(movement_type__code='SALE'):
            row.animal.refresh_from_db()
            self.assertEqual(row.animal.status.code, 'SOLD'); self.assertIsNone(row.animal.farm_id); self.assertIsNone(row.animal.lot_id)

    def test_no_outside_changes_and_parent_receipts_preserved(self):
        self.create(); after = _snapshot()
        for label, rows in self.before.items():
            for identifier, row in rows.items():
                if label == 'animals.Animal' and str(row['organization_id']) in self.org_ids:
                    continue
                self.assertEqual(after[label][identifier], row)
        self.assertEqual((self.d2.final.read_bytes(), self.d3.final.read_bytes()), self.parent_bytes)

    def test_idempotency_and_dry_run_never_write_or_rotate_credentials(self):
        self.create(); before = _snapshot(); receipt = self.delivery.final.read_bytes()
        with patch('apps.organizations.demo.d2.secrets.token_urlsafe') as generate:
            self.assertEqual(self.create()['state'], 'recognized-D4')
            self.assertEqual(self.create(dry_run=True)['state'], 'recognized-D4')
            generate.assert_not_called()
        self.assertEqual(_snapshot(), before)
        self.assertEqual(self.delivery.final.read_bytes(), receipt)
        self.assertEqual((self.d2.final.read_bytes(), self.d3.final.read_bytes()), self.parent_bytes)

    def test_fresh_dry_run_does_not_call_writers(self):
        from apps.organizations.demo import d4
        with patch.object(d4.BirthService, 'create') as births, patch.object(self.delivery, 'stage') as stage:
            self.assertEqual(self.create(dry_run=True)['state'], 'fresh-D4-dry-run')
            births.assert_not_called(); stage.assert_not_called()
        self.assertEqual(_snapshot(), self.before)

    def test_intermediate_failures_roll_back_all_tenants_and_new_calves(self):
        from apps.organizations.demo import d4
        for service, fail_at in [(d4.BirthService, 10), (d4.ProductionService, 8), (d4.AnimalMovementService, 3)]:
            original = service.create; count = 0
            def fail(context, data):
                nonlocal count
                count += 1
                if count == fail_at: raise RuntimeError('private test payload')
                return original(context, data)
            with patch.object(service, 'create', side_effect=fail):
                with self.assertRaises(D4Error) as caught: self.create()
            self.assertNotIn('private test payload', str(caught.exception))
            self.assertEqual(_snapshot(), self.before)
            self.assertFalse(self.delivery.pending.exists())

    def test_stage_and_commit_failures_leave_no_database_residue(self):
        with patch.object(self.delivery, 'stage', side_effect=OSError('test')):
            with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), self.before)
        with patch.object(connections['default'], 'commit', side_effect=OperationalError('test')):
            with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), self.before)
        with self.assertRaises(D4Error): self.create()  # Unconfirmed staged receipt cannot adopt rolled-back data.

    def test_publication_failure_recovers_same_ciphertext(self):
        with patch.object(self.delivery, 'publish', side_effect=OSError('test')):
            with self.assertRaises(DeliveryPending): self.create()
        before = _snapshot(); pending = self.delivery.pending.read_bytes()
        self.assertEqual(self.create()['state'], 'recognized-D4')
        self.assertEqual(self.delivery.final.read_bytes(), pending)
        self.assertEqual(_snapshot(), before)

    def test_altered_dataset_rejected_without_repair(self):
        self.create(); self.records('weights.Weight').filter(pk=self.records('weights.Weight').first().pk).update(notes='Altered')
        before = _snapshot()
        with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), before)

    def test_missing_receipt_rejects_partial_or_unknown_dataset(self):
        self.create(); self.delivery.final.unlink(); before = _snapshot()
        with self.assertRaises(ValueError): self.create()
        self.assertEqual(_snapshot(), before)

    def test_required_catalog_missing_is_not_repaired(self):
        WeighingMethod.objects.filter(code='SCALE').update(is_active=False)
        before = _snapshot()
        with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), before)

    def test_production_plan_requires_exact_bov_hol_and_milk_l(self):
        from apps.organizations.demo import d4
        species = Species.objects.get(code='BOV')
        Breed.objects.create(species=species, code='OTHER_BREED', name='Explicit incompatible demo-plan fixture')
        before = _snapshot()
        with self.assertRaises(D4Error): d4._catalogs('BOV', 'OTHER_BREED', 'SCALE', 'NAT')
        self.assertEqual(_snapshot(), before)
        ProductionType.objects.filter(code='MILK').update(default_unit='kg')
        before = _snapshot()
        with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), before)

    def test_services_receive_owner_context(self):
        from apps.organizations.demo import d4
        original = d4.BirthService.create; calls = []
        def inspect(context, data):
            self.assertEqual(context.membership.role, 'OWNER')
            self.assertEqual(context.membership.organization_id, context.organization.pk)
            self.assertEqual(context.membership.user_id, context.user.pk)
            calls.append(data.pregnancy_id)
            return original(context, data)
        with patch.object(d4.BirthService, 'create', side_effect=inspect): self.create()
        self.assertEqual(len(set(calls)), 49)

    def test_protected_mutation_during_staging_rolls_back(self):
        def mutate(_bundle):
            Animal.objects.filter(organization=self.protected).update(name='Changed')
        with patch.object(self.delivery, 'stage', side_effect=mutate):
            with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), self.before)

    def test_command_write_remains_blocked(self):
        import os
        with patch.dict(os.environ, {'AGROCORE_ENABLE_DEMO_WRITES': '1'}):
            with self.assertRaises(CommandError): call_command('seed_demo_ranches', '--write', stdout=io.StringIO())
        self.assertEqual(_snapshot(), self.before)

    def test_manifest_tracks_all_records_and_approved_transitions(self):
        self.create(); payload = self.delivery.load()['receipt']['payload']
        self.assertEqual(len(payload['automatic_calf_uuids']), 32)
        self.assertEqual(len(payload['transitions']), 9)
        self.assertEqual(set(payload['inventory']), {'animals.Animal', *D4_LABELS})
        for label, inventory in payload['inventory'].items():
            self.assertEqual(len(inventory['rows']), inventory['count'])
            for row in inventory['rows']:
                self.assertIn(row['organization_id'], self.org_ids); self.assertTrue(row['id'])
        for transition in payload['transitions'].values():
            self.assertIsNone(transition['after']['lot_id'])
            self.assertNotEqual(transition['before']['status_id'], transition['after']['status_id'])

    def test_cross_tenant_payload_rejected_and_everything_rolled_back(self):
        from apps.organizations.demo import d4
        original = d4.WeightService.create
        protected_animal = Animal.objects.get(organization=self.protected)
        def cross(context, data):
            return original(context, data.model_copy(update={'animal_id': protected_animal.pk}))
        with patch.object(d4.WeightService, 'create', side_effect=cross):
            with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), self.before)

    def test_tampered_receipt_rejected_without_adopting_data(self):
        import json
        self.create(); bundle = self.delivery.load()
        bundle['receipt']['payload']['stage'] = 'D4-partial'
        self.delivery.final.write_bytes(self.delivery.cipher.encrypt(json.dumps(bundle).encode()))
        before = _snapshot()
        with self.assertRaises(D4Error): self.create()
        self.assertEqual(_snapshot(), before)
