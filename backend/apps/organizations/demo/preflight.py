"""Fail-closed D1 guards, signed receipts and SQLite read-only inspection."""
import ctypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
from contextlib import contextmanager
from uuid import UUID

from django.utils.text import slugify

DATASET = 'agrocore-demo-ranches-v1'
PLAN = (
    ('Rancho El Encino Demo', 'RED01', 5, 2, 6, 50),
    ('Rancho La Esperanza', 'DEMO-V1-ESPERANZA', 7, 3, 9, 80),
    ('Ganadería San José', 'DEMO-V1-SANJOSE', 4, 1, 4, 30),
    ('Rancho Los Pinos', 'DEMO-V1-PINOS', 6, 2, 8, 65),
    ('Hacienda La Ceiba', 'DEMO-V1-CEIBA', 8, 4, 12, 100),
)
TABLES = ('organization', 'user', 'memberships', 'farms', 'lots', 'animals', 'weights',
          'vaccinations', 'animal_movements', 'breeding_events', 'pregnancies', 'births', 'production_records')
ALLOWED_SETTINGS = frozenset({'config.settings.local', 'config.settings.demo_testing'})
ALLOWED_ENV = 'AGROCORE_ENABLE_DEMO_WRITES'


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


PLAN_DIGEST = hashlib.sha256(canonical_json(PLAN).encode()).hexdigest()


def demo_emails():
    return [f'{code.lower()}.{index:02d}@demo.example.com' for _, code, users, *_ in PLAN for index in range(1, users + 1)]


def uuid_hex(value):
    try:
        return UUID(str(value)).hex
    except (ValueError, TypeError, AttributeError):
        raise ValueError('A valid protected organization UUID is required.') from None


def safe_file(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('An absolute canonical local file path is required.')
    if str(value).startswith(('\\\\', '//', 'file:', 'http:', 'https:')):
        raise ValueError('Remote paths and URI databases are forbidden.')
    if any(part.endswith((' ', '.')) or ':' in part for part in path.parts[1:]):
        raise ValueError('Ambiguous paths and alternate data streams are forbidden.')
    for entry in (path, *path.parents):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symlinks, junctions and reparse points are forbidden.')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('A regular existing file without hard links is required.')
    if os.name == 'nt':
        drive = path.drive + '\\'
        if ctypes.windll.kernel32.GetDriveTypeW(drive) != 3:
            raise ValueError('Only fixed local Windows drives are authorized.')
    return path.resolve(strict=True)


def authorize_database(config, alias):
    if config.SETTINGS_MODULE not in ALLOWED_SETTINGS:
        raise ValueError('Production or unknown settings are forbidden.')
    if alias != 'default':
        raise ValueError('Only the default alias is authorized.')
    database = config.DATABASES.get(alias, {})
    if database.get('ENGINE') != 'django.db.backends.sqlite3' or database.get('HOST') or database.get('PORT'):
        raise ValueError('Only a local SQLite database is authorized.')
    if database.get('OPTIONS'):
        raise ValueError('Custom SQLite connection options are not authorized in D1.')
    approved = getattr(config, 'DEMO_AUTHORIZED_DATABASE', None)
    if not approved:
        raise ValueError('DEMO_AUTHORIZED_DATABASE must explicitly authorize the database.')
    path, allowed = safe_file(database.get('NAME', '')), safe_file(approved)
    if path != allowed:
        raise ValueError('The configured database differs from the authorized path.')
    return path


def reject_write():
    if os.environ.get(ALLOWED_ENV) != '1':
        raise ValueError(f'Future writes require {ALLOWED_ENV}=1; D1 still forbids writes.')
    raise ValueError('Write mode is disabled in D1, including with the environment flag enabled.')


@contextmanager
def run_lock(path):
    """Cooperating-command exclusion without creating lock files."""
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        name = 'Global\\AgroCoreDemo-' + hashlib.sha256(str(path).casefold().encode()).hexdigest()
        handle = kernel.CreateMutexW(None, False, name)
        if not handle:
            raise ValueError('Cannot create the execution mutex.')
        acquired = kernel.WaitForSingleObject(handle, 0)
        if acquired not in (0, 0x80):
            kernel.CloseHandle(handle)
            raise ValueError('Another demo preflight is running or mutex acquisition failed.')
        try:
            yield
        finally:
            kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        import fcntl
        with open(path, 'rb') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError('Another demo preflight is running.') from None
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def readonly_database(path):
    checked = safe_file(path)
    identity = checked.stat()
    with open(checked, 'rb') as source:
        header = source.read(100)
    if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
        raise ValueError('Only rollback-journal SQLite files are supported; WAL sidecar writes are forbidden.')
    connection = sqlite3.connect(checked.as_uri() + '?mode=ro', uri=True)
    try:
        if not os.path.samestat(identity, checked.stat()):
            raise ValueError('Database identity changed while opening it.')
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        permitted = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_TRANSACTION}
        connection.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in permitted else sqlite3.SQLITE_DENY)
        connection.execute('BEGIN')
        yield connection
    finally:
        connection.rollback()
        connection.close()


