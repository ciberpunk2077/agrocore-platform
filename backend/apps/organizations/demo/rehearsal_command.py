"""D6C-2A controlled CLI integration. No production authorization issuer."""
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from uuid import UUID

from django.conf import settings
from django.apps import apps
from django.db import connections
from django.db.backends.sqlite3.base import DatabaseWrapper
from django.db.utils import ConnectionHandler

from . import backup, d2, rehearsal_adapter as adapter
from .preflight import canonical_json, run_lock, safe_file
from .rehearsal_locations import Locations, persistent_locations
from .windows_acl import current_sid, verify_private

VERSION = 'D6C-2A-v1'
FIELDS = {'version', 'run_id', 'nonce', 'expires', 'mode', 'sid', 'copy', 'original', 'receipt', 'ledger', 'artifacts'}
RUNTIME = 'config.settings.demo_rehearsal_execution'
_SEAL = object()


class _Consumption:
    """One in-process handoff after exclusive durable nonce creation."""
    def __init__(self, seal, authority, token):
        if seal is not _SEAL:
            raise d2.D2Error('Invalid authorization handoff.')
        self.authority, self.token, self.claimed = authority, token, False
        self.owner = (os.getpid(), threading.get_ident())

    def claim(self, authority):
        if self.claimed or self.authority is not authority or self.owner != (os.getpid(), threading.get_ident()):
            raise d2.D2Error('Authorization handoff reused or moved.')
        self.claimed = True
        authority.verify_used(self.token)
        return self.token


def locations_for_command(run_id, *, execute):
    if str(UUID(run_id)) != run_id:
        raise d2.D2Error('Canonical run UUID required.')
    module = settings.SETTINGS_MODULE
    if module == 'config.settings.demo_d2_testing':
        path = d2.test_database()  # Preserve the original strict disposable guard.
        plan = getattr(settings, 'DEMO_CONTROLLED_TEST_LOCATIONS', None)
        if (type(plan) is not Locations or not plan.testing or plan.run_id != run_id
                or plan.copy != path or plan.original.parent != path.parent
                or plan.artifact_root != path.parent / ('controlled-' + run_id)
                or not all(item.is_relative_to(path.parent) for item in (plan.backup_file, plan.receipt_file))):
            raise d2.D2Error('Controlled disposable locations rejected.')
    else:
        if module not in {RUNTIME, 'config.settings.local', 'config.settings.demo_rehearsal'} or execute and module != RUNTIME:
            raise d2.D2Error('Execution requires dedicated rehearsal settings; local/production cannot write.')
        plan = persistent_locations(run_id)
        if execute:
            expected = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                'NAME': plan.copy.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}}
            if (settings.DATABASE_ROUTERS or ConnectionHandler(deepcopy(settings.DATABASES)).settings
                    != ConnectionHandler(expected).settings):
                raise d2.D2Error('Rehearsal settings destination rejected.')
    plan.verify()
    return plan


def _private_directory(path):
    backup.directory(path)
    verify_private(path)
    return adapter.identity_directory(path)


def _private_tree(path, root):
    path, root = Path(path), Path(root)
    if not path.is_relative_to(root):
        raise d2.D2Error('Artifact directory escaped its authorized root.')
    while True:
        _private_directory(path)
        if path == root:
            return
        path = path.parent


def _read_json(path, *, limit=65536):
    path = safe_file(path)
    verify_private(path)
    if path.stat().st_size > limit:
        raise d2.D2Error('Oversized authorization.')
    def distinct_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise d2.D2Error('Duplicate authorization fields.')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=distinct_pairs)


def artifact_digest(plan):
    return hashlib.sha256(canonical_json({'keys': str(plan.keys), 'grants': str(plan.grants),
        'ledger': str(plan.ledger), 'deliveries': list(map(str, plan.deliveries))}).encode()).hexdigest()


