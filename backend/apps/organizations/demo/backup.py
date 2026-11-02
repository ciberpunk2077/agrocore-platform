"""D6B: exclusive, private SQLite snapshots; no seeder writer capability."""
import ctypes
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from types import SimpleNamespace
from uuid import UUID

from .preflight import audit, safe_file, run_lock

PROTECTED = 'ff667428-41cc-41db-820f-f2c4ffe27713'
ORIGINAL = Path(__file__).resolve().parents[3] / 'config' / 'db.sqlite3'


def digest(path):
    with open(path, 'rb') as stream:
        hasher = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(block)
        return hasher.hexdigest()


def directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts or str(path).startswith(('\\\\', '//')):
        raise ValueError('Unsafe directory.')
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse points are forbidden.')
        if any(part.endswith((' ', '.')) or ':' in part for part in item.parts[1:]):
            raise ValueError('Ambiguous directory.')
    if not path.is_dir():
        raise ValueError('Expected directory.')
    return path.resolve(strict=True)


def storage():
    if os.name != 'nt' or not os.environ.get('LOCALAPPDATA'):
        raise ValueError('Windows local profile required.')
    # Do not trust an environment redirect of the Windows local profile.
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x001c, None, 0, buffer) != 0:
        raise ValueError('Cannot resolve Windows LocalAppData identity.')
    profile = directory(Path(buffer.value))
    if directory(Path(os.environ['LOCALAPPDATA'])) != profile:
        raise ValueError('Redirected LOCALAPPDATA is forbidden.')
    return profile / 'AgroCore' / 'DemoDataV1'


def private_directory(path, *, exclusive=False):
    from .windows_acl import restrict_directory, verify_private
    if exclusive or not path.exists():
        directory(path.parent)
        path.mkdir()
        restrict_directory(path)
    directory(path)
    verify_private(path)


