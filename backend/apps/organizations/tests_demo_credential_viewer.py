"""D7C: synthetic credentials only, no persistent viewer invocation."""
from dataclasses import replace
from unittest.mock import patch
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from .demo.credential_viewer import Selection, validated_accounts
from . import tests_demo_rehearsal_command as fixture
from .demo import backup, demo_view, rehearsal_command as runtime


class Clipboard:
    value = ''
    def get(self): return self.value
    def set(self, value): self.value = value
    def clear(self): self.value = ''


class SelectionTests(SimpleTestCase):
    def setUp(self):
        self.accounts = [dict(password='FAKE-ONLY-A', email='a@example.invalid', role='OWNER'),
                         dict(password='FAKE-ONLY-B', email='b@example.invalid', role='VIEWER')]
        self.clipboard = Clipboard()
        self.timers = []
        self.confirm = False
        self.state = Selection(self.accounts, lambda prompt: self.confirm, self.clipboard,
                               lambda ms, fn: self.timers.append(fn))

    def test_selection_and_confirmation(self):
        self.assertFalse(self.state.copy())
        self.state.select(0)
        self.assertFalse(self.state.reveal())
        self.assertFalse(self.state.copy())
        self.assertEqual(self.clipboard.value, '')
        self.confirm = True
        self.assertTrue(self.state.reveal())
        self.state.select(1)
        self.assertFalse(self.state.visible)
        self.assertTrue(self.state.copy())
        self.assertEqual(self.clipboard.value, 'FAKE-ONLY-B')

    def test_conditional_cleanup_and_close(self):
        self.state.select(0); self.confirm = True
        self.state.copy(); self.clipboard.value = 'user content'
        self.timers[-1]()
        self.assertEqual(self.clipboard.value, 'user content')
        self.state.copy(); self.state.close()
        self.assertEqual(self.clipboard.value, '')
        self.assertEqual(self.accounts, [])
        self.assertFalse(self.state.copy())
        with self.assertRaises(ValueError): self.state.select(0)

    def test_old_timer_cannot_clear_new_copy(self):
        self.state.select(0); self.confirm = True
        self.state.copy(); old = self.timers[-1]
        self.state.select(1); self.state.copy(); old()
        self.assertEqual(self.clipboard.value, 'FAKE-ONLY-B')
        self.timers[-1]()
        self.assertEqual(self.clipboard.value, '')

    def test_gui_with_fictitious_account_confirmation_and_close(self):
        import tkinter as tk
        from tkinter import ttk
        from .demo.credential_viewer import show_window
        root = tk.Tk()
        root.withdraw()
        sample = [dict(organization='Fictitious Ranch', email='fake@example.invalid', role='OWNER', password='FAKE-GUI-ONLY')]
        errors = []
        root.report_callback_exception = lambda *ignored: errors.append('callback failed')
        def exercise():
            try:
                widgets = root.winfo_children()[0].winfo_children()
                selectors = [w for w in widgets if isinstance(w, ttk.Combobox)]
                selectors[0].current(0); selectors[0].event_generate('<<ComboboxSelected>>')
                root.update()
                selectors[1].current(0); selectors[1].event_generate('<<ComboboxSelected>>')
                root.update()
                buttons = {w.cget('text'): w for w in widgets if isinstance(w, ttk.Button)}
                buttons['Mostrar / Ocultar contraseña'].invoke()
                buttons['Copiar contraseña (30 s)'].invoke()
                self.assertEqual(root.clipboard_get(), 'FAKE-GUI-ONLY')
                buttons['Cerrar'].invoke()
            except Exception:
                errors.append('GUI exercise failed')
                root.destroy()
        root.after(10, exercise)
        with patch('tkinter.messagebox.askyesno', return_value=True) as confirm:
            show_window(root, sample)
        self.assertEqual(errors, [])
        self.assertEqual(confirm.call_count, 2)
        self.assertEqual(sample, [])

    def test_normal_settings_rejected_before_read(self):
        with override_settings(SETTINGS_MODULE='config.settings.local'), patch.object(demo_view, 'verified_locations') as read:
            with self.assertRaises(ValueError):
                with validated_accounts(): self.fail('Unexpected selection enabled')
            read.assert_not_called()


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class ValidationTests(TransactionTestCase):
    setUp = fixture.RehearsalCommandTests.setUp
    grant = fixture.RehearsalCommandTests.grant
    invoke = fixture.RehearsalCommandTests.invoke

    def prepare(self):
        self.invoke(authorization=self.grant())
        self.plan = replace(self.plan, testing=False)

    def open(self):
        # Only paths in the synthetic test root. Production path/hash/SID guards tested separately.
        return validated_accounts()

    def scope(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(override_settings(SETTINGS_MODULE='config.settings.demo_view'))
        stack.enter_context(patch.object(demo_view, 'RUN_ID', self.plan.run_id))
        stack.enter_context(patch.object(demo_view, 'verified_locations', return_value=self.plan))
        return stack

    def test_validated_exact_accounts_no_plaintext_files_or_sqlite_changes(self):
        self.prepare()
        before = {p: backup.digest(p) for p in self.root.rglob('*') if p.is_file()}
        with self.scope(), self.open() as accounts:
            self.assertEqual(len(accounts), 30)
            self.assertEqual(len({a['organization'] for a in accounts}), 5)
            self.assertEqual(sum(a['role'] == 'OWNER' for a in accounts), 5)
            secrets = [a['password'].encode() for a in accounts]
            for p in before:
                data = p.read_bytes()
                self.assertFalse(any(value in data for value in secrets))
        self.assertEqual(accounts, [])
        self.assertEqual(before, {p: backup.digest(p) for p in self.root.rglob('*') if p.is_file()})

    def test_corrupt_bundle_never_yields(self):
        self.prepare()
        path = self.plan.deliveries[0] / 'd2.bundle'
        path.write_bytes(b'corrupt fictitious ciphertext')
        with self.scope(), self.assertRaises(Exception):
            with self.open(): self.fail('Unexpected selection enabled')

    def test_wrong_run_never_decrypts(self):
        self.prepare()
        with self.scope(), patch.object(demo_view, 'RUN_ID', 'wrong'), patch.object(runtime, '_read_bundle') as read:
            with self.assertRaises(ValueError):
                with self.open(): self.fail('Unexpected selection enabled')
            read.assert_not_called()

    def test_failed_manifest_never_yields(self):
        self.prepare()
        with self.scope(), patch.object(runtime, '_phase_status', return_value={'D2': 'incomplete'}):
            with self.assertRaises(ValueError):
                with self.open(): self.fail('Unexpected selection enabled')

    def test_unsafe_acl_never_decrypts(self):
        self.prepare()
        with self.scope(), patch('apps.organizations.demo.windows_acl.verify_private', side_effect=ValueError('unsafe ACL')), patch.object(runtime, '_read_bundle') as read:
            with self.assertRaises(ValueError):
                with self.open(): self.fail('Unexpected selection enabled')
            read.assert_not_called()

    def test_invalid_signed_receipt_never_yields(self):
        import base64
        import json
        from cryptography.fernet import Fernet
        self.prepare()
        path = self.plan.deliveries[0] / 'd2.bundle'
        cipher = Fernet(base64.urlsafe_b64encode(self.material['encryption']))
        bundle = json.loads(cipher.decrypt(path.read_bytes()))
        bundle['receipt']['signature'] = '0' * 64
        path.write_bytes(cipher.encrypt(json.dumps(bundle).encode()))
        with self.scope(), self.assertRaises(Exception):
            with self.open(): self.fail('Unexpected selection enabled')