class _Authority:
    """Read existing private keys/grants only. No issue() or automatic provisioning."""
    def __init__(self, plan):
        self.plan = plan
        _private_tree(plan.keys, plan.artifact_root)
        _private_tree(plan.grants, plan.artifact_root)
        _private_tree(plan.ledger, plan.artifact_root)
        self.ledger_identity = _private_directory(plan.ledger)
        self.keys = {}
        self.key_files = {}
        for name in ('authorization', 'encryption', 'dataset-signing'):
            path = safe_file(plan.keys / (name + '.key'))
            verify_private(path)
            if path.stat().st_size != 32:
                raise d2.D2Error('Private key size rejected.')
            value = path.read_bytes()
            if len(value) != 32:
                raise d2.D2Error('Private key format rejected.')
            self.keys[name] = value
            self.key_files[name] = (path, adapter.identity(path), backup.digest(path))
        if len(set(self.keys.values())) != 3:
            raise d2.D2Error('Authorization, encryption and dataset keys must be separate.')

    def verify(self, path, *, live, mode=None):
        path = safe_file(path)
        if path.parent != self.plan.grants or path.suffix != '.json' or str(UUID(path.stem)) != path.stem:
            raise d2.D2Error('Authorization must belong to the exact run grants directory.')
        token = _read_json(path)
        payload = token['payload']
        signature = hmac.new(self.keys['authorization'], canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        if (set(token) != {'payload', 'signature'} or set(payload) != FIELDS
                or not hmac.compare_digest(signature, token['signature'])
                or payload['version'] != VERSION or payload['run_id'] != self.plan.run_id
                or payload['nonce'] != path.stem or payload['mode'] not in ('execute', 'resume')
                or mode is not None and payload['mode'] != mode
                or payload['sid'] != current_sid() or payload['artifacts'] != artifact_digest(self.plan)
                or payload['ledger'] != self.ledger_identity
                or payload['copy'] != adapter.identity(self.plan.copy)
                or payload['original'] != adapter.identity(self.plan.original)
                or payload['receipt'] != backup.digest(self.plan.receipt_file)
                or type(payload['expires']) not in (int, float) or not math.isfinite(payload['expires'])):
            raise d2.D2Error('Signed authorization scope rejected.')
        if live and not time.time() < payload['expires'] <= time.time() + 300:
            raise d2.D2Error('Authorization expired or outside the allowed lifetime.')
        self.verify_files()
        return token

    def verify_files(self):
        for folder in (self.plan.keys, self.plan.grants, self.plan.ledger):
            _private_tree(folder, self.plan.artifact_root)
        if _private_directory(self.plan.ledger) != self.ledger_identity:
            raise d2.D2Error('Authorization ledger replaced.')
        for path, identity, digest in self.key_files.values():
            verify_private(path)
            if adapter.identity(path) != identity or backup.digest(path) != digest:
                raise d2.D2Error('Private key replaced during execution.')

    def used_path(self, token):
        return self.plan.ledger / (token['payload']['nonce'] + '.used')

    def verify_used(self, token):
        path = safe_file(self.used_path(token))
        verify_private(path)
        if path.read_text(encoding='ascii') != hashlib.sha256(canonical_json(token['payload']).encode()).hexdigest():
            raise d2.D2Error('Durable authorization consumption evidence rejected.')

    def consume(self, path, binding, *, mode):
        if self.plan != locations_for_command(self.plan.run_id, execute=True):
            raise d2.D2Error('Unauthorized consumption locations.')
        token = self.verify(path, live=True, mode=mode)
        binding.revalidate(fresh=mode == 'execute')
        self.verify_files()
        with open(self.used_path(token), 'x', encoding='ascii') as stream:
            stream.write(hashlib.sha256(canonical_json(token['payload']).encode()).hexdigest())
            stream.flush()
            os.fsync(stream.fileno())
        self.verify_used(token)
        return _Consumption(_SEAL, self, token)


def _binding(plan, authority=None, reference=None):
    if reference is None:
        return adapter.bind_verified_files(plan.original, plan.copy, plan.backup_file, plan.receipt_file)
    token = authority.verify(reference, live=False)
    authority.verify_used(token)  # Expired reference is provenance, never new permission.
    receipt = plan.receipt()
    plan.verify()
    binding = adapter.Binding(plan.original, plan.copy, plan.backup_file, plan.receipt_file,
        token['payload']['receipt'], token['payload']['original'], token['payload']['copy'],
        receipt['source_sha256'], receipt['rehearsal_sha256'], receipt['protected_uuid'])
    binding.revalidate(fresh=False)
    return binding


class _Session:
    """Live grant-bound capability, checked by D2/D3/D4 and encrypted staging."""
    def __init__(self, plan, binding, authority, grant_file, proof, wrapper):
        if type(authority) is not _Authority or type(proof) is not _Consumption or plan != authority.plan:
            raise d2.D2Error('Invalid live execution authority.')
        token = proof.claim(authority)
        self.plan, self.binding, self.authority = plan, binding, authority
        self.grant_file, self.token, self.wrapper = grant_file, token, wrapper
        self.grant_identity, self.grant_hash = adapter.identity(grant_file), backup.digest(grant_file)
        self.thread, self.pid = threading.get_ident(), os.getpid()
        self.module = settings.SETTINGS_MODULE
        self.live = True

    def validate(self, *, _allow_atomic=False):
        if (not self.live or threading.get_ident() != self.thread or os.getpid() != self.pid
                or settings.SETTINGS_MODULE != self.module
                or self.module not in {RUNTIME, 'config.settings.demo_d2_testing'}
                or connections['default'] is not self.wrapper or settings.DATABASE_ROUTERS
                or self.wrapper.settings_dict['ENGINE'] != 'django.db.backends.sqlite3'
                or self.wrapper.settings_dict['NAME'] != str(self.binding.copy)
                or self.wrapper.settings_dict.get('OPTIONS')
                or self.wrapper.in_atomic_block and not _allow_atomic):
            raise d2.D2Error('Controlled rehearsal connection scope rejected.')
        if self.plan.testing:
            from tempfile import gettempdir
            root = Path(settings.DEMO_D2_TEST_ROOT)
            if (root.parent != Path(gettempdir()).resolve() or not root.name.startswith('agrocore-d2-')
                    or self.binding.copy != root / 'disposable.sqlite3'):
                raise d2.D2Error('Disposable scope identity rejected.')
        elif self.binding.original != backup.ORIGINAL or self.binding.copy == backup.ORIGINAL:
            raise d2.D2Error('Original destination forbidden.')
        if not self.plan.testing:
            expected = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                'NAME': self.binding.copy.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}}
            if ConnectionHandler(deepcopy(settings.DATABASES)).settings != ConnectionHandler(expected).settings:
                raise d2.D2Error('Normal settings changed during controlled execution.')
        self.binding.revalidate(fresh=False)
        self.authority.verify_files()
        self.authority.verify_used(self.token)
        if adapter.identity(self.grant_file) != self.grant_identity or backup.digest(self.grant_file) != self.grant_hash:
            raise d2.D2Error('Consumed grant file replaced.')
        # Recheck signature/context without treating an in-flight grant as a new use.
        if self.authority.verify(self.grant_file, live=False) != self.token:
            raise d2.D2Error('Consumed grant changed.')
        return self.binding.copy

    def revoke(self):
        self.live = False