@contextmanager
def frozen_source(path):
    """Deny concurrent Windows write/delete handles, including existing writers."""
    path = safe_file(path)
    if os.name != 'nt':
        raise ValueError('Writer exclusion requires Windows.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ValueError('Source busy or writer exclusion unavailable; stop.')
    try:
        identity = path.stat()
        for suffix in ('-wal', '-shm', '-journal'):
            if Path(str(path) + suffix).exists():
                raise ValueError('Unexpected SQLite sidecar; stop without checkpointing.')
        with open(path, 'rb') as stream:
            header = stream.read(100)
        if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
            raise ValueError('Only rollback-journal SQLite sources are authorized.')
        yield path
        if path.stat() != identity:
            # atime can change on some filesystems; compare actual file identity/size/mtime.
            after = path.stat()
            if (after.st_ino, after.st_size, after.st_mtime_ns) != (identity.st_ino, identity.st_size, identity.st_mtime_ns):
                raise ValueError('Source identity changed.')
    finally:
        kernel.CloseHandle(handle)


def inspect_database(path):
    with closing(sqlite3.connect(safe_file(path).as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed.')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite foreign keys failed.')
        db.execute('BEGIN')
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        result = {'schema': hashlib.sha256(repr(schema).encode()).hexdigest(), 'tables': {}}
        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            rows = sorted(repr(row) for row in db.execute('SELECT * FROM ' + quoted))
            result['tables'][name] = {'count': len(rows), 'digest': hashlib.sha256(repr(rows).encode()).hexdigest()}
        db.rollback()
        return result


def check_migrations(path):
    from django.db.migrations.loader import MigrationLoader
    expected = set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)
    with closing(sqlite3.connect(safe_file(path).as_uri() + '?mode=ro', uri=True)) as db:
        applied = set(db.execute('SELECT app,name FROM django_migrations'))
    if expected != applied:
        raise ValueError('Unapplied or unknown migrations; no migration will be executed.')


def preflight(path):
    bindings = {}
    with closing(sqlite3.connect(safe_file(path).as_uri() + '?mode=ro', uri=True)) as db:
        for table, code in (('catalog_species', 'BOV'), ('catalog_breeds', 'HOL'),
                            ('catalog_weighing_methods', 'SCALE'), ('catalog_breeding_types', 'NAT')):
            rows = db.execute(f'SELECT id FROM {table} WHERE code=? AND is_active=1 AND deleted_at IS NULL', (code,)).fetchall()
            if len(rows) != 1:
                raise ValueError('Required exact catalog missing: ' + code)
            bindings[table] = rows[0][0]
        milk = db.execute("SELECT default_unit FROM catalog_production_types WHERE code='MILK' AND is_active=1 AND deleted_at IS NULL").fetchall()
        if milk != [('L',)]:
            raise ValueError('Required MILK/L catalog missing.')
    result = audit(path, SimpleNamespace(DEMO_PROTECTED_ORGANIZATION_UUID=PROTECTED,
                                        DEMO_CATALOG_BINDINGS=bindings))
    if result['issues'] or result['state'] != 'fresh':
        raise ValueError('Read-only preflight rejected: ' + repr(result))
    return result


def copy_database(source, target):
    """New exclusive file only; failures retain a visibly incomplete artifact."""
    from .windows_acl import verify_private
    source = safe_file(source)
    directory(target.parent)
    verify_private(target.parent)
    if target.exists() or source == target:
        raise ValueError('Destination exists or equals source.')
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    verify_private(target)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as origin:
        origin.execute('PRAGMA query_only=ON')
        with closing(sqlite3.connect(target)) as destination:
            origin.backup(destination, pages=256)
    inspect_database(target)
    with open(target, 'r+b') as stream:
        os.fsync(stream.fileno())


def prepare(source, root, run_id):
    """Caller authorizes source/root; no ORM, credentials or seeder execution."""
    if str(UUID(run_id)) != run_id:
        raise ValueError('Canonical UUID run-id required.')
    source = safe_file(source)
    root = Path(root)
    directory(root.parent)
    if source.is_relative_to(root):
        raise ValueError('Source cannot be in destination storage.')
    if shutil.disk_usage(root.parent).free < source.stat().st_size * 4 + 64 * 1024 * 1024:
        raise ValueError('Insufficient free space.')
    with run_lock(source), frozen_source(source):
        before = digest(source)
        reference = inspect_database(source)
        check_migrations(source)
        preflight(source)
        private_directory(root)
        for category in ('backups', 'rehearsals'):
            private_directory(root / category)
        backup_dir, rehearsal_dir = (root / category / run_id for category in ('backups', 'rehearsals'))
        if backup_dir.exists() or rehearsal_dir.exists():
            raise ValueError('Run-id collision; incomplete runs must not be reused.')
        private_directory(backup_dir, exclusive=True)
        private_directory(rehearsal_dir, exclusive=True)
        backup = backup_dir / 'database.sqlite3'
        rehearsal = rehearsal_dir / 'database.sqlite3'
        copy_database(source, backup)
        backup_hash = digest(backup)
        with frozen_source(backup):
            copy_database(backup, rehearsal)
        for path in (backup, rehearsal):
            if inspect_database(path) != reference:
                raise ValueError('Restored snapshot differs from consistent source.')
            check_migrations(path)
        preflight(rehearsal)
        if digest(source) != before or digest(backup) != backup_hash:
            raise ValueError('Original or backup changed.')
        receipt = {'version': 'D6B', 'run_id': run_id, 'source': str(source),
                   'source_sha256': before, 'backup_sha256': backup_hash,
                   'rehearsal_sha256': digest(rehearsal), 'snapshot': reference,
                   'protected_uuid': PROTECTED}
        # Receipt is published last: incomplete runs never become authorized settings.
        with open(rehearsal_dir / 'receipt.json', 'x', encoding='utf-8') as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        from .windows_acl import verify_private
        verify_private(rehearsal_dir / 'receipt.json')
        return receipt


def rehearsal_path(run_id):
    from .windows_acl import verify_private
    if str(UUID(run_id)) != run_id:
        raise ValueError('Canonical rehearsal run-id required.')
    root = storage()
    folder = root / 'rehearsals' / run_id
    for item in (root, root / 'rehearsals', folder):
        directory(item)
        verify_private(item)
    receipt_file = safe_file(folder / 'receipt.json')
    verify_private(receipt_file)
    if receipt_file.stat().st_size > 1024 * 1024:
        raise ValueError('Oversized receipt.')
    receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
    path = safe_file(folder / 'database.sqlite3')
    backup = safe_file(root / 'backups' / run_id / 'database.sqlite3')
    for item in (root / 'backups', backup.parent):
        directory(item)
        verify_private(item)
    verify_private(path)
    verify_private(backup)
    if (receipt['version'] != 'D6B' or receipt['run_id'] != run_id
            or receipt['source'] != str(ORIGINAL) or receipt['protected_uuid'] != PROTECTED
            or os.path.samefile(path, ORIGINAL) or digest(path) != receipt['rehearsal_sha256']
            or digest(backup) != receipt['backup_sha256']):
        raise ValueError('Rehearsal provenance rejected.')
    if inspect_database(path) != receipt['snapshot']:
        raise ValueError('Rehearsal snapshot altered.')
    if inspect_database(backup) != receipt['snapshot']:
        raise ValueError('Backup snapshot altered.')
    return path


def authorize_rehearsal_connection(config, path):
    """Accept Django's standard normalization, never custom connection options."""
    from copy import deepcopy
    from django.db.utils import ConnectionHandler
    expected = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                           'NAME': path.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}}
    if (config.SETTINGS_MODULE != 'config.settings.demo_rehearsal'
            or getattr(config, 'DATABASE_ROUTERS', [])
            or ConnectionHandler(deepcopy(config.DATABASES)).settings != ConnectionHandler(expected).settings):
        raise ValueError('Unexpected rehearsal connection configuration.')
