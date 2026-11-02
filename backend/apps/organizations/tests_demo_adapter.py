"""D6C-1 certification: only the strict disposable D2 SQLite destination."""
from contextlib import closing
import importlib
from io import StringIO
import json
import secrets
import shutil
import sqlite3
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import Client, TransactionTestCase, override_settings

from apps.accounts.models import User, Membership
from apps.animals.models import Animal
from apps.catalogs.models import Species, Breed, Gender, AnimalStatus, FarmType, WeighingMethod, BreedingType, MovementType, ProductionType
from apps.organizations.models import Organization
from .demo import backup, d2, d3, d4, rehearsal_adapter as adapter
from .demo.windows_acl import restrict_directory


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class AdapterTests(TransactionTestCase):
    def setUp(self):
        self.path = d2.test_database()
        self.root = self.path.parent
        restrict_directory(self.root)
        restrict_directory(self.path)
        self.protected = Organization.objects.create(id=backup.PROTECTED, name='Rancho los Hermanos', code='RLH')
        self.roble = Organization.objects.create(name='Rancho El Roble', code='RER')
        self.old_user = User.objects.create_user(email='protected@example.com', password=secrets.token_urlsafe(32))
        Membership.objects.create(user=self.old_user, organization=self.protected, role='OWNER', is_default=True)
        species = Species.objects.create(code='BOV', name='Explicit species fixture')
        Breed.objects.create(code='HOL', species=species, name='Explicit breed fixture')
        for model, code, extra in (
            (Gender, 'F', {}), (Gender, 'M', {}), (AnimalStatus, 'ACTIVE', {}), (AnimalStatus, 'SOLD', {}),
            (FarmType, 'RANCH', {}), (MovementType, 'TRANSFER', {}), (MovementType, 'SALE', {}),
            (ProductionType, 'MILK', {'default_unit': 'L'}), (WeighingMethod, 'SCALE', {}), (BreedingType, 'NAT', {}),
        ):
            model.objects.get_or_create(code=code, defaults={'name': code, **extra})
        self.before = d2._existing_database_snapshot()
        connections['default'].close()
        self.source = self.root / ('original-' + uuid4().hex + '.sqlite3')
        backup.copy_database(self.path, self.source)
        self.addCleanup(self.source.unlink)
        self.storage = self.root / ('storage-' + uuid4().hex)
        self.addCleanup(shutil.rmtree, self.storage)
        run = str(uuid4())
        backup.prepare(self.source, self.storage, run)
        self.receipt_file = self.storage / 'rehearsals' / run / 'receipt.json'
        self.backup_file = self.storage / 'backups' / run / 'database.sqlite3'
        # Explicit fixture-only relocation into D2's canonical disposable target.
        # No guard is patched and neither persistent path is touched.
        self.path.unlink()
        backup.copy_database(self.receipt_file.parent / 'database.sqlite3', self.path)
        self.binding = adapter.bind_verified_files(self.source, self.path, self.backup_file, self.receipt_file)
        self.directories = [self.root / ('delivery-D' + str(number) + '-' + uuid4().hex) for number in (2, 3, 4)]
        for directory in self.directories:
            directory.mkdir()
            self.addCleanup(shutil.rmtree, directory)
        self.encryption_key = secrets.token_bytes(32)
        self.signing_key = secrets.token_bytes(32)
        self.deliveries = adapter.delivery_set(self.directories, encryption_key=self.encryption_key)
        ledger = self.root / ('ledger-' + uuid4().hex)
        self.addCleanup(shutil.rmtree, ledger)
        self.authority = adapter.DisposableAuthority(ledger)

    def run_adapter(self, *, recovery=False, dry_run=False, token=None):
        if token is None and not dry_run:
            token = self.authority.issue(self.binding, recovery=recovery)
        return adapter.run_disposable(self.binding, self.authority, token, self.deliveries,
            signing_key=self.signing_key, recovery=recovery, dry_run=dry_run)

    def assert_protected(self):
        after = d2._existing_database_snapshot()
        for label, rows in self.before.items():
            for identifier, row in rows.items():
                self.assertEqual(after[label][identifier], row)

    def test_dry_run_no_sql_writes_credentials_or_token_consumption(self):
        from .tests_demo_d5 import no_sql_writes
        before = backup.digest(self.path)
        with no_sql_writes(), patch.object(self.authority, 'consume') as consume, patch('apps.organizations.demo.d2.secrets.token_urlsafe') as passwords:
            self.assertEqual(self.run_adapter(dry_run=True)['state'], 'read-only')
            consume.assert_not_called()
            passwords.assert_not_called()
        self.assertEqual(backup.digest(self.path), before)
        self.assert_protected()
        self.assertFalse(list(self.authority.directory.iterdir()))

    def test_original_alias_rejected(self):
        with self.assertRaises(d2.D2Error):
            adapter.bind_verified_files(self.source, self.source, self.backup_file, self.receipt_file)

    def test_hardlink_rejected(self):
        linked = self.root / ('linked-' + uuid4().hex)
        linked.hardlink_to(self.source)
        try:
            with self.assertRaises(ValueError):
                adapter.identity(linked)
        finally:
            linked.unlink()

    def test_replacement_after_preflight_rejected(self):
        connections['default'].close()
        old = self.root / ('old-' + uuid4().hex)
        self.path.rename(old)
        try:
            backup.copy_database(old, self.path)
            with self.assertRaises(d2.D2Error):
                self.run_adapter()
        finally:
            old.unlink()

    def test_pin_prevents_replacement(self):
        with adapter.pinned_copy(self.binding):
            with self.assertRaises(OSError):
                self.path.rename(self.root / 'unexpected.sqlite3')

    def test_invalid_receipt_rejected(self):
        receipt = json.loads(self.receipt_file.read_text())
        receipt['rehearsal_sha256'] = '0' * 64
        self.receipt_file.write_text(json.dumps(receipt))
        with self.assertRaises(d2.D2Error):
            adapter.bind_verified_files(self.source, self.path, self.backup_file, self.receipt_file)

    def test_receipt_changed_after_binding_rejected(self):
        self.receipt_file.write_text('{}')
        with self.assertRaises(d2.D2Error):
            self.run_adapter()

    def test_bad_authorization_rejected(self):
        token = self.authority.issue(self.binding)
        token['signature'] = '0' * 64
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)
        self.assert_protected()
        self.assertEqual(Organization.objects.count(), 2)

    def test_expired_authorization_rejected(self):
        with patch.object(adapter.time, 'time', return_value=1000):
            token = self.authority.issue(self.binding)
        with patch.object(adapter.time, 'time', return_value=2000):
            with self.assertRaises(d2.D2Error):
                self.run_adapter(token=token)

    def test_other_authority_rejected(self):
        token = self.authority.issue(self.binding)
        self.authority.key = secrets.token_bytes(32)
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)

    def test_signed_wrong_file_rejected(self):
        token = self.authority.issue(self.binding)
        import hashlib,hmac
        token['payload']['copy'] = dict(self.binding.copy_identity, file_id=self.binding.copy_identity['file_id'] + 1)
        token['signature'] = hmac.new(self.authority.key, adapter.canonical_json(token['payload']).encode(), hashlib.sha256).hexdigest()
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)

    def test_before_commit_failure_burns_authorization(self):
        token = self.authority.issue(self.binding)
        with patch.object(d2, 'create_organization', side_effect=RuntimeError('injected')):
            with self.assertRaises(d2.D2Error):
                self.run_adapter(token=token)
        self.assertEqual(Organization.objects.count(), 2)
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)
        self.assert_protected()

    def test_d3_failure_preserves_d2_and_preexisting(self):
        with patch.object(d3.FarmService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(d3.D3Error):
                self.run_adapter()
        self.assertEqual(Organization.objects.count(), 7)
        self.assertEqual(Animal.objects.count(), 0)
        self.assertTrue(self.deliveries[0].final.exists())
        self.assert_protected()

    def test_d4_failure_preserves_d3_and_preexisting(self):
        with patch.object(d4.WeightService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(d4.D4Error):
                self.run_adapter()
        self.assertEqual(Animal.objects.count(), 293)
        self.assertFalse(self.deliveries[2].final.exists())
        self.assert_protected()

    def test_postcommit_publication_recovers_same_ciphertext(self):
        with patch.object(self.deliveries[0], 'publish', side_effect=OSError('injected')):
            with self.assertRaises(d2.DeliveryPending):
                self.run_adapter()
        ciphertext = self.deliveries[0].pending.read_bytes()
        self.deliveries = adapter.delivery_set(self.directories, encryption_key=self.encryption_key)
        with patch('apps.organizations.demo.d2.secrets.token_urlsafe') as passwords:
            self.run_adapter(recovery=True)
            passwords.assert_not_called()
        self.assertEqual(self.deliveries[0].final.read_bytes(), ciphertext)
        self.assertEqual(Animal.objects.count(), 325)
        self.assert_protected()

    def test_complete_idempotence_tenants_login_context(self):
        self.run_adapter()
        ciphertexts = [delivery.final.read_bytes() for delivery in self.deliveries]
        self.run_adapter(recovery=True)
        self.assertEqual([delivery.final.read_bytes() for delivery in self.deliveries], ciphertexts)
        self.assertEqual(Animal.objects.count(), 325)
        entries = self.deliveries[0].load()['credentials']
        client = Client()
        for entry in entries:
            response = client.post('/api/auth/login', data=json.dumps({'email': entry['email'], 'password': entry['password']}), content_type='application/json')
            self.assertEqual(response.status_code, 200)
            token = response.json()['access']
            response = client.get('/api/common/context', HTTP_AUTHORIZATION='Bearer ' + token)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['organization']['id'], entry['organization_uuid'])
            self.assertEqual(response.json()['can_write'], entry['role'] != 'VIEWER')
            foreign = Animal.objects.exclude(organization_id=entry['organization_uuid']).first()
            response = client.get('/api/animals/' + str(foreign.pk), HTTP_AUTHORIZATION='Bearer ' + token)
            self.assertEqual(response.status_code, 404)
            user = User.objects.get(pk=entry['user_uuid'])
            self.assertEqual(Membership.objects.filter(user=user).count(), 1)
        self.assert_protected()

    def test_local_and_production_cannot_activate_adapter(self):
        for module in ('config.settings.local', 'config.settings.production', 'config.settings.demo_rehearsal'):
            with override_settings(SETTINGS_MODULE=module):
                with self.assertRaises(d2.D2Error):
                    self.run_adapter(dry_run=True)

    def test_write_settings_and_real_command_remain_disabled(self):
        with self.assertRaises(ImproperlyConfigured):
            importlib.import_module('config.settings.demo_rehearsal_write')
        with self.assertRaises(CommandError):
            call_command('seed_demo_ranches', write=True, stdout=StringIO())

    def test_reused_authorization_rejected_across_authority_restart(self):
        token = self.authority.issue(self.binding)
        self.authority.consume(token, self.binding, recovery=False)
        restarted = adapter.DisposableAuthority(self.authority.directory, authority_key=self.authority.key)
        with self.assertRaises(d2.D2Error):
            restarted.consume(token, self.binding, recovery=False)

    def test_signed_wrong_receipt_rejected(self):
        import hashlib,hmac
        token = self.authority.issue(self.binding)
        token['payload']['receipt'] = '0' * 64
        token['signature'] = hmac.new(self.authority.key, adapter.canonical_json(token['payload']).encode(), hashlib.sha256).hexdigest()
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)

    def test_d3_postcommit_publication_recovers_without_duplicates(self):
        with patch.object(self.deliveries[1], 'publish', side_effect=OSError('injected')):
            with self.assertRaises(d2.DeliveryPending):
                self.run_adapter()
        ciphertext = self.deliveries[1].pending.read_bytes()
        self.assertEqual(Animal.objects.count(), 293)
        self.run_adapter(recovery=True)
        self.assertEqual(self.deliveries[1].final.read_bytes(), ciphertext)
        self.assertEqual(Animal.objects.count(), 325)
        self.assert_protected()

    def test_d4_postcommit_publication_recovers_without_duplicates(self):
        with patch.object(self.deliveries[2], 'publish', side_effect=OSError('injected')):
            with self.assertRaises(d2.DeliveryPending):
                self.run_adapter()
        ciphertext = self.deliveries[2].pending.read_bytes()
        self.assertEqual(Animal.objects.count(), 325)
        self.run_adapter(recovery=True)
        self.assertEqual(self.deliveries[2].final.read_bytes(), ciphertext)
        self.assertEqual(Animal.objects.count(), 325)
        self.assert_protected()

    def test_precommit_pending_ciphertext_is_not_adopted(self):
        stage = self.deliveries[0].stage
        def fail_after_stage(bundle):
            stage(bundle)
            raise OSError('injected before commit')
        with patch.object(self.deliveries[0], 'stage', side_effect=fail_after_stage):
            with self.assertRaises(d2.D2Error):
                self.run_adapter()
        ciphertext = self.deliveries[0].pending.read_bytes()
        self.assertEqual(Organization.objects.count(), 2)
        with self.assertRaises(d2.D2Error):
            self.run_adapter(recovery=True)
        self.assertEqual(self.deliveries[0].pending.read_bytes(), ciphertext)
        self.assertEqual(Organization.objects.count(), 2)
        self.assert_protected()

    def test_candidate_settings_exact_target_and_no_local_activation(self):
        for module in ('config.settings.local', 'config.settings.production', 'unknown'):
            with self.assertRaises(d2.D2Error):
                adapter.candidate_write_configuration(self.binding, settings_module=module)
        configuration = adapter.candidate_write_configuration(self.binding, settings_module='config.settings.demo_rehearsal_write')
        self.assertEqual(configuration['default']['NAME'], str(self.path))
        self.assertEqual(d2.test_database(), self.path)

    def test_recovery_rejects_preexisting_data_changes(self):
        with patch.object(d3.FarmService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(d3.D3Error):
                self.run_adapter()
        Organization.objects.filter(pk=self.protected.pk).update(description='tampered')
        with self.assertRaises(d2.D2Error):
            self.run_adapter(recovery=True)
        self.assertEqual(Animal.objects.count(), 0)

    def test_exclusive_sqlite_lock_survives_phase_commit(self):
        actual = self.deliveries[0].publish
        attempts = []
        def verify_exclusion():
            with closing(sqlite3.connect(self.path, timeout=0)) as contender:
                with self.assertRaises(sqlite3.OperationalError):
                    contender.execute('BEGIN IMMEDIATE')
                attempts.append(True)
            actual()
        with patch.object(self.deliveries[0], 'publish', side_effect=verify_exclusion):
            self.run_adapter()
        self.assertEqual(attempts, [True])

    def test_existing_writer_rejected_without_domain_writes(self):
        token = self.authority.issue(self.binding)
        connections['default'].close()
        with closing(sqlite3.connect(self.path, timeout=0)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):
                self.run_adapter(token=token)
            writer.rollback()
        self.assertEqual(Organization.objects.count(), 2)
        self.assert_protected()

    def test_authorization_ledger_replaced_rejected(self):
        token = self.authority.issue(self.binding)
        moved = self.root / ('moved-' + uuid4().hex)
        self.authority.directory.rename(moved)
        self.addCleanup(shutil.rmtree, moved)
        backup.private_directory(self.authority.directory)
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)
        self.assertEqual(Organization.objects.count(), 2)

    def test_change_after_authorization_is_rejected(self):
        token = self.authority.issue(self.binding)
        Organization.objects.filter(pk=self.protected.pk).update(description='changed after authorization')
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)
        self.assertEqual(Organization.objects.count(), 2)

    def test_complete_dry_run_verifies_parent_chain_without_writes(self):
        from .tests_demo_d5 import no_sql_writes
        self.run_adapter()
        before = backup.digest(self.path)
        with no_sql_writes(), patch.object(self.authority, 'consume') as consume:
            result = self.run_adapter(recovery=True, dry_run=True)
            consume.assert_not_called()
        self.assertEqual(result['D4']['state'], 'recognized-D4')
        self.assertEqual(backup.digest(self.path), before)

    def test_recovery_cannot_switch_encryption_key(self):
        with patch.object(self.deliveries[0], 'publish', side_effect=OSError('injected')):
            with self.assertRaises(d2.DeliveryPending):
                self.run_adapter()
        ciphertext = self.deliveries[0].pending.read_bytes()
        self.deliveries = adapter.delivery_set(self.directories, encryption_key=secrets.token_bytes(32))
        with self.assertRaises(d2.D2Error):
            self.run_adapter(recovery=True)
        self.assertEqual(self.deliveries[0].pending.read_bytes(), ciphertext)
        self.assertEqual(Organization.objects.count(), 7)

    def test_missing_exact_catalog_rejected_before_write(self):
        # Mutation invalidates the D6B binding; catalog repair/adoption is forbidden.
        Species.objects.filter(code='BOV').update(is_active=False)
        with self.assertRaises(d2.D2Error):
            self.run_adapter()
        self.assertEqual(Organization.objects.count(), 2)

    def test_signed_nonfinite_expiry_rejected(self):
        import hashlib,hmac
        for value in (float('nan'), float('inf'), float('-inf')):
            token = self.authority.issue(self.binding)
            token['payload']['expires'] = value
            token['signature'] = hmac.new(self.authority.key, adapter.canonical_json(token['payload']).encode(), hashlib.sha256).hexdigest()
            with self.assertRaises(d2.D2Error):
                self.run_adapter(token=token)
        self.assertEqual(Organization.objects.count(), 2)

    def test_ledger_flush_failure_never_opens_domain_writes(self):
        token = self.authority.issue(self.binding)
        with patch.object(adapter.os, 'fsync', side_effect=OSError('injected ledger flush')):
            with self.assertRaises(d2.D2Error):
                self.run_adapter(token=token)
        with self.assertRaises(d2.D2Error):
            self.run_adapter(token=token)
        self.assertEqual(Organization.objects.count(), 2)
        self.assert_protected()

    def test_cold_recovery_reconstructs_binding_without_reusing_authorization(self):
        bootstrap = self.authority.issue(self.binding)
        with patch.object(self.deliveries[1], 'publish', side_effect=OSError('injected')):
            with self.assertRaises(d2.DeliveryPending):
                self.run_adapter(token=bootstrap)
        ciphertexts = [delivery.final.read_bytes() if delivery.final.exists() else delivery.pending.read_bytes()
                       for delivery in self.deliveries[:2]]
        ledger, authority_key = self.authority.directory, self.authority.key
        self.binding = None
        self.authority = adapter.DisposableAuthority(ledger, authority_key=authority_key)
        self.deliveries = adapter.delivery_set(self.directories, encryption_key=self.encryption_key)
        self.binding = self.authority.recover_binding(bootstrap, backup_file=self.backup_file, receipt_file=self.receipt_file)
        with self.assertRaises(d2.D2Error):
            self.run_adapter(recovery=True, token=bootstrap)
        with patch('apps.organizations.demo.d2.secrets.token_urlsafe') as passwords:
            self.run_adapter(recovery=True)
            passwords.assert_not_called()
        self.assertEqual([delivery.final.read_bytes() for delivery in self.deliveries[:2]], ciphertexts)
        self.assertEqual(Animal.objects.count(), 325)
        self.assert_protected()

    def test_authorization_cannot_move_to_another_ledger(self):
        token = self.authority.issue(self.binding)
        ledger = self.root / ('another-ledger-' + uuid4().hex)
        self.addCleanup(shutil.rmtree, ledger)
        another = adapter.DisposableAuthority(ledger, authority_key=self.authority.key)
        with self.assertRaises(d2.D2Error):
            another.consume(token, self.binding, recovery=False)

    def test_cold_recovery_requires_consumed_signed_provenance(self):
        token = self.authority.issue(self.binding)
        with self.assertRaises(d2.D2Error):
            self.authority.recover_binding(token, backup_file=self.backup_file, receipt_file=self.receipt_file)