class _Delivery:
    """Authenticated bundles; staging/publishing requires the live consumed scope."""
    def __init__(self, session, directory):
        from cryptography.fernet import Fernet
        if directory not in session.plan.deliveries:
            raise d2.D2Error('Unplanned delivery directory.')
        self.session, self.directory = session, directory
        self.pending, self.final = directory / 'd2.pending', directory / 'd2.bundle'
        self.cipher = Fernet(base64.urlsafe_b64encode(session.authority.keys['encryption']))
        _private_tree(directory, session.plan.artifact_root)

    def load(self):
        self.session.validate()
        _private_directory(self.directory)
        if self.pending.exists() and self.final.exists():
            raise d2.D2Error('Ambiguous encrypted publication state.')
        path = self.final if self.final.exists() else self.pending
        if not path.exists():
            return None
        path = safe_file(path)
        verify_private(path)
        if path.stat().st_size > 2_000_000:
            raise d2.D2Error('Oversized encrypted bundle.')
        return json.loads(self.cipher.decrypt(path.read_bytes()).decode('utf-8'))

    def stage(self, bundle):
        self.session.validate(_allow_atomic=True)
        _private_directory(self.directory)
        if self.final.exists():
            raise d2.D2Error('Existing bundle cannot be overwritten.')
        payload = self.cipher.encrypt(canonical_json(bundle).encode())
        fd = os.open(self.pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        verify_private(safe_file(self.pending))

    def publish(self):
        self.session.validate()
        _private_directory(self.directory)
        if self.final.exists():
            if self.pending.exists():
                raise d2.D2Error('Ambiguous encrypted publication state.')
            verify_private(safe_file(self.final))
            return
        verify_private(safe_file(self.pending))
        if os.name != 'nt':
            raise d2.D2Error('Private publication requires Windows.')
        os.rename(self.pending, self.final)  # No overwrite on Windows.


def _prepare_deliveries(plan):
    # Called ONLY after verifying and consuming a future authorization.
    for path in (plan.artifact_root / 'deliveries', plan.artifact_root / 'deliveries' / plan.run_id, *plan.deliveries):
        backup.private_directory(path)


@contextmanager
def _readonly_connection(path):
    old = connections['default']
    old.close()
    config = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.sqlite3',
        'NAME': path.as_uri() + '?mode=ro', 'OPTIONS': {'uri': True}}}).settings['default']
    wrapper = DatabaseWrapper(config, alias='default')
    connections['default'] = wrapper
    try:
        wrapper.ensure_connection()
        yield
    finally:
        wrapper.close()
        connections['default'] = old


