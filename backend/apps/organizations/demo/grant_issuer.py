"""Explicit operational issuer; no database writer or automatic seeder hook."""
import hashlib
import hmac
import os
import time
from uuid import uuid4

from django.db import connections

from . import backup, rehearsal_adapter as adapter, rehearsal_command as runtime
from .preflight import canonical_json, run_lock, safe_file
from .windows_acl import current_sid, verify_private


def issue(run_id, *, confirmation, lifetime=120, reference=None):
    if confirmation != run_id or type(lifetime) is not int or not 1 <= lifetime <= 120:
        raise ValueError('Explicit matching confirmation and a short lifetime are required.')
    plan = runtime.locations_for_command(run_id, execute=True)
    connections['default'].close()
    with run_lock(plan.receipt_file), backup.frozen_source(plan.original), backup.frozen_source(plan.copy):
        plan.verify()
        authority = runtime._Authority(plan)
        binding = runtime._binding(plan, authority, reference)
        binding.revalidate(fresh=reference is None)
        backup.check_migrations(plan.copy)
        if reference is None:
            backup.preflight(plan.copy)
        runtime._phase_status(plan, binding, authority)
        # No concurrent outstanding grants, incomplete staging or unknown ledger evidence.
        grants = list(plan.grants.iterdir())
        ledger = list(plan.ledger.iterdir())
        if reference is None and (grants or ledger):
            raise ValueError('Initial issuance requires an empty authorization history.')
        for path in grants:
            token = authority.verify(path, live=False)
            authority.verify_used(token)
        expected = {authority.used_path(authority.verify(path, live=False)) for path in grants}
        if set(ledger) != expected:
            raise ValueError('Unknown or partial ledger evidence.')
        nonce = str(uuid4())  # OS cryptographic randomness; canonical UUID contract.
        payload = {'version': runtime.VERSION, 'run_id': run_id, 'nonce': nonce,
            'expires': time.time() + lifetime, 'mode': 'resume' if reference else 'execute',
            'sid': current_sid(), 'copy': adapter.identity(plan.copy),
            'original': adapter.identity(plan.original), 'receipt': backup.digest(plan.receipt_file),
            'ledger': authority.ledger_identity, 'artifacts': runtime.artifact_digest(plan)}
        signature = hmac.new(authority.keys['authorization'], canonical_json(payload).encode(), hashlib.sha256).hexdigest()
        pending, final = plan.grants / (nonce + '.pending'), plan.grants / (nonce + '.json')
        descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            verify_private(pending)
            stream.write(canonical_json({'payload': payload, 'signature': signature}))
            stream.flush()
            os.fsync(stream.fileno())
        # Every failure preserves evidence; an incomplete pending file blocks further issuance.
        safe_file(pending)
        verify_private(pending)
        authority.verify_files()
        binding.revalidate(fresh=reference is None)
        if not time.time() < payload['expires']:
            raise ValueError('Grant expired before publication.')
        os.rename(pending, final)  # Windows atomic same-directory, refuses overwrite.
        authority.verify(final, live=True, mode=payload['mode'])
        return final  # Private path only. Never return or log the signed token.
