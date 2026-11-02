"""Read-only original, exclusive external backup and restoration; no seed."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.organizations.demo.backup import ORIGINAL, prepare, storage, private_directory, frozen_source
import shutil
import sqlite3
from apps.organizations.demo.preflight import safe_file


class Command(BaseCommand):
    requires_system_checks = []
    requires_migrations_checks = False
    help = 'Create a verified private backup and rehearsal copy, without seeding.'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True)

    def handle(self, *args, **options):
        try:
            db = settings.DATABASES['default']
            if (settings.SETTINGS_MODULE != 'config.settings.local'
                    or set(settings.DATABASES) != {'default'} or settings.DATABASE_ROUTERS
                    or db['ENGINE'] != 'django.db.backends.sqlite3'
                    or db.get('HOST') or db.get('PORT') or db.get('OPTIONS')
                    or safe_file(db['NAME']) != safe_file(ORIGINAL)):
                raise ValueError('Only the exact original local SQLite configuration is authorized.')
            root = storage()
            with frozen_source(ORIGINAL):
                if shutil.disk_usage(root.parent.parent).free < ORIGINAL.stat().st_size * 4 + 64 * 1024 * 1024:
                    raise ValueError('Insufficient free space before directory creation.')
                # Newly created parent contains no database or credential material.
                private_directory(root.parent)
            receipt = prepare(ORIGINAL, root, options['run_id'])
        except (ValueError, OSError, KeyError, sqlite3.Error) as error:
            raise CommandError(str(error)) from None
        self.stdout.write('D6B verified. No seeder executed. Run-id: ' + receipt['run_id'])
        self.stdout.write('Original SHA256: ' + receipt['source_sha256'])
