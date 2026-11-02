"""D6C-2A command executes synthetic copies only; no guard monkeypatching."""
import base64
from contextlib import closing
import hashlib
import hmac
from io import StringIO
import json
import secrets
import shutil
import sqlite3
import time
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import Client, TransactionTestCase, override_settings

from apps.accounts.models import User, Membership
from apps.animals.models import Animal
from apps.farms.models import Farm
from apps.organizations.models import Organization
from . import tests_demo_adapter as fixture
from .demo import backup, d2, d3, d4, rehearsal_adapter as adapter, rehearsal_command as runtime
from .demo.rehearsal_locations import Locations
from .demo.windows_acl import current_sid, verify_private


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class RehearsalCommandTests(TransactionTestCase):
    def setUp(self):
        fixture.AdapterTests.setUp(self)  # Genuine disposable D6B reference, same strict D2 DB guard.
        run = json.loads(self.receipt_file.read_text())['run_id']
        self.plan = Locations(run, self.source, self.path, self.backup_file, self.receipt_file,
                              self.root / ('controlled-' + run), True)
        self.addCleanup(shutil.rmtree, self.plan.artifact_root)
        backup.private_directory(self.plan.artifact_root)
        for path in (self.plan.keys, self.plan.grants, self.plan.ledger):
            chain = []
            item = path
            while item != self.plan.artifact_root:
                chain.append(item)
                item = item.parent
            for item in reversed(chain):
                backup.private_directory(item)
        self.material = {name: secrets.token_bytes(32) for name in ('authorization', 'encryption', 'dataset-signing')}
        for name, value in self.material.items():
            with open(self.plan.keys / (name + '.key'), 'xb') as stream:
                stream.write(value)
            verify_private(self.plan.keys / (name + '.key'))
        override = override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing', DEMO_CONTROLLED_TEST_LOCATIONS=self.plan)
        override.enable()
        self.addCleanup(override.disable)

    def grant(self, *, mode='execute', expires=None, changes=None):
        # Test fixture issuer ONLY: all files and credentials reside in disposable TEMP.
        payload = {'version': runtime.VERSION, 'run_id': self.plan.run_id, 'nonce': str(uuid4()),
            'expires': time.time() + 300 if expires is None else expires, 'mode': mode,
            'sid': current_sid(), 'copy': adapter.identity(self.plan.copy), 'original': adapter.identity(self.plan.original),
            'receipt': backup.digest(self.receipt_file), 'ledger': adapter.identity_directory(self.plan.ledger),
            'artifacts': runtime.artifact_digest(self.plan)}
        if changes:
            payload.update(changes)
        signature = hmac.new(self.material['authorization'], runtime.canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        path = self.plan.grants / (payload['nonce'] + '.json')
        with open(path, 'x', encoding='utf-8') as stream:
            json.dump({'payload': payload, 'signature': signature}, stream)
        return path

    def invoke(self, *, execute=True, authorization=None, resume=False, reference=None):
        output = StringIO()
        call_command('seed_demo_rehearsal', run_id=self.plan.run_id, execute=execute,
            authorization_file=str(authorization) if authorization else None, resume=resume,
            reference_authorization=str(reference) if reference else None, stdout=output)
        return output.getvalue()

    def assert_preserved(self):
        fixture.AdapterTests.assert_protected(self)

    def bundle(self, phase):
        directory = self.plan.deliveries[phase - 2]
        path = directory / ('d2.bundle' if (directory / 'd2.bundle').exists() else 'd2.pending')
        cipher = Fernet(base64.urlsafe_b64encode(self.material['encryption']))
        return json.loads(cipher.decrypt(path.read_bytes()))

    def test_default_dry_run_no_mutating_sql_artifacts_or_consumption(self):
        from .tests_demo_d5 import no_sql_writes
        before = backup.digest(self.path)
        with no_sql_writes(), patch.object(runtime._Authority, 'consume') as consume:
            self.assertIn('DRY-RUN', self.invoke(execute=False))
            consume.assert_not_called()
        self.assertEqual(backup.digest(self.path), before)
        self.assertFalse((self.plan.artifact_root / 'deliveries').exists())
        self.assertEqual(list(self.plan.ledger.iterdir()), [])

    def test_command_complete_quotas_login_context_tenant_isolation(self):
        grant = self.grant()
        old = connections['default']
        output = self.invoke(authorization=grant)
        self.assertIn('created-D4', output)
        self.assertIs(connections['default'], old)
        self.assertEqual(Organization.objects.count(), 7)
        self.assertEqual(User.objects.count(), 31)
        self.assertEqual(Membership.objects.count(), 31)
        self.assertEqual(Farm.objects.count(), 12)
        self.assertEqual(Animal.objects.count(), 325)
        for entry in self.bundle(2)['credentials']:
            client = Client()
            response = client.post('/api/auth/login', data={'email': entry['email'], 'password': entry['password']}, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            access = response.json()['access']
            context = client.get('/api/common/context', HTTP_AUTHORIZATION='Bearer ' + access)
            self.assertEqual(context.status_code, 200)
            self.assertEqual(context.json()['organization']['id'], entry['organization_uuid'])
            self.assertEqual(context.json()['can_write'], entry['role'] != 'VIEWER')
            foreign = Animal.objects.exclude(organization_id=entry['organization_uuid']).first()
            self.assertEqual(client.get('/api/animals/' + str(foreign.pk), HTTP_AUTHORIZATION='Bearer ' + access).status_code, 404)
            self.assertNotIn(entry['password'], output)
        self.assert_preserved()

    def test_authorization_required_and_environment_cannot_enable(self):
        with patch.dict('os.environ', {'AGROCORE_ENABLE_DEMO_WRITES': '1'}):
            with self.assertRaises(CommandError):
                self.invoke()
            with self.assertRaises(CommandError):
                call_command('seed_demo_ranches', write=True, stdout=StringIO())
        self.assertEqual(Organization.objects.count(), 2)

    def test_local_production_and_unknown_settings_reject_execution(self):
        grant = self.grant()
        for module in ('config.settings.local', 'config.settings.production', 'unknown'):
            with override_settings(SETTINGS_MODULE=module):
                with self.assertRaises(CommandError):
                    self.invoke(authorization=grant)
        self.assertEqual(list(self.plan.ledger.iterdir()), [])

    def test_wrong_run_file_receipt_sid_and_expiry_rejected(self):
        changes = ({'run_id': str(uuid4())}, {'copy': dict(adapter.identity(self.path), file_id=0)},
                   {'receipt': '0' * 64}, {'sid': 'S-1-5-18'}, {'expires': time.time() - 1}, {'expires': float('nan')})
        for change in changes:
            with self.assertRaises(CommandError):
                self.invoke(authorization=self.grant(changes=change))
        self.assertEqual(Organization.objects.count(), 2)
        self.assertEqual(list(self.plan.ledger.iterdir()), [])

    def test_tampered_signature_rejected(self):
        grant = self.grant()
        value = json.loads(grant.read_text())
        value['signature'] = '0' * 64
        grant.write_text(json.dumps(value))
        with self.assertRaises(CommandError):
            self.invoke(authorization=grant)

    def test_grant_outside_authorized_directory_rejected(self):
        grant = self.grant()
        other = self.root / grant.name
        grant.rename(other)
        self.addCleanup(other.unlink)
        with self.assertRaises(CommandError):
            self.invoke(authorization=other)

    def test_before_d2_commit_burns_nonce_and_rolls_back(self):
        grant = self.grant()
        with patch.object(d2, 'create_organization', side_effect=RuntimeError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        self.assertEqual(Organization.objects.count(), 2)
        with self.assertRaises(CommandError):
            self.invoke(authorization=grant)
        self.assert_preserved()

    def test_before_d3_commit_keeps_only_d2(self):
        grant = self.grant()
        with patch.object(d3.FarmService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        self.assertEqual(Organization.objects.count(), 7)
        self.assertEqual(Farm.objects.count(), 0)
        self.assert_preserved()

    def test_before_d4_commit_keeps_d3(self):
        grant = self.grant()
        with patch.object(d4.WeightService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        self.assertEqual(Animal.objects.count(), 293)
        self.assert_preserved()

    def test_d2_postcommit_recovers_same_ciphertext(self):
        self._publication_failure(2)

    def _publication_failure(self, phase):
        grant = self.grant()
        actual = runtime._Delivery.publish
        def fail_delivery(delivery):
            if delivery.directory.name == 'D' + str(phase):
                raise OSError('injected publication')
            return actual(delivery)
        with patch.object(runtime._Delivery, 'publish', fail_delivery):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        pending = self.plan.deliveries[phase - 2] / 'd2.pending'
        ciphertext = pending.read_bytes()
        with patch('apps.organizations.demo.d2.secrets.token_urlsafe') as passwords:
            self.invoke(authorization=self.grant(mode='resume'), resume=True, reference=grant)
            passwords.assert_not_called()
        self.assertEqual((pending.parent / 'd2.bundle').read_bytes(), ciphertext)
        self.assertEqual(Animal.objects.count(), 325)
        self.assert_preserved()

    def test_d3_postcommit_recovers_same_ciphertext(self):
        self._publication_failure(3)

    def test_d4_postcommit_recovers_same_ciphertext(self):
        self._publication_failure(4)

    def test_complete_repeat_requires_new_resume_grant_no_duplicates(self):
        grant = self.grant()
        self.invoke(authorization=grant)
        ciphertexts = [(directory / 'd2.bundle').read_bytes() for directory in self.plan.deliveries]
        with self.assertRaises(CommandError):
            self.invoke(authorization=grant)
        self.invoke(authorization=self.grant(mode='resume'), resume=True, reference=grant)
        self.assertEqual([(directory / 'd2.bundle').read_bytes() for directory in self.plan.deliveries], ciphertexts)
        self.assertEqual(Animal.objects.count(), 325)

    def test_corrupt_bundle_stops_without_cleanup(self):
        grant = self.grant()
        self.invoke(authorization=grant)
        path = self.plan.deliveries[0] / 'd2.bundle'
        path.write_bytes(b'corrupt')
        with self.assertRaises(CommandError):
            self.invoke(authorization=self.grant(mode='resume'), resume=True, reference=grant)
        self.assertEqual(path.read_bytes(), b'corrupt')
        self.assertEqual(Animal.objects.count(), 325)

    def test_resume_rejects_modified_preexisting_rows(self):
        grant = self.grant()
        with patch.object(d3.FarmService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        Organization.objects.filter(pk=self.protected.pk).update(description='tampered')
        with self.assertRaises(CommandError):
            self.invoke(authorization=self.grant(mode='resume'), resume=True, reference=grant)
        self.assertEqual(Animal.objects.count(), 0)

    def test_original_alias_plan_rejected(self):
        forged = Locations(self.plan.run_id, self.source, self.source, self.backup_file,
                           self.receipt_file, self.plan.artifact_root, True)
        with override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing', DEMO_CONTROLLED_TEST_LOCATIONS=forged):
            with self.assertRaises(CommandError):
                self.invoke(authorization=self.grant())

    def test_handoff_cannot_be_reused_or_forged(self):
        authority = runtime._Authority(self.plan)
        proof = authority.consume(self.grant(), self.binding, mode='execute')
        proof.claim(authority)
        with self.assertRaises(d2.D2Error):
            proof.claim(authority)
        with self.assertRaises(d2.D2Error):
            runtime._Consumption(None, authority, {})

    def test_keys_private_separate_and_missing_key_has_no_fallback(self):
        (self.plan.keys / 'encryption.key').unlink()
        with self.assertRaises(CommandError):
            self.invoke(authorization=self.grant())
        self.assertFalse((self.plan.artifact_root / 'deliveries').exists())

    def test_normal_guard_cannot_use_runtime_module_without_live_scope(self):
        with override_settings(SETTINGS_MODULE=runtime.RUNTIME):
            with self.assertRaises(d2.D2Error):
                d2.test_database()

    def test_no_generic_route_or_migration_options(self):
        from apps.organizations.management.commands.seed_demo_rehearsal import Command
        parser = Command().create_parser('manage.py', 'seed_demo_rehearsal')
        options = {name for action in parser._actions for name in action.option_strings}
        self.assertTrue(options.isdisjoint({'--database', '--reset', '--clean', '--force', '--migrate', '--write'}))

    def test_readonly_status_of_complete_dataset_consumes_nothing(self):
        grant = self.grant()
        self.invoke(authorization=grant)
        before = backup.digest(self.path)
        used = list(self.plan.ledger.iterdir())
        output = self.invoke(execute=False, reference=grant)
        self.assertIn('D4: complete', output)
        self.assertEqual(backup.digest(self.path), before)
        self.assertEqual(list(self.plan.ledger.iterdir()), used)

    def test_partial_unknown_dataset_rejected_without_consuming_resume_grant(self):
        grant = self.grant()
        with patch.object(d3.FarmService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        # Explicit fixture divergence; never inserted by the command itself.
        from apps.catalogs.models import FarmType
        org = Organization.objects.exclude(pk__in=(self.protected.pk, self.roble.pk)).first()
        Farm.objects.create(organization=org, farm_type=FarmType.objects.get(code='RANCH'), name='Unknown partial', code='UNKNOWN')
        next_grant = self.grant(mode='resume')
        with self.assertRaises(CommandError):
            self.invoke(authorization=next_grant, resume=True, reference=grant)
        self.assertFalse((self.plan.ledger / (next_grant.stem + '.used')).exists())
        self.assertEqual(Farm.objects.count(), 1)

    def test_unowned_extra_records_rejected_before_resume(self):
        grant = self.grant()
        with patch.object(d3.FarmService, 'create', side_effect=RuntimeError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        Organization.objects.create(name='Unowned extra', code='EXTRA')
        next_grant = self.grant(mode='resume')
        with self.assertRaises(CommandError):
            self.invoke(authorization=next_grant, resume=True, reference=grant)
        self.assertFalse((self.plan.ledger / (next_grant.stem + '.used')).exists())

    def test_nonce_flush_failure_never_opens_write_connection(self):
        grant = self.grant()
        with patch.object(runtime.os, 'fsync', side_effect=OSError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        self.assertEqual(Organization.objects.count(), 2)
        self.assertFalse((self.plan.artifact_root / 'deliveries').exists())

    def test_file_replacement_after_grant_rejected(self):
        grant = self.grant()
        connections['default'].close()
        old = self.root / ('previous-' + uuid4().hex)
        self.path.rename(old)
        try:
            backup.copy_database(old, self.path)
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        finally:
            old.unlink()

    def test_session_revoked_and_connection_restored_after_failure(self):
        captured = []
        actual = runtime._Session.__init__
        def capture(session, *args, **kwargs):
            actual(session, *args, **kwargs)
            captured.append(session)
        old = connections['default']
        with patch.object(runtime._Session, '__init__', capture), patch.object(d2, 'create_organization', side_effect=RuntimeError('injected')):
            with self.assertRaises(CommandError):
                self.invoke(authorization=self.grant())
        self.assertIs(connections['default'], old)
        self.assertEqual(len(captured), 1)
        with self.assertRaises(d2.D2Error):
            captured[0].validate()

    def test_malformed_duplicate_authorization_fields_rejected(self):
        grant = self.grant()
        grant.write_text('{"payload":{},"payload":{},"signature":"invalid"}')
        with self.assertRaises(CommandError):
            self.invoke(authorization=grant)

    def test_dedicated_runtime_namespace_on_synthetic_persistent_layout(self):
        # Exercise the production-format branch entirely in disposable TEMP.
        # Only the read-only location roots are redirected; no guards are patched.
        self.plan = Locations(self.plan.run_id, self.source,
            self.receipt_file.parent / 'database.sqlite3', self.backup_file, self.receipt_file, self.storage)
        for path in (self.plan.keys, self.plan.grants, self.plan.ledger):
            chain = []
            item = path
            while item != self.storage:
                chain.append(item)
                item = item.parent
            for item in reversed(chain):
                backup.private_directory(item)
        for name, value in self.material.items():
            with open(self.plan.keys / (name + '.key'), 'xb') as stream:
                stream.write(value)
        expected = {'default': {'ENGINE': 'django.db.backends.sqlite3',
            'NAME': self.plan.copy.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}}
        from django.conf import settings
        original_hash = backup.digest(self.source)
        with patch.object(backup, 'ORIGINAL', self.source), patch.object(backup, 'storage', return_value=self.storage), override_settings(
                SETTINGS_MODULE=runtime.RUNTIME, DATABASES=expected):
            with self.assertRaises(d2.D2Error):
                d2.test_database()  # The dedicated namespace alone cannot open the guard.
            self.assertIn('created-D4', self.invoke(authorization=self.grant()))
            self.assertEqual(settings.DATABASES['default']['NAME'], expected['default']['NAME'])
            with self.assertRaises(d2.D2Error):
                d2.test_database()  # Live permission was revoked after the command.
        self.assertEqual(backup.digest(self.source), original_hash)
        with closing(sqlite3.connect(self.plan.copy.as_uri() + '?mode=ro', uri=True)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM animals').fetchone()[0], 325)
        self.assertEqual(Animal.objects.count(), 0)  # Normal test destination stayed intact.

    def test_live_scope_blocks_other_sqlite_writers_between_commits(self):
        actual = runtime._Delivery.publish
        checked = []
        def check(delivery):
            with closing(sqlite3.connect(self.path, timeout=0)) as writer:
                with self.assertRaises(sqlite3.OperationalError):
                    writer.execute('BEGIN IMMEDIATE')
            checked.append(delivery.directory.name)
            actual(delivery)
        with patch.object(runtime._Delivery, 'publish', check):
            self.invoke(authorization=self.grant())
        self.assertEqual(checked, ['D2', 'D3', 'D4'])

    def test_precommit_pending_manifest_is_not_adopted(self):
        grant = self.grant()
        actual = runtime._Delivery.stage
        def fail(delivery, bundle):
            actual(delivery, bundle)
            if delivery.directory.name == 'D2':
                raise OSError('injected after staging before commit')
        with patch.object(runtime._Delivery, 'stage', fail):
            with self.assertRaises(CommandError):
                self.invoke(authorization=grant)
        pending = self.plan.deliveries[0] / 'd2.pending'
        ciphertext = pending.read_bytes()
        resume = self.grant(mode='resume')
        with self.assertRaises(CommandError):
            self.invoke(authorization=resume, resume=True, reference=grant)
        self.assertFalse((self.plan.ledger / (resume.stem + '.used')).exists())
        self.assertEqual(pending.read_bytes(), ciphertext)
        self.assertEqual(Organization.objects.count(), 2)
