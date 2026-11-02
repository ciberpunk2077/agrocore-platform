from uuid import uuid4

from django.test import TestCase

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.common.tenancy.context import get_current_organization
from apps.organizations.models import Organization


class OrganizationAccessIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="organization-owner@example.com")
        cls.other_user = User.objects.create_user(email="other-owner@example.com")
        cls.current = Organization.objects.create(code="CURRENT", name="Zulu current")
        cls.secondary = Organization.objects.create(code="SECONDARY", name="Alpha secondary")
        cls.foreign = Organization.objects.create(code="FOREIGN", name="Foreign organization")
        cls.default_membership = Membership.objects.create(
            user=cls.user, organization=cls.current, is_default=True,
        )
        cls.secondary_membership = Membership.objects.create(
            user=cls.user, organization=cls.secondary, is_default=False,
        )
        Membership.objects.create(
            user=cls.other_user, organization=cls.foreign, is_default=True,
        )
        # Other users' memberships must neither duplicate results nor grant access.
        Membership.objects.create(user=cls.other_user, organization=cls.current)

    def setUp(self):
        self.authorization = f"Bearer {create_access_token(self.user)}"

    def get(self, path):
        response = self.client.get(path, HTTP_AUTHORIZATION=self.authorization)
        self.assertIsNone(get_current_organization())
        return response

    def detail_path(self, organization):
        return f"/api/organizations/{organization.pk}"

    def assert_list(self, organizations):
        response = self.get("/api/organizations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()],
            [str(organization.pk) for organization in organizations],
        )
        return response

    def assert_not_found(self, organization_id):
        response = self.get(f"/api/organizations/{organization_id}")
        self.assertEqual(response.status_code, 404)
        # Ninja preserves the existing generic Http404 response with DEBUG=False.
        self.assertEqual(response.json(), {"detail": "Not Found"})

    def test_list_contains_only_accessible_organizations_in_order_without_duplicates(self):
        self.assert_list([self.secondary, self.current])
        self.authorization = f"Bearer {create_access_token(self.other_user)}"
        self.assert_list([self.foreign, self.current])

    def test_non_default_membership_allows_list_and_detail_without_current_tenant(self):
        self.default_membership.is_default = False
        self.default_membership.save(update_fields=["is_default"])
        response = self.assert_list([self.secondary, self.current])
        self.assertIsNone(response.wsgi_request.context.organization)
        response = self.get(self.detail_path(self.secondary))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.secondary.pk))
        self.assertIsNone(response.wsgi_request.context.organization)

    def test_user_without_memberships_gets_empty_list_and_not_found(self):
        user = User.objects.create_user(email="no-memberships@example.com")
        self.authorization = f"Bearer {create_access_token(user)}"
        self.assert_list([])
        self.assert_not_found(self.current.pk)

    def test_own_organization_detail_is_accessible(self):
        response = self.get(self.detail_path(self.current))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.current.pk))
        self.assertEqual(response.wsgi_request.auth.pk, self.user.pk)

    def test_foreign_and_nonexistent_organizations_have_same_not_found_response(self):
        self.assert_not_found(self.foreign.pk)
        self.assert_not_found(uuid4())

    def test_inactive_membership_revokes_access_with_existing_token(self):
        self.default_membership.is_active = False
        self.default_membership.save(update_fields=["is_active"])
        # The other user's active membership to CURRENT must not authorize this user.
        self.assert_list([self.secondary])
        self.assert_not_found(self.current.pk)

    def test_inactive_organization_revokes_access_with_existing_token(self):
        self.current.is_active = False
        self.current.save(update_fields=["is_active"])
        self.assert_list([self.secondary])
        self.assert_not_found(self.current.pk)

    def test_staff_and_superuser_have_no_implicit_access(self):
        for superuser in (False, True):
            with self.subTest(is_superuser=superuser):
                user = User.objects.create_user(
                    email=f"privileged-{superuser}@example.com",
                    is_staff=True, is_superuser=superuser,
                )
                self.authorization = f"Bearer {create_access_token(user)}"
                self.assert_list([])
                self.assert_not_found(self.current.pk)

    def test_secondary_organization_read_preserves_context_and_defaults(self):
        before = list(Membership.objects.filter(user=self.user).order_by("pk").values())
        for path in ("/api/organizations/", self.detail_path(self.secondary)):
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status_code, 200)
                request = response.wsgi_request
                self.assertEqual(request.context.user.pk, self.user.pk)
                self.assertEqual(request.context.organization.pk, self.current.pk)
                self.assertEqual(request.organization.pk, self.current.pk)
                self.assertEqual(request.context.membership.pk, self.default_membership.pk)
        self.assertEqual(
            list(Membership.objects.filter(user=self.user).order_by("pk").values()), before,
        )
        response = self.get("/api/common/tenant")
        self.assertEqual(response.json(), {
            "organization": self.current.name, "code": self.current.code,
        })

    def test_missing_or_invalid_bearer_is_rejected_even_with_session(self):
        for with_session in (False, True):
            self.client.logout()
            if with_session:
                self.client.force_login(self.user)
            for authorization in (None, "Bearer invalid-token"):
                for path in ("/api/organizations/", self.detail_path(self.current)):
                    with self.subTest(session=with_session, auth=authorization, path=path):
                        headers = {} if authorization is None else {
                            "HTTP_AUTHORIZATION": authorization,
                        }
                        response = self.client.get(path, **headers)
                        self.assertEqual(response.status_code, 401)
                        self.assertIsNone(get_current_organization())

    def test_session_and_matching_bearer_are_allowed(self):
        self.client.force_login(self.user)
        self.assert_list([self.secondary, self.current])
        self.assertEqual(self.get(self.detail_path(self.current)).status_code, 200)

    def test_session_and_conflicting_bearer_are_rejected(self):
        self.client.force_login(self.other_user)
        for path in ("/api/organizations/", self.detail_path(self.current)):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 401)

    def test_invalid_uuid_is_rejected_by_ninja(self):
        self.assertEqual(self.get("/api/organizations/not-a-uuid").status_code, 422)