def _read_bundle(plan, authority, directory):
    from cryptography.fernet import Fernet
    if not directory.exists():
        return None, 'not-started'
    _private_directory(directory)
    pending, final = directory / 'd2.pending', directory / 'd2.bundle'
    if pending.exists() and final.exists():
        raise d2.D2Error('Ambiguous phase files; investigation required.')
    path = final if final.exists() else pending
    if not path.exists():
        return None, 'not-started'
    path = safe_file(path)
    verify_private(path)
    if path.stat().st_size > 2_000_000:
        raise d2.D2Error('Oversized phase bundle.')
    cipher = Fernet(base64.urlsafe_b64encode(authority.keys['encryption']))
    return json.loads(cipher.decrypt(path.read_bytes()).decode()), 'complete' if final.exists() else 'publication-pending'


def _reject_unowned_rows(binding, parent):
    from contextlib import closing
    from uuid import UUID
    inventory = parent['receipt']['payload']['inventory']
    allowed = {model: {UUID(value) for value in inventory[name]['ids']} for name, model in d2.MODELS.items()}
    organizations = allowed[d2.Organization]
    domain_labels = {model._meta.label for model in adapter.d3.DOMAIN_MODELS.values()} | set(adapter.d3.D4_LABELS)
    with closing(sqlite3.connect(binding.original.as_uri() + '?mode=ro', uri=True)) as original:
        for model in apps.get_models():
            if not model._meta.managed or model._meta.proxy:
                continue
            table = '"' + model._meta.db_table.replace('"', '""') + '"'
            pk = '"' + model._meta.pk.column.replace('"', '""') + '"'
            old = {model._meta.pk.to_python(row[0]) for row in original.execute('SELECT ' + pk + ' FROM ' + table)}
            extra = model._base_manager.exclude(pk__in=old)
            if model in allowed:
                if set(extra.values_list('pk', flat=True)) != allowed[model]:
                    raise d2.D2Error('Unowned identity rows detected; resume refused.')
            elif model._meta.label in domain_labels:
                if extra.exclude(organization_id__in=organizations).exists():
                    raise d2.D2Error('Unowned tenant rows detected; resume refused.')
            elif extra.exists():
                raise d2.D2Error('Unexpected global records detected; resume refused.')


def _phase_status(plan, binding, authority):
    """Validate signed inventories with a physically read-only ORM connection."""
    with _readonly_connection(plan.copy):
        adapter.assert_reference_rows(binding)
        bundles, states = zip(*(_read_bundle(plan, authority, path) for path in plan.deliveries))
        parent2, parent3, child4 = bundles
        protected = d2._protected(binding.protected_uuid)
        if parent2 is None:
            if parent3 is not None or child4 is not None:
                raise d2.D2Error('Missing D2 parent provenance.')
            binding.revalidate()
            d2._collisions()
            return dict(zip(('D2', 'D3', 'D4'), states))
        d2._verify(parent2, authority.keys['dataset-signing'], protected)
        _reject_unowned_rows(binding, parent2)
        org_ids = parent2['receipt']['payload']['inventory']['organizations']['ids']
        if child4 is not None:
            if parent3 is None:
                raise d2.D2Error('Missing D3 parent provenance.')
            catalogs = adapter.d4._catalogs('BOV', 'HOL', 'SCALE', 'NAT')
            adapter.d4._signed_parent(parent3, parent2, authority.keys['dataset-signing'])
            adapter.d4._verify_d4(child4, parent2, parent3, authority.keys['dataset-signing'], org_ids, catalogs)
        elif parent3 is not None:
            adapter.d3._verify_d3(parent3, parent2, authority.keys['dataset-signing'], org_ids)
            catalogs = adapter.d3.resolve_catalogs('BOV', 'HOL')
            if parent3['receipt']['payload']['catalogs'] != {name: str(row.pk) for name, row in catalogs.items()}:
                raise d2.D2Error('D3 catalog provenance diverged.')
            if any(apps.get_model(label)._base_manager.filter(organization_id__in=org_ids).exists() for label in adapter.d3.D4_LABELS):
                raise d2.D2Error('Unconfirmed partial D4 dataset.')
        elif any(model._base_manager.filter(organization_id__in=org_ids).exists() for model in adapter.d3.DOMAIN_MODELS.values()) or any(
                apps.get_model(label)._base_manager.filter(organization_id__in=org_ids).exists() for label in adapter.d3.D4_LABELS):
            raise d2.D2Error('Unconfirmed partial D3/D4 dataset.')
        return dict(zip(('D2', 'D3', 'D4'), states))


