"""Provision private storage only; no grant issuer and no SQLite writer."""
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.demo.authorization_storage import prepare


class Command(BaseCommand):
    help = 'Prepare private keys and an empty ledger for a fresh D6B rehearsal; does not authorize execution.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--run-id', required=True)

    def handle(self, *args, **options):
        try:
            prepare(options['run_id'])
        except Exception:
            raise CommandError('Authorization storage preparation stopped. Preserve artifacts for private inspection; no automatic cleanup, repair or key regeneration.') from None
        self.stdout.write('Private keys prepared; ledger empty. No grant issued; no seeder execution.')