def read_manifest(path, key, protected):
    if not key or len(key.encode()) < 32:
        raise ValueError('A private manifest verification key of at least 32 bytes is required.')
    source = safe_file(path)
    if source.stat().st_size > 2_000_000:
        raise ValueError('Manifest exceeds the D1 size limit.')
    try:
        envelope = json.loads(source.read_text(encoding='utf-8'))
        payload, signature = envelope['payload'], envelope['signature']
        expected = hmac.new(key.encode(), canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            raise ValueError('Manifest authenticity could not be verified.')
        if payload['dataset'] != DATASET or payload['version'] != 1 or payload['plan_digest'] != PLAN_DIGEST:
            raise ValueError('Unknown dataset or manifest version.')
        if payload['state'] != 'complete' or uuid_hex(payload['protected_uuid']) != protected:
            raise ValueError('Partial dataset or protected UUID mismatch.')
        if set(payload['inventory']) != set(TABLES):
            raise ValueError('Manifest inventory is incomplete.')
        return payload
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('Malformed manifest; no data may be adopted.') from None


def inventory_digest(rows):
    return hashlib.sha256(canonical_json(sorted([dict(row) for row in rows], key=lambda row: row['id'])).encode()).hexdigest()


def audit(path, config, manifest_path=None):
    protected = uuid_hex(getattr(config, 'DEMO_PROTECTED_ORGANIZATION_UUID', None))
    manifest = read_manifest(manifest_path, getattr(config, 'DEMO_MANIFEST_KEY', ''), protected) if manifest_path else None
    issues = []
    try:
        with readonly_database(path) as db:
            for table in TABLES:
                columns = 'id' if table in ('organization', 'user') else 'id, organization_id'
                db.execute(f'SELECT {columns} FROM "{table}" LIMIT 0')
            protected_row = db.execute('SELECT id, name FROM organization WHERE id=?', (protected,)).fetchone()
            if not protected_row or protected_row['name'].strip().casefold() != 'rancho los hermanos':
                raise ValueError('Protected UUID does not identify Rancho los Hermanos.')
            organizations = []
            for name, code, *_ in PLAN:
                matches = db.execute('SELECT * FROM organization WHERE name=? OR code=? OR slug=?', (name, code, slugify(name))).fetchall()
                if matches and (len(matches) != 1 or matches[0]['name'] != name or matches[0]['code'] != code or matches[0]['slug'] != slugify(name)):
                    raise ValueError('Organization name/code/slug collision; no adoption is allowed.')
                organizations.extend(matches)
            emails = demo_emails()
            users = db.execute('SELECT * FROM user WHERE lower(email) IN (' + ','.join('?' for _ in emails) + ')', emails).fetchall()
            if not manifest and (organizations or users):
                raise ValueError('Existing unknown or partial demo dataset; no adoption is allowed.')
            if manifest:
                if len(organizations) != 5 or len(users) != 30:
                    raise ValueError('Manifest references a partial dataset.')
                org_ids = [row['id'] for row in organizations]
                if protected in org_ids:
                    raise ValueError('Protected organization cannot be part of the demo dataset.')
                user_ids = [row['id'] for row in users]
                for table in TABLES:
                    if table == 'organization':
                        rows = organizations
                    elif table == 'user':
                        rows = users
                    else:
                        column, ids = ('user_id', user_ids) if table == 'memberships' else ('organization_id', org_ids)
                        rows = db.execute(f'SELECT * FROM "{table}" WHERE {column} IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
                    receipt = manifest['inventory'][table]
                    if receipt != {'count': len(rows), 'digest': inventory_digest(rows)}:
                        raise ValueError('Dataset differs from its signed inventory; no repair is allowed.')
                for org, (_, _, users_count, farms, lots, animals) in zip(organizations, PLAN):
                    for table, count in [('memberships', users_count), ('farms', farms), ('lots', lots), ('animals', animals)]:
                        actual = db.execute(f'SELECT count(*) FROM "{table}" WHERE organization_id=?', (org['id'],)).fetchone()[0]
                        if actual != count:
                            raise ValueError('Dataset quotas differ from the signed plan.')
                for user in users:
                    memberships = db.execute('SELECT * FROM memberships WHERE user_id=?', (user['id'],)).fetchall()
                    if len(memberships) != 1 or memberships[0]['organization_id'] not in org_ids or not memberships[0]['is_default'] or not memberships[0]['is_active']:
                        raise ValueError('Demo membership is partial or crosses tenants.')
                    expected_org = next(org['id'] for org in organizations if user['email'].lower().startswith(org['code'].lower() + '.'))
                    if memberships[0]['organization_id'] != expected_org:
                        raise ValueError('Demo user belongs to the wrong organization.')
            required = {
                'catalog_farm_types': ('RANCH',), 'catalog_genders': ('F', 'M'),
                'catalog_animal_statuses': ('ACTIVE', 'SOLD'), 'catalog_movement_types': ('TRANSFER', 'SALE'),
                'catalog_production_types': ('MILK',),
            }
            for table, codes in required.items():
                for code in codes:
                    if db.execute(f'SELECT count(*) FROM "{table}" WHERE code=? AND is_active=1', (code,)).fetchone()[0] != 1:
                        issues.append(f'Missing or ambiguous active catalog: {table}/{code}.')
            bindings = getattr(config, 'DEMO_CATALOG_BINDINGS', {})
            for table in ('catalog_species', 'catalog_breeds', 'catalog_weighing_methods', 'catalog_breeding_types'):
                identifier = bindings.get(table)
                if not identifier:
                    issues.append(f'Explicit catalog UUID required: {table}.')
                elif db.execute(f'SELECT count(*) FROM "{table}" WHERE id=? AND is_active=1', (uuid_hex(identifier),)).fetchone()[0] != 1:
                    issues.append(f'Missing active catalog binding: {table}.')
            if bindings.get('catalog_breeds') and bindings.get('catalog_species'):
                breed = db.execute('SELECT species_id FROM catalog_breeds WHERE id=?', (uuid_hex(bindings['catalog_breeds']),)).fetchone()
                if not breed or breed[0] != uuid_hex(bindings['catalog_species']):
                    issues.append('Breed does not belong to the selected species.')
    except sqlite3.Error:
        raise ValueError('Read-only inspection failed: unavailable schema, database or query.') from None
    return {'state': 'recognized-complete' if manifest else 'fresh', 'issues': issues}
