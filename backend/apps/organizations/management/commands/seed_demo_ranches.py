"""D1: read-only preflight. There is intentionally no writer implementation."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.demo.preflight import audit, authorize_database, reject_write, run_lock


class Command(BaseCommand):
    help = "Audit demo prerequisites without creating or modifying records (D1)."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Read-only; also the default.')
        parser.add_argument('--write', action='store_true', help='Reserved; always rejected in D1.')
        parser.add_argument('--database', default='default')
        parser.add_argument('--manifest', help='Existing signed receipt; never created by D1.')

    def handle(self, *args, **options):
        try:
            if options['write']:
                reject_write()
            if settings.SETTINGS_MODULE == 'config.settings.demo_rehearsal':
                from apps.organizations.demo.backup import rehearsal_path, preflight, check_migrations, authorize_rehearsal_connection
                import os
                if options['database'] != 'default' or options.get('manifest'):
                    raise ValueError('D6B permits only a fresh default read-only rehearsal.')
                path = rehearsal_path(os.environ.get('AGROCORE_DEMO_REHEARSAL_RUN_ID', ''))
                authorize_rehearsal_connection(settings, path)
                with run_lock(path):
                    check_migrations(path)
                    result = preflight(path)
            else:
                path = authorize_database(settings, options['database'])
                with run_lock(path):
                    result = audit(path, settings, options.get('manifest'))
        except (ValueError, OSError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write('D1 DRY-RUN: no records, credentials or files written.')
        self.stdout.write(f"Dataset: {result['state']}. Target: 5 organizations, 30 users, 12 farms, 39 lots, 325 animals.")
        for issue in result['issues']:
            self.stdout.write(f'BLOCKER: {issue}')
        if result['issues']:
            raise CommandError('Preflight incomplete. No writes performed.')
        self.stdout.write('Preflight passed. D1 write mode remains disabled; D2-D5 are not certified.')
