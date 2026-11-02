"""Loopback-only read-only WSGI viewer; independent of runserver."""
from contextlib import ExitStack
import threading
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIRequestHandler

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.wsgi import get_wsgi_application
from django.db import connections, OperationalError

from apps.organizations.demo import backup, rehearsal_command as runtime
from apps.organizations.demo.demo_view import verified_locations


def validate_configuration(plan):
    config = connections['default'].settings_dict
    if (settings.SETTINGS_MODULE != 'config.settings.demo_view' or settings.DEBUG
            or set(settings.ALLOWED_HOSTS) != {'127.0.0.1', 'localhost'}
            or set(settings.DATABASES) != {'default'} or settings.DATABASE_ROUTERS
            or config['ENGINE'] != 'django.db.backends.sqlite3'
            or config['NAME'] != plan.copy.as_uri() + '?mode=ro' or config['OPTIONS'] != {'uri': True}):
        raise ValueError('Unsafe demo server configuration.')


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass  # Never log request URLs, headers or credential payloads.


class Command(BaseCommand):
    help = 'Serve the certified read-only demo on 127.0.0.1; never migrate or seed.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--port', type=int, default=8011)

    def handle(self, *args, **options):
        port = options['port']
        if not 1024 <= port <= 65535 or port == 8000:
            raise CommandError('Use a non-default unprivileged loopback port.')
        stopped = threading.Event()
        try:
            plan = verified_locations()
            validate_configuration(plan)
            with backup.frozen_source(plan.original), backup.frozen_source(plan.copy), ExitStack() as stack:
                verified_locations()
                backup.check_migrations(plan.copy)
                authority = runtime._Authority(plan)
                grants = list(plan.grants.glob('*.json'))
                if len(grants) != 1 or len(list(plan.grants.iterdir())) != 1 or len(list(plan.ledger.iterdir())) != 1:
                    raise ValueError('Unexpected authorization history.')
                binding = runtime._binding(plan, authority, grants[0])
                if runtime._phase_status(plan, binding, authority) != dict.fromkeys(('D2','D3','D4'), 'complete'):
                    raise ValueError('Incomplete demo phases.')
                db = connections['default']
                db.ensure_connection()
                actual = db.connection.execute('PRAGMA database_list').fetchall()
                if len(actual) != 1 or actual[0][:2] != (0, 'main') or Path(actual[0][2]).resolve() != plan.copy:
                    raise ValueError('Unexpected effective SQLite destination.')
                def read_only(execute, sql, params, many, context):
                    if sql.lstrip().split(None, 1)[0].upper() not in {'SELECT', 'BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE'}:
                        stopped.set()
                        raise OperationalError('Demo viewer refuses database writes.')
                    return execute(sql, params, many, context)
                application = get_wsgi_application()
                def guarded(environ, start_response):
                    with db.execute_wrapper(read_only):
                        return application(environ, start_response)
                server = stack.enter_context(make_server('127.0.0.1', port, guarded, handler_class=QuietHandler))
                server.timeout = 0.5
                self.stdout.write(f'DEMO READY http://127.0.0.1:{port}/api/docs — SQLite verified, read-only.')
                while not stopped.is_set():
                    server.handle_request()
                raise ValueError('A database write was attempted; viewer stopped.')
        except KeyboardInterrupt:
            self.stdout.write('Demo viewer stopped.')
        except Exception:
            raise CommandError('Demo viewer refused or stopped; inspect safely. No seed, migration or recovery performed.') from None
        finally:
            connections.close_all()
