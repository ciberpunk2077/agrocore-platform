"""D6C-1: identity/authentication core and test-only orchestration.

Persistent activation and authorization issuance deliberately have no entry point.
Every mutating entry point still requires the unmodified D2 disposable DB guard.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import ctypes
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4

from django.db import connections

from . import backup, d2, d3, d4
from .delivery import EncryptedTestDelivery
from .preflight import canonical_json, safe_file
from .windows_acl import verify_private


def identity(path):
    path = safe_file(path)
    info = path.stat()
    return {'path': str(path), 'device': info.st_dev, 'file_id': info.st_ino}


def identity_directory(path):
    path = backup.directory(path)
    info = path.stat()
    return {'path': str(path), 'device': info.st_dev, 'file_id': info.st_ino}


@dataclass(frozen=True)
class Binding:
    original: Path
    copy: Path
    backup_file: Path
    receipt_file: Path
    receipt_hash: str
    original_identity: dict
    copy_identity: dict
    original_hash: str
    copy_hash: str
    protected_uuid: str

    def revalidate(self, *, fresh=True):
        if (identity(self.original) != self.original_identity
                or identity(self.copy) != self.copy_identity
                or os.path.samefile(self.original, self.copy)
                or backup.digest(self.original) != self.original_hash
                or backup.digest(safe_file(self.receipt_file)) != self.receipt_hash):
            raise d2.D2Error('Database or receipt identity changed; authorization rejected.')
        verify_private(self.receipt_file)
        verify_private(self.copy)
        receipt = json.loads(self.receipt_file.read_text(encoding='utf-8'))
        if backup.digest(safe_file(self.backup_file)) != receipt['backup_sha256']:
            raise d2.D2Error('Backup changed.')
        verify_private(self.backup_file)
        if fresh and (backup.digest(self.copy) != self.copy_hash
                      or backup.inspect_database(self.copy) != receipt['snapshot']):
            raise d2.D2Error('Rehearsal changed after preflight.')


def bind_verified_files(original, copy, backup_file, receipt_file):
    """Read-only core. Caller must derive paths from trusted D6B provenance."""
    original, copy, backup_file, receipt_file = map(safe_file, (original, copy, backup_file, receipt_file))
    if os.path.samefile(original, copy) or os.path.samefile(backup_file, copy):
        raise d2.D2Error('Original/backup aliases cannot be a write target.')
    verify_private(receipt_file)
    if receipt_file.stat().st_size > 1024 * 1024:
        raise d2.D2Error('Receipt size rejected.')
    try:
        receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
        from uuid import UUID
        if (receipt['version'] != 'D6B' or str(UUID(receipt['run_id'])) != receipt['run_id']
                or receipt['protected_uuid'] != backup.PROTECTED or receipt['source'] != str(original)
                or receipt['source_sha256'] != backup.digest(original)
                or receipt['rehearsal_sha256'] != backup.digest(copy)
                or receipt['backup_sha256'] != backup.digest(backup_file)
                or backup.inspect_database(copy) != receipt['snapshot']
                or backup.inspect_database(backup_file) != receipt['snapshot']
                or backup.inspect_database(original) != receipt['snapshot']):
            raise d2.D2Error('D6B receipt or consistent snapshots rejected.')
        binding = Binding(original, copy, backup_file, receipt_file, backup.digest(receipt_file),
                          identity(original), identity(copy), backup.digest(original),
                          backup.digest(copy), receipt['protected_uuid'])
        binding.revalidate()
        return binding
    except (KeyError, TypeError, ValueError):
        raise d2.D2Error('Invalid D6B binding; no write authorization.') from None


def inspect_persistent(run_id):
    """Only persistent operation exposed in D6C-1: verified read-only inspection."""
    with backup.frozen_source(backup.ORIGINAL):
        copy = backup.rehearsal_path(run_id)
        root = backup.storage()
        with backup.frozen_source(copy):
            return bind_verified_files(backup.ORIGINAL, copy, root / 'backups' / run_id / 'database.sqlite3',
                                       copy.parent / 'receipt.json')


@contextmanager
def pinned_copy(binding):
    """Deny rename/delete/replacement while allowing this SQLite connection to write."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(binding.copy), 0x80000000, 3, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise d2.D2Error('Cannot pin rehearsal identity.')
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


