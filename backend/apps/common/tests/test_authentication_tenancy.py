from unittest.mock import patch
from uuid import uuid4

import jwt
from django.conf import settings
from django.test import TestCase

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token, create_refresh_token, decode_token
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

    def assert_non_access_bearer_rejected(self, token):
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
                        HTTP_AUTHORIZATION=f"Bearer {token}",
                    )

                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json(), {"detail": "Unauthorized"})
                    endpoint_getter.assert_not_called()

                self.assertIsNone(getattr(response.wsgi_request, "auth", None))
                if not with_session:
                    self.assertFalse(response.wsgi_request.user.is_authenticated)
                    self.assertIsNone(response.wsgi_request.context)
                self.assertIsNone(get_current_organization())

    def test_refresh_bearer_is_rejected_with_and_without_session(self):
        self.assert_non_access_bearer_rejected(create_refresh_token(self.user_a))

    def test_bearer_without_type_is_rejected_with_and_without_session(self):
        payload = decode_token(create_access_token(self.user_a))
        del payload["type"]
        token = jwt.encode(
            payload,
            settings.JWT["SECRET_KEY"],
            algorithm=settings.JWT["ALGORITHM"],
        )
        self.assert_non_access_bearer_rejected(token)

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


class TenantContextRegressionTests(TestCase):
    def test_bearer_without_default_active_membership_has_no_tenant(self):
        user = User.objects.create_user(
            email="b4-no-membership@example.com",
            is_active=True,
        )
        token = create_access_token(user)

        response = self.client.get(
            "/api/common/tenant",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        request = response.wsgi_request
        self.assertEqual(request.user.pk, user.pk)
        self.assertEqual(request.auth.pk, user.pk)
        self.assertIsNotNone(request.context)
        self.assertEqual(request.context.user.pk, user.pk)
        self.assertIsNone(request.context.membership)
        self.assertIsNone(request.context.organization)
        self.assertIsNone(request.organization)
        self.assertEqual(response.json(), {"organization": None})
        self.assertIsNone(get_current_organization())

    def test_bearer_with_inactive_organization_has_no_tenant(self):
        user = User.objects.create_user(
            email="b4-inactive-org@example.com",
            is_active=True,
        )
        organization = Organization.objects.create(
            code="TEST_B4_INACTIVE",
            name="Test B4 inactive organization",
        )
        membership = Membership.objects.create(
            user=user,
            organization=organization,
            role=Membership.Role.VIEWER,
            is_default=True,
            is_active=True,
        )
        organization.is_active = False
        organization.save(update_fields=["is_active"])
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)
        self.assertTrue(membership.is_default)
        self.assertFalse(Organization.objects.filter(pk=organization.pk).exists())
        token = create_access_token(user)

        response = self.client.get(
            "/api/common/tenant",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        request = response.wsgi_request
        self.assertEqual(request.user.pk, user.pk)
        self.assertEqual(request.auth.pk, user.pk)
        self.assertIsNotNone(request.context)
        self.assertEqual(request.context.user.pk, user.pk)
        self.assertIsNone(request.context.membership)
        self.assertIsNone(request.context.organization)
        self.assertIsNone(request.organization)
        self.assertEqual(response.json(), {"organization": None})
        self.assertIsNone(get_current_organization())


class TenantAuthorizationIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="b4-tenant@example.com", is_active=True,
        )
        self.authorization = f"Bearer {create_access_token(self.user)}"

    def create_membership(self, *, organization_active=True):
        organization = Organization.objects.create(
            code="TEST_B4", name="Test B4 organization",
        )
        membership = Membership.objects.create(
            user=self.user, organization=organization,
            role=Membership.Role.VIEWER, is_default=True, is_active=True,
        )
        if not organization_active:
            organization.is_active = False
            organization.save(update_fields=["is_active"])
        return membership, organization

    def assert_breeding_rejected(self, expected_status, authorization=None):
        headers = {} if authorization is None else {"HTTP_AUTHORIZATION": authorization}
        with patch("apps.breeding.api.endpoints.BreedingSelector.list") as selector:
            response = self.client.get("/api/breeding/", **headers)
        self.assertEqual(response.status_code, expected_status)
        selector.assert_not_called()
        self.assertIsNone(get_current_organization())
        return response

    def test_breeding_without_valid_membership_is_forbidden(self):
        for state in ("missing", "inactive", "non_default"):
            with self.subTest(state=state):
                if state == "inactive":
                    membership, _ = self.create_membership()
                    membership.is_active = False
                    membership.save(update_fields=["is_active"])
                elif state == "non_default":
                    membership.is_active = True
                    membership.is_default = False
                    membership.save(update_fields=["is_active", "is_default"])
                response = self.assert_breeding_rejected(403, self.authorization)
                self.assertIsNone(response.wsgi_request.context.membership)
                self.assertIsNone(response.wsgi_request.context.organization)
                self.assertIsNone(response.wsgi_request.organization)

    def test_breeding_with_inactive_organization_is_forbidden(self):
        self.create_membership(organization_active=False)
        response = self.assert_breeding_rejected(403, self.authorization)
        self.assertIsNone(response.wsgi_request.context.membership)
        self.assertIsNone(response.wsgi_request.context.organization)
        self.assertIsNone(response.wsgi_request.organization)

    def test_breeding_with_valid_tenant_executes_real_selector(self):
        from apps.breeding.selectors import BreedingSelector

        membership, organization = self.create_membership()
        real_list = BreedingSelector.list

        def select(context):
            self.assertEqual(get_current_organization().pk, organization.pk)
            return real_list(context)

        with patch(
            "apps.breeding.api.endpoints.BreedingSelector.list", side_effect=select,
        ) as selector:
            response = self.client.get(
                "/api/breeding/", HTTP_AUTHORIZATION=self.authorization,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        request = response.wsgi_request
        selector.assert_called_once_with(request.context)
        self.assertEqual(request.user.pk, self.user.pk)
        self.assertEqual(request.auth.pk, self.user.pk)
        self.assertEqual(request.context.user.pk, self.user.pk)
        self.assertEqual(request.context.membership.pk, membership.pk)
        self.assertEqual(request.context.organization.pk, organization.pk)
        self.assertEqual(request.organization.pk, organization.pk)
        self.assertIsNone(get_current_organization())

    def test_breeding_missing_or_invalid_bearer_is_unauthorized(self):
        for authorization in (None, "Bearer invalid-token"):
            with self.subTest(authorization=authorization):
                self.assert_breeding_rejected(401, authorization)

    def test_breeding_conflicting_session_and_bearer_is_unauthorized(self):
        session_user = User.objects.create_user(
            email="b4-session@example.com", is_active=True,
        )
        self.client.force_login(session_user)
        self.assert_breeding_rejected(401, self.authorization)

    def test_identity_routes_allow_user_without_tenant(self):
        for path in ("/api/auth/me", "/api/common/context"):
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_AUTHORIZATION=self.authorization)
                self.assertEqual(response.status_code, 200)
                request = response.wsgi_request
                self.assertEqual(request.user.pk, self.user.pk)
                self.assertEqual(request.auth.pk, self.user.pk)
                self.assertEqual(request.context.user.pk, self.user.pk)
                self.assertIsNone(request.context.membership)
                self.assertIsNone(request.context.organization)
                self.assertIsNone(request.organization)
                if path == "/api/auth/me":
                    self.assertEqual(response.json()["id"], str(self.user.pk))
                    self.assertEqual(response.json()["email"], self.user.email)
                else:
                    self.assertEqual(response.json()["user"], self.user.email)
                    self.assertIsNone(response.json()["organization"])
                    self.assertIsNone(response.json()["membership"])
                    self.assertIsNone(response.json()["role"])
                    self.assertFalse(response.json()["can_read"])
                    self.assertFalse(response.json()["can_write"])
                self.assertIsNone(get_current_organization())

    def test_all_eleven_tenant_mounts_reject_before_domain_logic(self):
        routes = (
            ("animals/", "animals", "AnimalSelector.list"),
            ("farms/", "farms", "FarmSelector.list"),
            ("lots/", "lots", "LotSelector.list"),
            ("weights/", "weights", "WeightSelector.list"),
            ("animal-movements/", "animal_movements", "AnimalMovementSelector.list"),
            ("vaccinations/", "vaccinations", "VaccinationSelector.list"),
            (f"timeline/animal/{uuid4()}", "timeline", "TimelineSelector.history"),
            ("dashboard/summary", "dashboard", "DashboardSelector.summary"),
            ("breeding/", "breeding", "BreedingSelector.list"),
            ("pregnancies/", "pregnancy", "PregnancySelector.list"),
            ("births/", "births", "BirthSelector.list"),
        )
        for route, app, selector_name in routes:
            with self.subTest(route=route):
                with patch(f"apps.{app}.api.endpoints.{selector_name}") as selector:
                    response = self.client.get(
                        f"/api/{route}", HTTP_AUTHORIZATION=self.authorization,
                    )
                self.assertEqual(response.status_code, 403)
                selector.assert_not_called()
                self.assertIsNone(get_current_organization())
