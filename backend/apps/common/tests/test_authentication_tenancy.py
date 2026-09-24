from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.common.tenancy.context import get_current_organization
from apps.organizations.models import Organization


class AuthenticationTenancyIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.organization_a = Organization.objects.create(
            code="TEST_B3_A",
            name="Test B3 Organization A",
        )
        cls.organization_b = Organization.objects.create(
            code="TEST_B3_B",
            name="Test B3 Organization B",
        )
        cls.user_a = User.objects.create_user(
            email="b3-a@example.com",
            first_name="User",
            last_name="A",
            is_active=True,
        )
        cls.user_b = User.objects.create_user(
            email="b3-b@example.com",
            first_name="User",
            last_name="B",
            is_active=True,
        )
        Membership.objects.create(
            user=cls.user_a,
            organization=cls.organization_a,
            role=Membership.Role.VIEWER,
            is_default=True,
            is_active=True,
        )
        Membership.objects.create(
            user=cls.user_b,
            organization=cls.organization_b,
            role=Membership.Role.VIEWER,
            is_default=True,
            is_active=True,
        )

    def assert_identity_and_tenant(self, response, user, organization):
        self.assertEqual(response.status_code, 200)
        request = response.wsgi_request
        self.assertEqual(request.user.pk, user.pk)
        self.assertEqual(request.auth.pk, user.pk)
        self.assertEqual(request.context.user.pk, user.pk)
        self.assertEqual(request.context.organization.pk, organization.pk)
        self.assertEqual(request.organization.pk, organization.pk)
        self.assertEqual(response.json(), {
            "organization": organization.name,
            "code": organization.code,
        })
        self.assertIsNone(get_current_organization())

    def test_bearer_only_uses_token_identity(self):
        token_b = create_access_token(self.user_b)
        response = self.client.get(
            "/api/common/tenant",
            HTTP_AUTHORIZATION=f"Bearer {token_b}",
        )

        self.assert_identity_and_tenant(response, self.user_b, self.organization_b)

    def test_session_only_requires_bearer(self):
        self.client.force_login(self.user_a)

        with patch(
            "apps.common.api.endpoints.get_current_organization",
            wraps=get_current_organization,
        ) as endpoint_getter:
            response = self.client.get("/api/common/tenant")

            self.assertEqual(response.status_code, 401)
            endpoint_getter.assert_not_called()

        self.assertIsNone(get_current_organization())

    def test_session_and_same_bearer_are_allowed(self):
        self.client.force_login(self.user_a)
        token_a = create_access_token(self.user_a)
        response = self.client.get(
            "/api/common/tenant",
            HTTP_AUTHORIZATION=f"Bearer {token_a}",
        )

        self.assert_identity_and_tenant(response, self.user_a, self.organization_a)

    def test_session_and_different_bearer_are_rejected(self):
        self.client.force_login(self.user_a)
        token_b = create_access_token(self.user_b)

        with patch(
            "apps.common.api.endpoints.get_current_organization",
            wraps=get_current_organization,
        ) as endpoint_getter:
            response = self.client.get(
                "/api/common/tenant",
                HTTP_AUTHORIZATION=f"Bearer {token_b}",
            )

            self.assertEqual(response.status_code, 401)
            endpoint_getter.assert_not_called()

        self.assertIsNone(getattr(response.wsgi_request, "auth", None))
        self.assertIsNone(get_current_organization())

    def test_invalid_bearer_is_rejected(self):
        for with_session in (False, True):
            with self.subTest(with_session=with_session):
                self.client.logout()
                if with_session:
                    self.client.force_login(self.user_a)

                with patch(
                    "apps.common.api.endpoints.get_current_organization",
                    wraps=get_current_organization,
                ) as endpoint_getter:
                    response = self.client.get(
                        "/api/common/tenant",
                        HTTP_AUTHORIZATION="Bearer invalid-token",
                    )

                    self.assertEqual(response.status_code, 401)
                    endpoint_getter.assert_not_called()

                self.assertIsNone(get_current_organization())

    def test_public_health_allows_conflicting_credentials(self):
        self.client.force_login(self.user_a)
        token_b = create_access_token(self.user_b)
        response = self.client.get(
            "/api/auth/health",
            HTTP_AUTHORIZATION=f"Bearer {token_b}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "module": "accounts"})
        self.assertIsNone(get_current_organization())

    def test_admin_session_is_unaffected_by_bearer(self):
        self.user_a.is_staff = True
        self.user_a.save(update_fields=["is_staff"])
        self.client.force_login(self.user_a)
        token_b = create_access_token(self.user_b)
        response = self.client.get(
            "/admin/",
            HTTP_AUTHORIZATION=f"Bearer {token_b}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.user.pk, self.user_a.pk)
        self.assertFalse(response.wsgi_request.user.is_superuser)
        self.assertIsNone(get_current_organization())
