from django.test import TestCase

from apps.accounts.models import Membership
from apps.common.tests.test_membership_rbac import MembershipRBACIntegrationTests


class CurrentContextContractTests(TestCase):
    setUpTestData = classmethod(MembershipRBACIntegrationTests.setUpTestData.__func__)
    setUp = MembershipRBACIntegrationTests.setUp
    request = MembershipRBACIntegrationTests.request

    def test_writer_roles_receive_default_tenant_and_policy_capabilities(self):
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN,
                     Membership.Role.VETERINARIAN, Membership.Role.OPERATOR):
            with self.subTest(role=role):
                Membership._base_manager.filter(pk=self.membership.pk).update(role=role)
                response = self.request("GET", "/api/common/context")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data["user"], self.user.email)
                self.assertEqual(data["current_user"], {
                    "id": str(self.user.pk), "email": self.user.email,
                    "first_name": self.user.first_name, "last_name": self.user.last_name,
                })
                self.assertEqual(data["organization"], {
                    "id": str(self.organization.pk), "name": self.organization.name,
                    "code": self.organization.code,
                })
                self.assertEqual(data["membership"], {"id": str(self.membership.pk), "is_default": True})
                self.assertEqual(data["role"], role)
                self.assertTrue(data["can_read"])
                self.assertTrue(data["can_write"])

    def test_viewer_reads_but_cannot_write(self):
        data = self.request("GET", "/api/common/context").json()
        self.assertEqual(data["role"], Membership.Role.VIEWER)
        self.assertTrue(data["can_read"])
        self.assertFalse(data["can_write"])

    def test_unavailable_membership_preserves_identity_only_contract(self):
        for changes in ({"is_active": False}, {"is_default": False}):
            with self.subTest(changes=changes):
                Membership._base_manager.filter(pk=self.membership.pk).update(is_active=True, is_default=True)
                Membership._base_manager.filter(pk=self.membership.pk).update(**changes)
                self.assert_identity_only()
        self.membership.delete()
        self.assert_identity_only()

    def test_inactive_organization_preserves_identity_only_contract(self):
        type(self.organization)._base_manager.filter(pk=self.organization.pk).update(is_active=False)
        self.assert_identity_only()

    def assert_identity_only(self):
        response = self.request("GET", "/api/common/context")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["current_user"]["id"], str(self.user.pk))
        for name in ("organization", "membership", "role"):
            self.assertIsNone(data[name])
        self.assertFalse(data["can_read"])
        self.assertFalse(data["can_write"])

    def test_query_cannot_select_tenant_or_role(self):
        from apps.organizations.models import Organization

        other = Organization.objects.create(code="F1_OTHER", name="Other context")
        Membership.objects.create(user=self.user, organization=other,
                                  role=Membership.Role.OWNER, is_default=False)
        data = self.request("GET", f"/api/common/context?organization_id={other.pk}&role=OWNER&can_write=true").json()
        self.assertEqual(data["organization"]["id"], str(self.organization.pk))
        self.assertEqual(data["membership"]["id"], str(self.membership.pk))
        self.assertEqual(data["role"], Membership.Role.VIEWER)
        self.assertFalse(data["can_write"])

    def test_context_requires_access_authentication(self):
        self.assertEqual(self.request("GET", "/api/common/context", headers={}).status_code, 401)
