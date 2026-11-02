import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from apps.organizations.demo.preflight import (
    DATASET, PLAN, PLAN_DIGEST, TABLES, audit, authorize_database, canonical_json,
    demo_emails, inventory_digest, readonly_database, reject_write, run_lock,
)


class DemoD1Tests(SimpleTestCase):
    databases = set()  # Django ORM connections are forbidden for these tests.

    def test_deterministic_email_plan_accepted_by_actual_auth_schemas(self):
        from apps.accounts.api.schemas import LoginSchema, UserSchema
        emails = demo_emails()
        self.assertEqual(emails, demo_emails())
        self.assertEqual(len(emails), 30)
        self.assertEqual(len(set(emails)), 30)
        for email in ['red01.01@demo.example.com', *emails]:
            self.assertTrue(email.endswith('@demo.example.com'))
            self.assertEqual(str(LoginSchema(email=email, password='schema-only-placeholder').email), email)
            self.assertEqual(str(UserSchema(id=uuid4(), email=email, first_name='Demo', last_name='User').email), email)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve() / 'disposable.sqlite3'
        self.protected = uuid4().hex
        self.bindings = {table: uuid4().hex for table in ('catalog_species', 'catalog_breeds', 'catalog_weighing_methods', 'catalog_breeding_types')}
        self.config = SimpleNamespace(SETTINGS_MODULE='config.settings.demo_testing',
            DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(self.path)}},
            DEMO_AUTHORIZED_DATABASE=str(self.path), DEMO_PROTECTED_ORGANIZATION_UUID=self.protected,
            DEMO_CATALOG_BINDINGS=self.bindings, DEMO_MANIFEST_KEY='test-only-manifest-key-not-credentials-123')
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE organization (id TEXT PRIMARY KEY, name TEXT, code TEXT, slug TEXT)')
            db.execute('INSERT INTO organization VALUES (?, ?, ?, ?)', (self.protected, 'Rancho los Hermanos', 'PROTECTED', 'rancho-los-hermanos'))
            db.execute('CREATE TABLE user (id TEXT PRIMARY KEY, email TEXT)')
            db.execute('CREATE TABLE memberships (id TEXT PRIMARY KEY, organization_id TEXT, user_id TEXT, is_default INTEGER, is_active INTEGER)')
            for table in TABLES[3:]:
                db.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY, organization_id TEXT)')
            for table in ('catalog_farm_types', 'catalog_genders', 'catalog_animal_statuses', 'catalog_movement_types', 'catalog_production_types', *self.bindings):
                db.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY, code TEXT, is_active INTEGER, species_id TEXT)')
            required = {'catalog_farm_types': ['RANCH'], 'catalog_genders': ['F', 'M'], 'catalog_animal_statuses': ['ACTIVE', 'SOLD'], 'catalog_movement_types': ['TRANSFER', 'SALE'], 'catalog_production_types': ['MILK']}
            for table, codes in required.items():
                for code in codes:
                    db.execute(f'INSERT INTO "{table}" VALUES (?, ?, 1, NULL)', (uuid4().hex, code))
            for table, identifier in self.bindings.items():
                db.execute(f'INSERT INTO "{table}" VALUES (?, ?, 1, ?)', (identifier, 'TEST', self.bindings['catalog_species'] if table == 'catalog_breeds' else None))

    def manifest(self, complete=True):
        from django.utils.text import slugify
        with sqlite3.connect(self.path) as db:
            for name, code, users, farms, lots, animals in PLAN:
                org = uuid4().hex
                db.execute('INSERT INTO organization VALUES (?, ?, ?, ?)', (org, name, code, slugify(name)))
                for index in range(1, users + 1):
                    user = uuid4().hex
                    db.execute('INSERT INTO user VALUES (?, ?)', (user, f'{code.lower()}.{index:02d}@demo.example.com'))
                    db.execute('INSERT INTO memberships VALUES (?, ?, ?, 1, 1)', (uuid4().hex, org, user))
                for table, count in [('farms', farms), ('lots', lots), ('animals', animals)]:
                    for _ in range(count):
                        db.execute(f'INSERT INTO "{table}" VALUES (?, ?)', (uuid4().hex, org))
        with readonly_database(self.path) as db:
            inventory = {}
            for table in TABLES:
                query = f'SELECT * FROM "{table}"'
                params = ()
                if table == 'organization':
                    query += ' WHERE id != ?'; params = (self.protected,)
                rows = db.execute(query, params).fetchall()
                inventory[table] = {'count': len(rows), 'digest': inventory_digest(rows)}
        payload = {'dataset': DATASET, 'version': 1, 'plan_digest': PLAN_DIGEST,
            'protected_uuid': self.protected, 'state': 'complete' if complete else 'partial', 'inventory': inventory}
        path = self.path.parent / 'receipt.json'
        signature = hmac.new(self.config.DEMO_MANIFEST_KEY.encode(), canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        path.write_text(json.dumps({'payload': payload, 'signature': signature}), encoding='utf-8')
        return path

    def test_fresh_dry_run_is_repeatable_and_does_not_write_files_or_database(self):
        before = self.path.read_bytes()
        files = set(self.path.parent.iterdir())
        self.assertEqual(audit(self.path, self.config), {'state': 'fresh', 'issues': []})
        self.assertEqual(audit(self.path, self.config), {'state': 'fresh', 'issues': []})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(set(self.path.parent.iterdir()), files)

    def test_command_default_and_explicit_dry_run_are_readonly(self):
        before = self.path.read_bytes()
        with override_settings(SETTINGS_MODULE=self.config.SETTINGS_MODULE, DATABASES=self.config.DATABASES,
            DEMO_AUTHORIZED_DATABASE=str(self.path), DEMO_PROTECTED_ORGANIZATION_UUID=self.protected, DEMO_CATALOG_BINDINGS=self.bindings):
            for args in [[], ['--dry-run']]:
                out = io.StringIO()
                call_command('seed_demo_ranches', *args, stdout=out)
                self.assertIn('D1 DRY-RUN', out.getvalue())
        self.assertEqual(before, self.path.read_bytes())

    def test_settings_allowlist(self):
        for module in ['config.settings.production', 'config.settings.base', 'config.settings.testing', 'unknown']:
            self.config.SETTINGS_MODULE = module
            with self.assertRaises(ValueError): authorize_database(self.config, 'default')
        self.config.SETTINGS_MODULE = 'config.settings.local'
        self.assertEqual(authorize_database(self.config, 'default'), self.path)

    def test_alias_engine_path_and_options_fail_closed(self):
        with self.assertRaises(ValueError): authorize_database(self.config, 'other')
        for mutation in [{'ENGINE': 'django.db.backends.postgresql'}, {'NAME': ':memory:'}, {'NAME': '//remote/db.sqlite3'}, {'OPTIONS': {'uri': True}}, {'HOST': 'remote'}]:
            original = self.config.DATABASES['default'].copy()
            self.config.DATABASES['default'].update(mutation)
            with self.assertRaises(ValueError): authorize_database(self.config, 'default')
            self.config.DATABASES['default'] = original
        self.config.DEMO_AUTHORIZED_DATABASE = None
        with self.assertRaises(ValueError): authorize_database(self.config, 'default')

    def test_different_authorized_file_rejected(self):
        other = self.path.parent / 'other.sqlite3'; other.write_bytes(self.path.read_bytes())
        self.config.DEMO_AUTHORIZED_DATABASE = str(other)
        with self.assertRaises(ValueError): authorize_database(self.config, 'default')

    def test_hard_links_rejected(self):
        linked = self.path.parent / 'linked.sqlite3'; os.link(self.path, linked)
        with self.assertRaises(ValueError): authorize_database(self.config, 'default')

    def test_reparse_or_symlink_rejected(self):
        from apps.organizations.demo import preflight
        real = Path.lstat
        def suspicious(path):
            info = real(path)
            if path == self.path:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(preflight.Path, 'lstat', suspicious):
            with self.assertRaises(ValueError): authorize_database(self.config, 'default')

    def test_writes_rejected_with_or_without_environment_flag(self):
        for value in ['', '1']:
            with patch.dict(os.environ, {'AGROCORE_ENABLE_DEMO_WRITES': value}):
                with self.assertRaises(ValueError): reject_write()
                with self.assertRaises(CommandError): call_command('seed_demo_ranches', '--write')

    def test_sql_write_and_attach_denied(self):
        before = self.path.read_bytes()
        with readonly_database(self.path) as db:
            for query in ['DELETE FROM organization', 'CREATE TABLE forbidden (id TEXT)', "ATTACH ':memory:' AS other", 'PRAGMA query_only=OFF']:
                with self.assertRaises(sqlite3.DatabaseError): db.execute(query)
        self.assertEqual(before, self.path.read_bytes())

    def test_failure_rolls_back_read_snapshot_and_releases_connection(self):
        before = self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            with readonly_database(self.path): raise RuntimeError('test')
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(audit(self.path, self.config)['state'], 'fresh')

    def test_protected_uuid_and_name_required(self):
        for value in [None, 'invalid', uuid4().hex]:
            self.config.DEMO_PROTECTED_ORGANIZATION_UUID = value
            with self.assertRaises(ValueError): audit(self.path, self.config)
        self.config.DEMO_PROTECTED_ORGANIZATION_UUID = self.protected
        with sqlite3.connect(self.path) as db: db.execute("UPDATE organization SET name='Different'")
        with self.assertRaises(ValueError): audit(self.path, self.config)

    def test_missing_catalog_and_bad_breed_report_without_changes(self):
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM catalog_genders WHERE code=?', ('F',))
            db.execute('UPDATE catalog_breeds SET species_id=?', (uuid4().hex,))
        before = self.path.read_bytes()
        result = audit(self.path, self.config)
        self.assertEqual(len(result['issues']), 2)
        self.assertEqual(before, self.path.read_bytes())

    def test_missing_explicit_catalog_bindings(self):
        self.config.DEMO_CATALOG_BINDINGS = {}
        self.assertEqual(len(audit(self.path, self.config)['issues']), 4)

    def test_unknown_organization_collision_even_inactive_dataset(self):
        from django.utils.text import slugify
        name, code, *_ = PLAN[0]
        with sqlite3.connect(self.path) as db: db.execute('INSERT INTO organization VALUES (?, ?, ?, ?)', (uuid4().hex, name, code, slugify(name)))
        with self.assertRaises(ValueError): audit(self.path, self.config)

    def test_name_code_and_slug_collision(self):
        for field, value in [('name', PLAN[0][0]), ('code', PLAN[0][1]), ('slug', 'rancho-el-encino-demo')]:
            with sqlite3.connect(self.path) as db:
                db.execute('DELETE FROM organization WHERE id != ?', (self.protected,))
                row = dict(id=uuid4().hex, name='Other', code='Other', slug='other'); row[field] = value
                db.execute('INSERT INTO organization VALUES (:id, :name, :code, :slug)', row)
            with self.assertRaises(ValueError): audit(self.path, self.config)

    def test_existing_roble_is_preserved_and_does_not_collide_with_encino(self):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO organization VALUES (?, ?, ?, ?)', (uuid4().hex, 'Rancho El Roble', 'RER', 'rancho-el-roble'))
        before = self.path.read_bytes()
        self.assertEqual(audit(self.path, self.config), {'state': 'fresh', 'issues': []})
        self.assertEqual(before, self.path.read_bytes())

    def test_signed_previous_plan_manifest_is_rejected_without_writes(self):
        receipt = self.manifest()
        envelope = json.loads(receipt.read_text(encoding='utf-8'))
        old_plan = (('Rancho El Roble', 'DEMO-V1-ROBLE', 5, 2, 6, 50), *PLAN[1:])
        envelope['payload']['plan_digest'] = hashlib.sha256(canonical_json(old_plan).encode()).hexdigest()
        envelope['signature'] = hmac.new(self.config.DEMO_MANIFEST_KEY.encode(), canonical_json(envelope['payload']).encode(), hashlib.sha256).hexdigest()
        receipt.write_text(json.dumps(envelope), encoding='utf-8')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): audit(self.path, self.config, receipt)
        self.assertEqual(before, self.path.read_bytes())

    def test_existing_email_never_adopted(self):
        with sqlite3.connect(self.path) as db: db.execute('INSERT INTO user VALUES (?, ?)', (uuid4().hex, demo_emails()[0].upper()))
        with self.assertRaises(ValueError): audit(self.path, self.config)

    def test_signed_complete_receipt_is_idempotent_readonly(self):
        receipt = self.manifest(); before = self.path.read_bytes()
        for _ in range(2): self.assertEqual(audit(self.path, self.config, receipt)['state'], 'recognized-complete')
        self.assertEqual(before, self.path.read_bytes())

    def test_partial_receipt_rejected(self):
        with self.assertRaises(ValueError): audit(self.path, self.config, self.manifest(complete=False))

    def test_tampered_receipt_rejected(self):
        receipt = self.manifest(); envelope = json.loads(receipt.read_text()); envelope['payload']['version'] = 2
        receipt.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError): audit(self.path, self.config, receipt)

    def test_changed_dataset_rejected_without_repair(self):
        receipt = self.manifest()
        with sqlite3.connect(self.path) as db: db.execute('DELETE FROM animals WHERE id=(SELECT id FROM animals LIMIT 1)')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): audit(self.path, self.config, receipt)
        self.assertEqual(before, self.path.read_bytes())

    def test_malformed_manifest_rejected(self):
        receipt = self.path.parent / 'bad.json'; receipt.write_text('{bad')
        with self.assertRaises(ValueError): audit(self.path, self.config, receipt)

    def test_concurrent_run_rejected_and_lock_released_on_failure(self):
        failures = []
        def contender():
            try:
                with run_lock(self.path): failures.append('unexpected acquisition')
            except ValueError: failures.append('rejected')
        with self.assertRaises(RuntimeError):
            with run_lock(self.path):
                thread = Thread(target=contender); thread.start(); thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(failures, ['rejected'])
                raise RuntimeError('test')
        with run_lock(self.path): pass

    def test_no_destructive_options(self):
        from apps.organizations.management.commands.seed_demo_ranches import Command
        parser = Command().create_parser('manage.py', 'seed_demo_ranches')
        for option in ['--reset', '--clean', '--force', '--update-existing']:
            self.assertNotIn(option, parser._option_string_actions)

    def test_wal_rejected_before_opening_sqlite(self):
        with sqlite3.connect(self.path) as db: db.execute('PRAGMA journal_mode=WAL')
        with self.assertRaises(ValueError):
            with readonly_database(self.path): pass

    def test_signed_unknown_dataset_rejected(self):
        receipt = self.manifest()
        envelope = json.loads(receipt.read_text())
        envelope['payload']['dataset'] = 'unrelated-dataset'
        envelope['signature'] = hmac.new(self.config.DEMO_MANIFEST_KEY.encode(), canonical_json(envelope['payload']).encode(), hashlib.sha256).hexdigest()
        receipt.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError): audit(self.path, self.config, receipt)

    def test_short_or_wrong_verification_key_rejected(self):
        receipt = self.manifest()
        for key in ['', 'short', 'wrong-key-of-at-least-thirty-two-bytes']:
            self.config.DEMO_MANIFEST_KEY = key
            with self.assertRaises(ValueError): audit(self.path, self.config, receipt)

    def test_missing_domain_schema_rejected(self):
        with sqlite3.connect(self.path) as db: db.execute('DROP TABLE births')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): audit(self.path, self.config)
        self.assertEqual(before, self.path.read_bytes())

    def test_missing_protected_config_rejected_before_database_open(self):
        self.config.DEMO_PROTECTED_ORGANIZATION_UUID = None
        with patch('apps.organizations.demo.preflight.sqlite3.connect') as connect:
            with self.assertRaises(ValueError): audit(self.path, self.config)
            connect.assert_not_called()

    def test_command_reports_missing_catalog_without_mutations(self):
        with sqlite3.connect(self.path) as db: db.execute('DELETE FROM catalog_genders')
        before = self.path.read_bytes()
        out = io.StringIO()
        with override_settings(SETTINGS_MODULE=self.config.SETTINGS_MODULE, DATABASES=self.config.DATABASES,
            DEMO_AUTHORIZED_DATABASE=str(self.path), DEMO_PROTECTED_ORGANIZATION_UUID=self.protected, DEMO_CATALOG_BINDINGS=self.bindings):
            with self.assertRaises(CommandError): call_command('seed_demo_ranches', stdout=out)
        self.assertIn('BLOCKER:', out.getvalue())
        self.assertEqual(before, self.path.read_bytes())

    def test_other_process_cannot_acquire_held_mutex(self):
        import subprocess
        import sys
        script = 'from pathlib import Path; from apps.organizations.demo.preflight import run_lock; import sys\ntry:\n with run_lock(Path(sys.argv[1])): sys.exit(3)\nexcept ValueError: sys.exit(0)'
        with run_lock(self.path):
            result = subprocess.run([sys.executable, '-B', '-c', script, str(self.path)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
