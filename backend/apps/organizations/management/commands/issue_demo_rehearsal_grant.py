from django.core.management.base import BaseCommand, CommandError

from apps.organizations.demo.grant_issuer import issue


class Command(BaseCommand):
    help = 'Explicitly issue one short-lived private rehearsal grant; never executes the seeder.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True)
        parser.add_argument('--confirm-run-id', required=True)
        parser.add_argument('--lifetime', type=int, default=120)
        parser.add_argument('--reference-authorization', help='Consumed grant required for a resume authorization.')

    def handle(self, *args, **options):
        try:
            path = issue(options['run_id'], confirmation=options['confirm_run_id'],
                         lifetime=options['lifetime'], reference=options.get('reference_authorization'))
        except Exception:
            raise CommandError('Grant issuance refused or stopped. Preserve private evidence; no automatic retry, cleanup or execution.') from None
        self.stdout.write('Grant published privately; seeder not executed. Authorization file: ' + str(path))
