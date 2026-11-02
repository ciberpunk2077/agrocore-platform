"""D6C-2B.1 exclusive key/ledger provisioning; never issues a grant."""
import os
import secrets

from . import backup, rehearsal_adapter as adapter, rehearsal_command as runtime
from .preflight import run_lock
from .windows_acl import verify_private


def prepare(run_id):
    plan = runtime.locations_for_command(run_id, execute=False)
    with run_lock(str(plan.receipt_file)), backup.frozen_source(plan.original), backup.frozen_source(plan.copy):
        plan.verify()
        # A fresh binding includes receipt, file identities, hashes and protected snapshots.
        adapter.bind_verified_files(plan.original, plan.copy, plan.backup_file, plan.receipt_file)
        preflight = backup.preflight(plan.copy)
        if preflight != {'state': 'fresh', 'issues': []}:
            raise ValueError('Only a fresh verified copy may prepare authorization storage.')
        # Fail closed on partial or previous provisioning. Never repair ACLs or rotate keys.
        destinations = (plan.keys, plan.ledger.parent, plan.deliveries[0].parent)
        if any(path.exists() or path.is_symlink() for path in destinations):
            raise ValueError('Existing run artifacts require independent inspection; no overwrite.')
        for parent in (plan.keys.parent, plan.ledger.parent.parent, plan.deliveries[0].parent.parent):
            backup.private_directory(parent)
        backup.private_directory(plan.keys, exclusive=True)
        backup.private_directory(plan.ledger.parent, exclusive=True)
        backup.private_directory(plan.grants, exclusive=True)
        backup.private_directory(plan.ledger, exclusive=True)
        backup.private_directory(plan.deliveries[0].parent, exclusive=True)
        for folder in plan.deliveries:
            backup.private_directory(folder, exclusive=True)
        values = set()
        for name in ('authorization', 'encryption', 'dataset-signing'):
            value = secrets.token_bytes(32)
            while value in values:
                value = secrets.token_bytes(32)
            values.add(value)
            path = plan.keys / (name + '.key')
            # Parent DACL is private BEFORE key material exists; no temporary plaintext copy.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                verify_private(path)
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            verify_private(path)
        runtime._Authority(plan).verify_files()
        if any(plan.grants.iterdir()) or any(plan.ledger.iterdir()):
            raise ValueError('Provisioning must not create grants or consumption evidence.')
        plan.verify()
        return {'state': 'prepared', 'grant_issued': False, 'seeder_executed': False}
