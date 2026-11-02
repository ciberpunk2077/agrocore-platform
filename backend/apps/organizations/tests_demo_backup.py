from contextlib import closing
"""D6B uses only disposable raw SQLite files, never the persistent database."""
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .demo import backup
from .demo.windows_acl import verify_private


class BackupTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agrocore-backup-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.sqlite3'
        with closing(sqlite3.connect(self.source)) as db:
            db.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY, name TEXT);'
                             'CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));'
                             "INSERT INTO parent VALUES(1,'protected'); INSERT INTO child VALUES(1,1);")
        self.before = backup.digest(self.source)
        self.target = self.root / 'private'
        backup.private_directory(self.target)

    def test_consistent_backup_and_restore(self):
        first = self.target / 'backup.sqlite3'
        second = self.target / 'restored.sqlite3'
        with backup.frozen_source(self.source):
            backup.copy_database(self.source, first)
        with backup.frozen_source(first):
            backup.copy_database(first, second)
        self.assertEqual(backup.inspect_database(self.source), backup.inspect_database(second))
        self.assertEqual(backup.digest(self.source), self.before)
        verify_private(first)
        verify_private(second)

    def test_existing_destination(self):
        target = self.target / 'exists.sqlite3'
        target.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            backup.copy_database(self.source, target)
        self.assertEqual(target.read_bytes(), b'keep')

    def test_same_source_destination(self):
        with self.assertRaises(ValueError):
            backup.copy_database(self.source, self.source)
        self.assertEqual(backup.digest(self.source), self.before)

    def test_corrupt_database(self):
        corrupt = self.target / 'bad.sqlite3'
        corrupt.write_bytes(b'not SQLite')
        with self.assertRaises(sqlite3.DatabaseError):
            backup.inspect_database(corrupt)

    def test_foreign_key_failure(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('INSERT INTO child VALUES(2,99)')
            db.commit()
        with self.assertRaises(ValueError):
            backup.inspect_database(self.source)

    def test_writer_handle_rejected(self):
        with closing(sqlite3.connect(self.source)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError):
                with backup.frozen_source(self.source):
                    self.fail('Writer exclusion bypassed')
            writer.rollback()

    def test_sidecars_rejected(self):
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = Path(str(self.source) + suffix)
            sidecar.touch()
            try:
                with self.assertRaises(ValueError):
                    with backup.frozen_source(self.source):
                        pass
            finally:
                sidecar.unlink()

    def test_unsafe_directories(self):
        for path in (Path('relative'), self.root / '..' / self.root.name):
            with self.assertRaises(ValueError):
                backup.directory(path)

    def test_hardlink_rejected(self):
        linked = self.root / 'linked.sqlite3'
        linked.hardlink_to(self.source)
        with self.assertRaises(ValueError):
            backup.inspect_database(linked)

    def test_failed_backup_has_no_authorized_receipt(self):
        target = self.target / 'failed.sqlite3'
        with patch('apps.organizations.demo.backup.sqlite3.connect', side_effect=sqlite3.OperationalError('injected')):
            with self.assertRaises(sqlite3.OperationalError):
                backup.copy_database(self.source, target)
        self.assertEqual(backup.digest(self.source), self.before)
        self.assertFalse((self.target / 'receipt.json').exists())

    def test_prepare_receipt_and_snapshot(self):
        with patch.object(backup, 'check_migrations'), patch.object(backup, 'preflight'):
            receipt = backup.prepare(self.source, self.target / 'storage', str(uuid4()))
        self.assertEqual(receipt['source_sha256'], self.before)
        self.assertEqual(receipt['snapshot'], backup.inspect_database(self.source))

    def test_run_collision(self):
        run = str(uuid4())
        with patch.object(backup, 'check_migrations'), patch.object(backup, 'preflight'):
            backup.prepare(self.source, self.target / 'storage', run)
            with self.assertRaises(ValueError):
                backup.prepare(self.source, self.target / 'storage', run)

    def test_restore_failure_no_receipt(self):
        actual = backup.copy_database
        calls = []
        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError('injected restore failure')
            return actual(source, target)
        run = str(uuid4())
        with patch.object(backup, 'check_migrations'), patch.object(backup, 'preflight'), patch.object(backup, 'copy_database', side_effect=fail_second):
            with self.assertRaises(OSError):
                backup.prepare(self.source, self.target / 'storage', run)
        self.assertFalse((self.target / 'storage' / 'rehearsals' / run / 'receipt.json').exists())
        self.assertEqual(backup.digest(self.source), self.before)

    def test_insufficient_space(self):
        with patch.object(backup.shutil, 'disk_usage', return_value=type('Usage', (), {'free': 0})()):
            with self.assertRaises(ValueError):
                backup.prepare(self.source, self.target / 'storage', str(uuid4()))
        self.assertFalse((self.target / 'storage').exists())

    def test_write_still_disabled(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo_ranches', write=True, stdout=StringIO())

    def test_unknown_configuration_rejected(self):
        with self.assertRaises(CommandError):
            call_command('prepare_demo_rehearsal', run_id=str(uuid4()), stdout=StringIO())

    def test_invalid_run_id(self):
        with self.assertRaises(ValueError):
            backup.prepare(self.source, self.target / 'storage', '../escape')

    def test_readonly_connection_refuses_write(self):
        with closing(sqlite3.connect(self.source.as_uri() + '?mode=ro', uri=True)) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM parent')

    def test_unsafe_symlink_rejected(self):
        link = self.root / 'junction'
        import subprocess
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(self.target)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.addCleanup(link.rmdir)
        with self.assertRaises(ValueError):
            backup.directory(link)

    def test_redirected_localappdata_rejected(self):
        with patch.dict('os.environ', {'LOCALAPPDATA': str(self.root)}):
            with self.assertRaises(ValueError):
                backup.storage()

    def test_receipt_provenance_and_tamper(self):
        run = str(uuid4())
        root = self.target / 'storage'
        with patch.object(backup, 'check_migrations'), patch.object(backup, 'preflight'):
            backup.prepare(self.source, root, run)
        with patch.object(backup, 'storage', return_value=root), patch.object(backup, 'ORIGINAL', self.source), patch.object(backup, 'check_migrations'):
            path = backup.rehearsal_path(run)
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE parent SET name='altered'")
                db.commit()
            with self.assertRaises(ValueError):
                backup.rehearsal_path(run)

    def test_partial_run_rejected(self):
        run = str(uuid4())
        root = self.target / 'storage'
        backup.private_directory(root)
        backup.private_directory(root / 'rehearsals')
        backup.private_directory(root / 'rehearsals' / run)
        with patch.object(backup, 'storage', return_value=root):
            with self.assertRaises(FileNotFoundError):
                backup.rehearsal_path(run)

    def test_missing_migration_rejected(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('CREATE TABLE django_migrations(app TEXT, name TEXT)')
        with self.assertRaises(ValueError):
            backup.check_migrations(self.source)

    def test_acl_failure_before_copy(self):
        with patch('apps.organizations.demo.windows_acl.verify_private', side_effect=ValueError('unsafe ACL')):
            with self.assertRaises(ValueError):
                backup.copy_database(self.source, self.target / 'new.sqlite3')
        self.assertFalse((self.target / 'new.sqlite3').exists())

    def test_original_rejected_as_rehearsal(self):
        run = str(uuid4())
        root = self.target / 'storage'
        with patch.object(backup, 'check_migrations'), patch.object(backup, 'preflight'):
            backup.prepare(self.source, root, run)
        with patch.object(backup, 'storage', return_value=root), patch.object(backup, 'ORIGINAL', root / 'rehearsals' / run / 'database.sqlite3'):
            with self.assertRaises(ValueError):
                backup.rehearsal_path(run)

    def test_readonly_rehearsal_command_rejects_configuration(self):
        from django.test import override_settings
        with override_settings(SETTINGS_MODULE='config.settings.demo_rehearsal'):
            with self.assertRaises(CommandError):
                call_command('seed_demo_ranches', database='other', stdout=StringIO())

    def test_write_flag_cannot_unlock(self):
        with patch.dict('os.environ', {'AGROCORE_ENABLE_DEMO_WRITES': '1'}):
            with self.assertRaises(CommandError):
                call_command('seed_demo_ranches', write=True, stdout=StringIO())

    def test_exact_catalog_preflight(self):
        with closing(sqlite3.connect(self.source)) as db:
            for table, code in (('catalog_species', 'BOV'), ('catalog_breeds', 'HOL'),
                                ('catalog_weighing_methods', 'SCALE'), ('catalog_breeding_types', 'NAT')):
                db.execute(f'CREATE TABLE {table}(id TEXT,code TEXT,is_active INTEGER,deleted_at TEXT)')
                db.execute(f'INSERT INTO {table} VALUES(?,?,1,NULL)', (uuid4().hex, code))
            db.execute('CREATE TABLE catalog_production_types(code TEXT,default_unit TEXT,is_active INTEGER,deleted_at TEXT)')
            db.execute("INSERT INTO catalog_production_types VALUES('MILK','L',1,NULL)")
            db.commit()
        with patch.object(backup, 'audit', return_value={'state': 'fresh', 'issues': []}):
            self.assertEqual(backup.preflight(self.source)['state'], 'fresh')
            with closing(sqlite3.connect(self.source)) as db:
                db.execute("UPDATE catalog_production_types SET default_unit='kg'")
                db.commit()
            with self.assertRaises(ValueError):
                backup.preflight(self.source)

    def test_missing_catalog_rejected(self):
        with closing(sqlite3.connect(self.source)) as db:
            db.execute('CREATE TABLE catalog_species(id TEXT,code TEXT,is_active INTEGER,deleted_at TEXT)')
        with self.assertRaises(ValueError):
            backup.preflight(self.source)

    def test_rehearsal_identity_is_safe_before_apps_are_ready(self):
        run = str(uuid4())
        root = self.target / 'storage'
        with patch.object(backup, 'check_migrations'), patch.object(backup, 'preflight'):
            backup.prepare(self.source, root, run)
        with patch.object(backup, 'storage', return_value=root), patch.object(backup, 'ORIGINAL', self.source), patch.object(backup, 'check_migrations', side_effect=AssertionError('Apps not ready')) as loader:
            self.assertTrue(backup.rehearsal_path(run).exists())
            loader.assert_not_called()

    def test_rehearsal_connection_normalization(self):
        from types import SimpleNamespace
        from django.db.utils import ConnectionHandler
        config = SimpleNamespace(SETTINGS_MODULE='config.settings.demo_rehearsal',
            DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3',
                                  'NAME': self.source.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}})
        backup.authorize_rehearsal_connection(config, self.source)
        config.DATABASES = ConnectionHandler(config.DATABASES).settings
        backup.authorize_rehearsal_connection(config, self.source)
        config.DATABASES['default']['OPTIONS']['init_command'] = 'PRAGMA query_only=OFF'
        with self.assertRaises(ValueError):
            backup.authorize_rehearsal_connection(config, self.source)
