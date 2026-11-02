"""D6C-2B.1 private provisioning on disposable SQLite only."""
from io import StringIO
import json
import shutil
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings

from . import tests_demo_adapter as fixture
from .demo import authorization_storage as storage, backup, rehearsal_command as runtime
from .demo.rehearsal_locations import Locations
from .demo.windows_acl import verify_private


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class AuthorizationStorageTests(TransactionTestCase):
    def setUp(self):
        fixture.AdapterTests.setUp(self)
        run = json.loads(self.receipt_file.read_text())['run_id']
        self.plan = Locations(run, self.source, self.path, self.backup_file, self.receipt_file,
                              self.root / ('controlled-' + run), True)
        backup.private_directory(self.plan.artifact_root)
        self.addCleanup(shutil.rmtree, self.plan.artifact_root)
        override = override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing', DEMO_CONTROLLED_TEST_LOCATIONS=self.plan)
        override.enable()
        self.addCleanup(override.disable)

    def test_prepare_private_distinct_keys_empty_ledger_no_sqlite_changes(self):
        from .tests_demo_d5 import no_sql_writes
        before = [backup.digest(p) for p in (self.source, self.path)]
        output = StringIO()
        with no_sql_writes():
            call_command('prepare_demo_authorization', run_id=self.plan.run_id, stdout=output)
        authority = runtime._Authority(self.plan)
        self.assertEqual(len(set(authority.keys.values())), 3)
        for name, value in authority.keys.items():
            self.assertEqual(len(value), 32)
            self.assertNotIn(value.hex(), output.getvalue())
            verify_private(self.plan.keys / (name + '.key'))
        self.assertEqual(list(self.plan.grants.iterdir()), [])
        self.assertEqual(list(self.plan.ledger.iterdir()), [])
        self.assertTrue(all(not list(p.iterdir()) for p in self.plan.deliveries))
        self.assertEqual(before, [backup.digest(p) for p in (self.source, self.path)])
        runtime.run_command(self.plan, execute=False)
        with self.assertRaises(ValueError):
            runtime.run_command(self.plan, execute=True)

    def test_repeat_rejected_without_rotation(self):
        storage.prepare(self.plan.run_id)
        before = {p.name: p.read_bytes() for p in self.plan.keys.iterdir()}
        with self.assertRaises(ValueError):
            storage.prepare(self.plan.run_id)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.plan.keys.iterdir()})

    def test_key_write_failure_leaves_partial_rejected_no_grant(self):
        with patch.object(storage.os, 'fsync', side_effect=OSError('simulated secret-like payload')):
            with self.assertRaises(CommandError) as error:
                call_command('prepare_demo_authorization', run_id=self.plan.run_id)
        self.assertNotIn('secret-like', str(error.exception))
        with self.assertRaises(ValueError):
            storage.prepare(self.plan.run_id)
        self.assertFalse(any(self.plan.grants.iterdir()))
        self.assertFalse(any(self.plan.ledger.iterdir()))

    def test_bad_acl_rejected_not_repaired(self):
        storage.prepare(self.plan.run_id)
        import subprocess
        subprocess.run(['icacls', str(self.plan.keys), '/grant', '*S-1-1-0:(OI)(CI)R'],
                       check=True, capture_output=True)
        with self.assertRaises(Exception):
            runtime._Authority(self.plan)

    def test_altered_grant_rejected_no_consumption(self):
        storage.prepare(self.plan.run_id)
        from uuid import uuid4
        grant = self.plan.grants / (str(uuid4()) + '.json')
        grant.write_text(json.dumps({'payload': {}, 'signature': 'altered'}))
        with self.assertRaises(Exception):
            runtime._Authority(self.plan).verify(grant, live=True)
        self.assertEqual(list(self.plan.ledger.iterdir()), [])

    def test_divergent_copy_rejected_before_keys(self):
        with open(self.path, 'ab') as stream:
            stream.write(b'divergence')
        with self.assertRaises(ValueError):
            storage.prepare(self.plan.run_id)
        self.assertFalse(self.plan.keys.exists())

    def test_unknown_settings_rejected(self):
        with override_settings(SETTINGS_MODULE='config.settings.production'):
            with self.assertRaises(ValueError):
                storage.prepare(self.plan.run_id)
        self.assertFalse(self.plan.keys.exists())
