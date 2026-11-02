"""Import-safe D6C-2A path plan. Resolving paths never creates artifacts."""
from dataclasses import dataclass
import json
from pathlib import Path
from uuid import UUID

from . import backup
from .preflight import safe_file
from .windows_acl import verify_private


@dataclass(frozen=True)
class Locations:
    run_id: str
    original: Path
    copy: Path
    backup_file: Path
    receipt_file: Path
    artifact_root: Path
    testing: bool = False

    @property
    def keys(self):
        return self.artifact_root / 'keys' / self.run_id

    @property
    def ledger(self):
        return self.artifact_root / 'authorizations' / self.run_id / 'ledger'

    @property
    def grants(self):
        return self.ledger.parent / 'grants'

    @property
    def deliveries(self):
        return tuple(self.artifact_root / 'deliveries' / self.run_id / phase for phase in ('D2', 'D3', 'D4'))

    def receipt(self):
        path = safe_file(self.receipt_file)
        verify_private(path)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError('Oversized D6B receipt.')
        value = json.loads(path.read_text(encoding='utf-8'))
        if (value['version'] != 'D6B' or value['run_id'] != self.run_id
                or value['source'] != str(safe_file(self.original))
                or value['protected_uuid'] != backup.PROTECTED):
            raise ValueError('D6B run identity rejected.')
        return value

    def verify(self):
        import os
        original, copy, saved = map(safe_file, (self.original, self.copy, self.backup_file))
        if os.path.samefile(original, copy) or os.path.samefile(saved, copy):
            raise ValueError('Original or backup alias cannot be an execution target.')
        backup.directory(self.artifact_root)
        verify_private(self.artifact_root)
        for path in (copy, saved, self.receipt_file):
            folders = [path.parent]
            if path.is_relative_to(self.artifact_root):
                folder = path.parent
                while folder != self.artifact_root:
                    folder = folder.parent
                    folders.append(folder)
            for folder in folders:
                backup.directory(folder)
                verify_private(folder)
            verify_private(path)
        receipt = self.receipt()
        if (backup.digest(original) != receipt['source_sha256']
                or backup.digest(saved) != receipt['backup_sha256']
                or backup.inspect_database(original) != receipt['snapshot']
                or backup.inspect_database(saved) != receipt['snapshot']):
            raise ValueError('Immutable D6B reference changed.')


def persistent_locations(run_id):
    if str(UUID(run_id)) != run_id:
        raise ValueError('Canonical run UUID required.')
    root = backup.storage()
    plan = Locations(run_id, backup.ORIGINAL, root / 'rehearsals' / run_id / 'database.sqlite3',
        root / 'backups' / run_id / 'database.sqlite3', root / 'rehearsals' / run_id / 'receipt.json', root)
    with backup.frozen_source(plan.original):
        plan.verify()
    return plan
