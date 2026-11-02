"""Separate command; normal seed_demo_ranches --write remains blocked."""
from django.core.management.base import BaseCommand, CommandError
from apps.organizations.demo.rehearsal_command import locations_for_command, run_command


class Command(BaseCommand):
    help = 'Audit or execute a grant-authorized D2-D4 rehearsal copy only.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True)
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument('--dry-run', action='store_true', help='Default; no files or credentials created.')
        modes.add_argument('--execute', action='store_true', help='Requires an existing private one-use HMAC grant.')
        parser.add_argument('--authorization-file')
        parser.add_argument('--resume', action='store_true')
        parser.add_argument('--reference-authorization', help='Previously consumed signed grant; provenance only.')

    def handle(self, *args, **options):
        try:
            plan = locations_for_command(options['run_id'], execute=options['execute'])
            result = run_command(plan, execute=options['execute'], authorization_file=options.get('authorization_file'),
                resume=options['resume'], reference=options.get('reference_authorization'))
        except Exception:
            # Never echo tokens, key contents, credentials, raw SQL or third-party exception payloads.
            raise CommandError('Controlled rehearsal refused or stopped. Preserve phase artifacts and investigate; no automatic cleanup or reseed.') from None
        if not options['execute']:
            self.stdout.write('D6C-2A DRY-RUN: validation passed; no records, credentials or authorizations written.')
            for phase, state in result.get('phases', {}).items():
                self.stdout.write(phase + ': ' + state)
        else:
            for phase in ('D2', 'D3', 'D4'):
                self.stdout.write(phase + ': ' + result[phase]['state'])
            self.stdout.write('Controlled rehearsal complete; D2/D3/D4 committed separately.')
