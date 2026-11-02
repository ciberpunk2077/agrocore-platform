from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class OrganizationTimezoneMigrationTests(TransactionTestCase):
    def test_existing_organizations_receive_default_without_history_rewrite(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        old_target = [("organizations", "0001_initial")]
        executor.migrate(old_target)
        old_apps = executor.loader.project_state(old_target).apps
        old_model = old_apps.get_model("organizations", "Organization")
        active = old_model.objects.create(name="Existing active", code="OLD_ACTIVE", slug="existing-active")
        inactive = old_model.objects.create(name="Existing inactive", code="OLD_INACTIVE", slug="existing-inactive", is_active=False)
        before = {row.pk: (row.created_at, row.updated_at) for row in old_model.objects.all()}
        new_target = [("organizations", "0002_organization_timezone")]
        executor = MigrationExecutor(connection)
        executor.migrate(new_target)
        model = executor.loader.project_state(new_target).apps.get_model("organizations", "Organization")
        for pk in (active.pk, inactive.pk):
            row = model.objects.get(pk=pk)
            self.assertEqual(row.timezone, "America/Mexico_City")
            self.assertEqual((row.created_at, row.updated_at), before[pk])
