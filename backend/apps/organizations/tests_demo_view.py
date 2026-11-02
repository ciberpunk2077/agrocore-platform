"""D7A identity/configuration rejection on disposable files only."""
from dataclasses import replace
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings
from django.core.management import call_command
from django.core.management.base import CommandError

from . import tests_demo_authorization_storage as fixture
from .demo import backup, demo_view as view
from .management.commands.serve_demo import validate_configuration


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class DemoViewTests(TransactionTestCase):
    def setUp(self):
        fixture.AuthorizationStorageTests.setUp(self)
        def identity(path):
            s=path.stat()
            return (str(path),s.st_dev,s.st_ino)
        self.expected={'source_identity':identity(self.source),'copy_identity':identity(self.path),
                       'source_sha':backup.digest(self.source),'copy_sha':backup.digest(self.path)}

    def test_read_only_valid_files(self):
        before=backup.digest(self.path)
        self.assertEqual(view.validate_files(self.plan,**self.expected),self.plan)
        self.assertEqual(backup.digest(self.path),before)

    def test_original_alias_rejected(self):
        with self.assertRaises(ValueError):
            view.validate_files(replace(self.plan,copy=self.source),**self.expected)

    def test_wrong_path_rejected(self):
        with self.assertRaises(Exception):
            view.validate_files(replace(self.plan,copy=self.root/'missing.sqlite3'),**self.expected)

    def test_replaced_file_rejected(self):
        import os
        moved=self.root/'swapped.sqlite3'
        os.rename(self.path,moved)
        backup.copy_database(moved,self.path)
        self.addCleanup(moved.unlink)
        with self.assertRaises(ValueError):
            view.validate_files(self.plan,**self.expected)

    def test_modified_content_rejected(self):
        with open(self.path,'ab') as stream: stream.write(b'changed')
        with self.assertRaises(ValueError):
            view.validate_files(self.plan,**self.expected)

    def test_normal_settings_cannot_serve_demo(self):
        with self.assertRaises(ValueError): validate_configuration(self.plan)

    def test_unsafe_port_rejected(self):
        for port in (80,8000,65536):
            with self.assertRaises(CommandError): call_command('serve_demo',port=port)

    def test_unsafe_hosts_and_debug_rejected(self):
        for values in ({'DEBUG':True},{'ALLOWED_HOSTS':['*']}):
            config={'SETTINGS_MODULE':'config.settings.demo_view','DEBUG':False,
                    'ALLOWED_HOSTS':['localhost','127.0.0.1']}
            config.update(values)
            with override_settings(**config):
                with self.assertRaises(ValueError): validate_configuration(self.plan)

    def test_exact_read_only_configuration(self):
        from types import SimpleNamespace
        good={'ENGINE':'django.db.backends.sqlite3','NAME':self.path.as_uri()+'?mode=ro','OPTIONS':{'uri':True}}
        with override_settings(SETTINGS_MODULE='config.settings.demo_view',DEBUG=False,
                               ALLOWED_HOSTS=['localhost','127.0.0.1'],DATABASE_ROUTERS=[]):
            with patch('apps.organizations.management.commands.serve_demo.connections',
                       {'default':SimpleNamespace(settings_dict=good)}):
                validate_configuration(self.plan)
            for changes in ({'NAME':str(self.source)},{'OPTIONS':{}},{'ENGINE':'django.db.backends.postgresql'}):
                with patch('apps.organizations.management.commands.serve_demo.connections',
                           {'default':SimpleNamespace(settings_dict={**good,**changes})}):
                    with self.assertRaises(ValueError): validate_configuration(self.plan)