@contextmanager
def _connection_scope(plan, binding, authority, grant_file, proof):
    old = connections['default']
    old.close()
    config = ConnectionHandler({'default': {'ENGINE': 'django.db.backends.sqlite3',
        'NAME': str(binding.copy), 'OPTIONS': {}}}).settings['default']
    wrapper = DatabaseWrapper(config, alias='default')
    connections['default'] = wrapper  # Process/thread-local; global settings never change.
    try:
        session = _Session(plan, binding, authority, grant_file, proof, wrapper)
        token = session.token
        from .rehearsal_scope import execution_scope
        with execution_scope(session):
            binding.revalidate(fresh=token['payload']['mode'] == 'execute')
            wrapper.ensure_connection()
            session.validate()
            db = wrapper.connection
            db.execute('PRAGMA busy_timeout=0')
            if db.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone()[0] != 'exclusive':
                raise d2.D2Error('Exclusive SQLite locking unavailable.')
            db.execute('BEGIN EXCLUSIVE')
            db.execute('COMMIT')
            if token['payload']['mode'] == 'execute' and backup.digest(binding.copy) != binding.copy_hash:
                raise d2.D2Error('Rehearsal changed between verification and connection.')
            yield session
    finally:
        wrapper.close()
        connections['default'] = old


def run_command(plan, *, execute=False, authorization_file=None, resume=False, reference=None):
    if plan != locations_for_command(plan.run_id, execute=execute):
        raise d2.D2Error('Caller supplied unauthorized locations.')
    connections['default'].close()  # No own stale handle may bypass writer exclusion.
    if not execute:
        if authorization_file or resume:
            raise d2.D2Error('Dry-run cannot execute or consume a new authorization.')
        with backup.frozen_source(plan.original), backup.frozen_source(plan.copy):
            if reference:
                authority = _Authority(plan)
                binding = _binding(plan, authority, reference)
                backup.check_migrations(plan.copy)
                return {'mode': 'dry-run', 'phases': _phase_status(plan, binding, authority)}
            binding = _binding(plan)
            binding.revalidate()
            backup.check_migrations(plan.copy)
            return {'mode': 'dry-run', 'preflight': backup.preflight(plan.copy)}
    if not authorization_file or bool(reference) != bool(resume):
        raise d2.D2Error('Execution needs an explicit grant; resume additionally needs consumed provenance.')
    grant_file = safe_file(authorization_file)
    with run_lock(plan.receipt_file), backup.frozen_source(plan.original), adapter.pinned_copy(plan):
        plan.verify()
        authority = _Authority(plan)
        binding = _binding(plan, authority, reference)
        mode = 'resume' if resume else 'execute'
        authority.verify(grant_file, live=True, mode=mode)
        # Stop on WAL/journal or active writers before consuming/opening for write.
        with backup.frozen_source(plan.copy):
            binding.revalidate(fresh=not resume)
            backup.check_migrations(plan.copy)
            if not resume:
                backup.preflight(plan.copy)
            _phase_status(plan, binding, authority)
        proof = authority.consume(grant_file, binding, mode=mode)
        _prepare_deliveries(plan)
        with _connection_scope(plan, binding, authority, grant_file, proof) as session:
            deliveries = tuple(_Delivery(session, path) for path in plan.deliveries)
            return adapter._certified_phases(binding, deliveries, signing_key=authority.keys['dataset-signing'])
