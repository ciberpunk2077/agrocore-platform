"""Operational issuer certification: disposable files only."""
import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings

from . import tests_demo_authorization_storage as fixture
from .demo import authorization_storage, backup, grant_issuer as issuer, rehearsal_command as runtime


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class GrantIssuerTests(TransactionTestCase):
    def setUp(self):
        fixture.AuthorizationStorageTests.setUp(self)
        authorization_storage.prepare(self.plan.run_id)

    def issue(self, **kwargs):
        return issuer.issue(self.plan.run_id, confirmation=self.plan.run_id, **kwargs)

    def test_issue_no_database_writes_then_full_consumption_and_resume(self):
        from .tests_demo_d5 import no_sql_writes
        before = backup.digest(self.path)
        with no_sql_writes():
            grant = self.issue()
        self.assertEqual(before, backup.digest(self.path))
        self.assertEqual(list(self.plan.ledger.iterdir()), [])
        result = runtime.run_command(self.plan, execute=True, authorization_file=grant)
        self.assertEqual(result['D4']['state'], 'created-D4')
        with self.assertRaises(Exception):
            runtime.run_command(self.plan, execute=True, authorization_file=grant)
        resume = self.issue(reference=grant)
        after = backup.digest(self.path)
        runtime.run_command(self.plan, execute=True, authorization_file=resume, resume=True, reference=grant)
        self.assertEqual(after, backup.digest(self.path))

    def test_explicit_confirmation_required(self):
        with self.assertRaises(ValueError):
            issuer.issue(self.plan.run_id, confirmation='other')
        self.assertEqual(list(self.plan.grants.iterdir()), [])

    def test_lifetime_limits(self):
        for value in (0, -1, 121, True, float('nan')):
            with self.assertRaises(ValueError):
                self.issue(lifetime=value)

    def test_outstanding_grant_blocks_second_issue(self):
        self.issue()
        with self.assertRaises(Exception):
            self.issue()
        self.assertEqual(len(list(self.plan.grants.iterdir())), 1)

    def test_altered_grant_rejected(self):
        grant = self.issue()
        token = json.loads(grant.read_text())
        token['payload']['copy']['file_id'] += 1
        grant.write_text(json.dumps(token))
        with self.assertRaises(Exception):
            runtime._Authority(self.plan).verify(grant, live=True)
        self.assertEqual(list(self.plan.ledger.iterdir()), [])

    def test_expired_grant_rejected(self):
        grant = self.issue(lifetime=1)
        with patch.object(runtime.time, 'time', return_value=10**12):
            with self.assertRaises(Exception):
                runtime._Authority(self.plan).verify(grant, live=True)

    def test_wrong_sid_rejected(self):
        grant = self.issue()
        with patch.object(runtime, 'current_sid', return_value='wrong'):
            with self.assertRaises(Exception):
                runtime._Authority(self.plan).verify(grant, live=True)

    def test_fsync_failure_preserves_pending_blocks_retry(self):
        with patch.object(issuer.os, 'fsync', side_effect=OSError('private error')):
            with self.assertRaises(OSError):
                self.issue()
        self.assertEqual(len(list(self.plan.grants.glob('*.pending'))), 1)
        self.assertEqual(list(self.plan.grants.glob('*.json')), [])
        with self.assertRaises(Exception):
            self.issue()

    def test_publication_failure_preserves_pending(self):
        with patch.object(issuer.os, 'rename', side_effect=OSError('publication')):
            with self.assertRaises(OSError):
                self.issue()
        self.assertEqual(len(list(self.plan.grants.glob('*.pending'))), 1)
        self.assertEqual(list(self.plan.ledger.iterdir()), [])

    def test_unknown_ledger_rejected(self):
        (self.plan.ledger / 'unknown.used').write_text('unknown')
        with self.assertRaises(Exception):
            self.issue()
        self.assertEqual(list(self.plan.grants.iterdir()), [])

    def test_missing_key_rejected(self):
        (self.plan.keys / 'authorization.key').unlink()
        with self.assertRaises(Exception):
            self.issue()

    def test_original_command_blocked_and_no_auto_issuance(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo_ranches', write=True)
        runtime.run_command(self.plan, execute=False)
        self.assertEqual(list(self.plan.grants.iterdir()), [])

    def test_cli_sanitizes_failure(self):
        with patch('apps.organizations.management.commands.issue_demo_rehearsal_grant.issue', side_effect=ValueError('SECRET')):
            with self.assertRaises(CommandError) as error:
                call_command('issue_demo_rehearsal_grant', run_id=self.plan.run_id, confirm_run_id=self.plan.run_id)
        self.assertNotIn('SECRET', str(error.exception))

    def test_cli_reports_path_only(self):
        output = StringIO()
        call_command('issue_demo_rehearsal_grant', run_id=self.plan.run_id, confirm_run_id=self.plan.run_id, stdout=output)
        grant = next(self.plan.grants.glob('*.json'))
        token = json.loads(grant.read_text())
        self.assertNotIn(token['signature'], output.getvalue())
        self.assertNotIn('payload', output.getvalue())

    def test_concurrent_mutex_rejects_issuance(self):
        import threading
        from .demo.preflight import run_lock
        ready, release = threading.Event(), threading.Event()
        def holder():
            with run_lock(self.plan.receipt_file):
                ready.set()
                release.wait(10)
        thread = threading.Thread(target=holder)
        thread.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaises(ValueError):
                self.issue()
            self.assertEqual(list(self.plan.grants.iterdir()), [])
        finally:
            release.set()
            thread.join(5)

    def test_ledger_fsync_failure_burns_nonce_without_reissue(self):
        grant = self.issue()
        authority = runtime._Authority(self.plan)
        binding = runtime._binding(self.plan)
        before = backup.digest(self.path)
        with patch.object(runtime.os, 'fsync', side_effect=OSError('ledger failure')):
            with self.assertRaises(OSError):
                authority.consume(grant, binding, mode='execute')
        self.assertEqual(before, backup.digest(self.path))
        with self.assertRaises(FileExistsError):
            authority.consume(grant, binding, mode='execute')
        with self.assertRaises(ValueError):
            self.issue()

    def test_expiry_during_publication_preserves_pending(self):
        from time import time
        now = time()
        with patch.object(issuer.time, 'time', side_effect=[now, now + 121]):
            with self.assertRaises(ValueError):
                self.issue()
        self.assertEqual(len(list(self.plan.grants.glob('*.pending'))), 1)