class DisposableAuthority:
    """HMAC authority for disposable tests ONLY; no real issuer or CLI."""
    def __init__(self, directory, *, authority_key=None):
        root = d2.test_database().parent
        self.directory = Path(directory)
        if self.directory.parent != root:
            raise d2.D2Error('Authorization ledger must be disposable.')
        backup.private_directory(self.directory)
        info = self.directory.stat()
        self.directory_identity = (info.st_dev, info.st_ino)
        if authority_key is not None and (not isinstance(authority_key, bytes) or len(authority_key) != 32):
            raise d2.D2Error('Invalid disposable authority key.')
        self.key = authority_key if authority_key is not None else secrets.token_bytes(32)

    def issue(self, binding, *, recovery=False, lifetime=60):
        if binding.copy != d2.test_database() or binding.original.parent != binding.copy.parent:
            raise d2.D2Error('Only a disposable fixture can receive authorization.')
        binding.revalidate(fresh=not recovery)
        if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or not 0 < lifetime <= 300:
            raise d2.D2Error('Authorization lifetime rejected.')
        payload = {'nonce': str(uuid4()), 'expires': time.time() + lifetime,
                   'copy': binding.copy_identity, 'receipt': binding.receipt_hash,
                   'original': binding.original_identity, 'recovery': recovery,
                   'ledger': {'path': str(self.directory), 'identity': list(self.directory_identity)}}
        payload = json.loads(canonical_json(payload))  # No mutable alias to the captured binding.
        return {'payload': payload, 'signature': hmac.new(self.key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()}

    def consume(self, token, binding, *, recovery):
        if binding.copy != d2.test_database():
            raise d2.D2Error('Persistent authorization consumption disabled.')
        backup.directory(self.directory)
        info = self.directory.stat()
        if self.directory.parent != binding.copy.parent or (info.st_dev, info.st_ino) != self.directory_identity:
            raise d2.D2Error('Authorization ledger replaced.')
        verify_private(self.directory)
        try:
            payload = token['payload']
            signature = hmac.new(self.key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
            if (set(payload) != {'nonce', 'expires', 'copy', 'receipt', 'original', 'recovery', 'ledger'}
                    or payload['ledger'] != {'path': str(self.directory), 'identity': list(self.directory_identity)}
                    or type(payload['expires']) not in (int, float) or not math.isfinite(payload['expires'])
                    or type(payload['recovery']) is not bool
                    or not hmac.compare_digest(signature, token['signature']) or payload['expires'] <= time.time()
                    or payload['expires'] > time.time() + 300
                    or payload['copy'] != binding.copy_identity or payload['receipt'] != binding.receipt_hash
                    or payload['original'] != binding.original_identity or payload['recovery'] != recovery):
                raise d2.D2Error('Authorization rejected.')
            from uuid import UUID
            nonce = str(UUID(payload['nonce']))
            if nonce != payload['nonce']:
                raise d2.D2Error('Authorization nonce rejected.')
            # Durable exclusive ledger entry; a failed execution burns its token too.
            with open(self.directory / (nonce + '.used'), 'x', encoding='ascii') as stream:
                stream.write(hashlib.sha256(canonical_json(payload).encode()).hexdigest())
                stream.flush()
                os.fsync(stream.fileno())
            verify_private(self.directory / (nonce + '.used'))
        except (KeyError, TypeError, ValueError, OSError):
            raise d2.D2Error('Invalid, expired or reused authorization.') from None

    def recover_binding(self, consumed_token, *, backup_file, receipt_file):
        """A used grant is provenance ONLY, never permission to execute again."""
        path = d2.test_database()
        root = path.parent
        backup.directory(self.directory)
        verify_private(self.directory)
        try:
            payload = consumed_token['payload']
            signature = hmac.new(self.key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()
            if (not hmac.compare_digest(signature, consumed_token['signature'])
                    or payload['ledger'] != {'path': str(self.directory), 'identity': list(self.directory_identity)}):
                raise d2.D2Error('Recovery provenance rejected.')
            from uuid import UUID
            nonce = str(UUID(payload['nonce']))
            if nonce != payload['nonce']:
                raise d2.D2Error('Recovery nonce rejected.')
            used = safe_file(self.directory / (nonce + '.used'))
            verify_private(used)
            if used.read_text(encoding='ascii') != hashlib.sha256(canonical_json(payload).encode()).hexdigest():
                raise d2.D2Error('No durable consumption evidence.')
            original = safe_file(payload['original']['path'])
            backup_file, receipt_file = map(safe_file, (backup_file, receipt_file))
            if original.parent != root or not all(item.is_relative_to(root) for item in (backup_file, receipt_file)):
                raise d2.D2Error('Recovery is restricted to disposable fixtures.')
            if (identity(path) != payload['copy'] or identity(original) != payload['original']
                    or os.path.samefile(original, path) or os.path.samefile(backup_file, path)
                    or backup.digest(receipt_file) != payload['receipt']):
                raise d2.D2Error('Recovery file identity rejected.')
            verify_private(receipt_file)
            if receipt_file.stat().st_size > 1024 * 1024:
                raise d2.D2Error('Recovery receipt size rejected.')
            receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
            if (receipt['version'] != 'D6B' or receipt['source'] != str(original)
                    or str(UUID(receipt['run_id'])) != receipt['run_id']
                    or receipt['protected_uuid'] != backup.PROTECTED
                    or backup.digest(original) != receipt['source_sha256']
                    or backup.digest(backup_file) != receipt['backup_sha256']
                    or backup.inspect_database(original) != receipt['snapshot']
                    or backup.inspect_database(backup_file) != receipt['snapshot']):
                raise d2.D2Error('Immutable D6B recovery reference rejected.')
            binding = Binding(original, path, backup_file, receipt_file, payload['receipt'],
                dict(payload['original']), dict(payload['copy']), receipt['source_sha256'],
                receipt['rehearsal_sha256'], receipt['protected_uuid'])
            binding.revalidate(fresh=False)
            return binding  # Must receive a NEW recovery authorization before execution.
        except (KeyError, TypeError, ValueError, OSError):
            raise d2.D2Error('Recovery binding could not be reconstructed safely.') from None


def delivery_set(directories, *, encryption_key):
    """Uses existing encrypted delivery and all its unchanged disposable guards."""
    d2.test_database()
    if len(directories) != 3 or len(set(map(str, directories))) != 3:
        raise d2.D2Error('Three distinct private delivery directories required.')
    return tuple(EncryptedTestDelivery(path, encryption_key=encryption_key) for path in directories)


def candidate_write_configuration(binding, *, settings_module):
    """Design-only config builder: no connection, grant or global settings change."""
    if settings_module != 'config.settings.demo_rehearsal_write':
        raise d2.D2Error('Local, production and unknown write settings forbidden.')
    binding.revalidate()
    return {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(binding.copy), 'OPTIONS': {}}}


def assert_reference_rows(binding):
    """Recovery cannot adopt changes to any row present in the D6B reference."""
    from contextlib import closing
    db = connections['default'].connection
    with closing(sqlite3.connect(binding.original.as_uri() + '?mode=ro', uri=True,
                                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)) as original:
        original.execute('PRAGMA query_only=ON')
        schema = original.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        if db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall() != schema:
            raise d2.D2Error('Rehearsal schema changed; no recovery allowed.')
        for name, in original.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            quoted = '"' + name.replace('"', '""') + '"'
            columns = original.execute('PRAGMA table_info(' + quoted + ')').fetchall()
            keys = [index for index, column in enumerate(columns) if column[5]] or list(range(len(columns)))
            where = ' AND '.join('"' + columns[index][1].replace('"', '""') + '" IS ?' for index in keys)
            for row in original.execute('SELECT * FROM ' + quoted):
                current = db.execute('SELECT * FROM ' + quoted + ' WHERE ' + where, tuple(row[index] for index in keys)).fetchall()
                if current != [row]:
                    raise d2.D2Error('Preexisting D6B reference row altered; recovery rejected.')


def run_disposable(binding, authority, token, deliveries, *, signing_key, recovery=False, dry_run=False):
    """Commits D2, D3 and D4 separately. No generic/persistent writer exists."""
    path = d2.test_database()
    if path != binding.copy or binding.original == backup.ORIGINAL:
        raise d2.D2Error('Persistent/original targets forbidden in D6C-1.')
    if len(deliveries) != 3:
        raise d2.D2Error('Complete encrypted delivery set required.')
    # Lock only adapter sessions. Per-phase D1 mutexes remain untouched.
    from .preflight import run_lock
    with run_lock(binding.receipt_file), backup.frozen_source(binding.original), pinned_copy(binding):
        binding.revalidate(fresh=not recovery)
        if dry_run:
            # Never mint/consume credentials or authorization during dry-run.
            backup.check_migrations(path)
            if not recovery:
                backup.preflight(path)
            result = d2.create_d2(binding.protected_uuid, deliveries[0], signing_key=signing_key, dry_run=True)
            plan = {'state': 'read-only', 'D2': result}
            if deliveries[0].load() is None or deliveries[0].pending.exists():
                plan['later_phases'] = 'require published D2 parent receipt'
                return plan
            if deliveries[2].load() is None:
                plan['D3'] = d3.create_d3(binding.protected_uuid, deliveries[0], deliveries[1], signing_key=signing_key,
                                           species_code='BOV', breed_code='HOL', dry_run=True)
                if deliveries[1].load() is None or deliveries[1].pending.exists():
                    plan['later_phases'] = 'require published D3 parent receipt'
                    return plan
            plan['D4'] = d4.create_d4(binding.protected_uuid, *deliveries, signing_key=signing_key,
                species_code='BOV', breed_code='HOL', weighing_method_code='SCALE', breeding_type_code='NAT', dry_run=True)
            return plan
        connections['default'].close()
        binding.revalidate(fresh=not recovery)  # Immediately before opening the write connection.
        authority.consume(token, binding, recovery=recovery)
        connections['default'].ensure_connection()
        try:
            if identity(path) != binding.copy_identity:
                raise d2.D2Error('File replaced while connecting.')
            # Connection-level exclusion survives the separate phase commits.
            db = connections['default'].connection
            db.execute('PRAGMA busy_timeout=0')
            if db.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone()[0] != 'exclusive':
                raise d2.D2Error('Exclusive SQLite locking unavailable.')
            db.execute('BEGIN EXCLUSIVE')
            db.execute('COMMIT')
            if not recovery and backup.digest(path) != binding.copy_hash:
                raise d2.D2Error('Rehearsal changed while opening connection.')
            return _certified_phases(binding, deliveries, signing_key=signing_key)
        finally:
            connections['default'].close()  # Releases exclusive locks even after a failure.


def _certified_phases(binding, deliveries, *, signing_key):
    """Shared phase runner; still guarded before any service can write."""
    if d2.test_database() != binding.copy:
        raise d2.D2Error('Phase connection differs from the authorized copy.')
    assert_reference_rows(binding)
    result2 = d2.create_d2(binding.protected_uuid, deliveries[0], signing_key=signing_key)
    if deliveries[2].load() is None:
        result3 = d3.create_d3(binding.protected_uuid, deliveries[0], deliveries[1], signing_key=signing_key,
                               species_code='BOV', breed_code='HOL')
    else:
        result3 = {'state': 'validated-by-D4-parent-chain'}
    result4 = d4.create_d4(binding.protected_uuid, *deliveries, signing_key=signing_key,
                           species_code='BOV', breed_code='HOL', weighing_method_code='SCALE', breeding_type_code='NAT')
    assert_reference_rows(binding)
    return {'D2': result2, 'D3': result3, 'D4': result4}
