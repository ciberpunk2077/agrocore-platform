"""Import-safe, fixed D7A file identity for the read-only demo viewer."""
from . import backup
from .preflight import safe_file
from .rehearsal_locations import persistent_locations

RUN_ID = '93f864fe-0e45-4eaa-9253-79f8f7f88467'
SOURCE_SHA = '7726ad14f1d855cfc0ee9a2a0a8c2039c4cc84b2e885b7f0cbc78317f9d0f2a0'
COPY_SHA = 'aa4a77d2e9cdf8f8e72fafa42efb7ff2bdc2bae79efdd4f916f68872eeaebd2e'


def validate_files(plan, *, source_identity, copy_identity, source_sha, copy_sha):
    plan.verify()
    for path, expected, digest in ((plan.original, source_identity, source_sha),
                                   (plan.copy, copy_identity, copy_sha)):
        path = safe_file(path)
        info = path.stat()
        if (str(path), info.st_dev, info.st_ino) != expected or backup.digest(path) != digest:
            raise ValueError('Demo file identity or content changed.')
    backup.inspect_database(plan.copy)
    return plan


def verified_locations():
    plan = persistent_locations(RUN_ID)
    return validate_files(plan,
        source_identity=(str(backup.ORIGINAL), 911516099, 17169973579469451),
        copy_identity=(str(backup.storage() / 'rehearsals' / RUN_ID / 'database.sqlite3'), 911516099, 86694292826967486),
        source_sha=SOURCE_SHA, copy_sha=COPY_SHA)