class OrganizationTimezoneTests(TestCase):
    def test_default_and_valid_service_creation(self):
        from apps.organizations.services import create_organization
        organization = create_organization(code="TZ_DEFAULT", name="Timezone default")
        self.assertEqual(organization.timezone, "America/Mexico_City")
        organization = create_organization(code="TZ_UTC", name="Timezone UTC", timezone="UTC")
        self.assertEqual(organization.timezone, "UTC")

    def test_invalid_service_creation_and_update_do_not_persist(self):
        from django.core.exceptions import ValidationError
        from apps.organizations.services import create_organization, update_organization
        organization = create_organization(code="TZ_UPDATE", name="Timezone update")
        for value in ("", None, " UTC", "UTC ", "UTC-6", "invalid", "x" * 65):
            with self.subTest(value=value):
                before = Organization.objects.count()
                with self.assertRaises(ValidationError):
                    create_organization(code="TZ_BAD", name="Invalid timezone", timezone=value)
                self.assertEqual(Organization.objects.count(), before)
                with self.assertRaises(ValidationError):
                    update_organization(organization, timezone=value, name="Should not change")
                organization.refresh_from_db()
                self.assertEqual(organization.name, "Timezone update")
                self.assertEqual(organization.timezone, "America/Mexico_City")

    def test_admin_exposes_validated_timezone(self):
        from django.contrib import admin
        from django.core.exceptions import ValidationError
        registered = admin.site._registry[Organization]
        fields = [field for _, group in registered.fieldsets for field in group["fields"]]
        self.assertIn("timezone", fields)
        organization = Organization(code="TZ_MODEL", name="Timezone model", timezone="invalid")
        with self.assertRaises(ValidationError) as raised:
            organization.full_clean()
        self.assertIn("timezone", raised.exception.message_dict)
