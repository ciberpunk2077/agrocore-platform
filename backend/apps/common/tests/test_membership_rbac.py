from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from ninja.errors import AuthorizationError, HttpError

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token, create_refresh_token
from apps.catalogs.models import FarmType
from apps.farms.models import Farm
from apps.farms.services import FarmService
from apps.organizations.models import Organization


class MembershipRBACIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rbac@example.com")
        cls.organization = Organization.objects.create(code="RBAC", name="RBAC")
        cls.membership = Membership.objects.create(
            user=cls.user, organization=cls.organization,
            role=Membership.Role.VIEWER, is_default=True,
        )
        cls.farm_type = FarmType.objects.create(code="RBAC", name="RBAC type")
        cls.farm = Farm.objects.create(
            organization=cls.organization, farm_type=cls.farm_type,
            code="EXISTING", name="Existing farm",
        )

    def setUp(self):
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {create_access_token(self.user)}"}
        self.payload = {
            "code": "NEW", "name": "New farm", "farm_type_id": str(self.farm_type.pk),
        }

    def request(self, method, path, data=None, headers=None):
        return getattr(self.client, method.lower())(
            path, data=data, content_type="application/json",
            **(self.headers if headers is None else headers),
        )

    def test_viewer_can_read_all_tenant_routers(self):
        paths = [
            "animals/", "farms/", "lots/", "weights/", "animal-movements/",
            "vaccinations/", "breeding/", "pregnancies/", "births/",
            "dashboard/summary", f"timeline/animal/{uuid4()}",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", f"/api/{path}").status_code, 200)

    def test_viewer_cannot_create_farm(self):
        with patch("apps.farms.api.endpoints.FarmService.create", wraps=FarmService.create) as service:
            response = self.request("POST", "/api/farms/", self.payload)
            self.assertEqual(response.status_code, 403)
            service.assert_not_called()
        self.assertFalse(Farm.objects.filter(code="NEW").exists())

    def test_viewer_cannot_update_accessible_farm(self):
        with patch("apps.farms.api.endpoints.FarmService.update", wraps=FarmService.update) as service:
            response = self.request("PUT", f"/api/farms/{self.farm.pk}", self.payload)
            self.assertEqual(response.status_code, 403)
            service.assert_not_called()
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.name, "Existing farm")

    def test_viewer_cannot_delete_accessible_farm(self):
        with patch("apps.farms.api.endpoints.FarmService.delete", wraps=FarmService.delete) as service:
            response = self.request("DELETE", f"/api/farms/{self.farm.pk}")
            self.assertEqual(response.status_code, 403)
            service.assert_not_called()
        self.farm.refresh_from_db()
        self.assertTrue(self.farm.is_active)

    def test_viewer_cannot_abort_pregnancy_before_service_runs(self):
        with patch(
            "apps.pregnancy.api.endpoints.PregnancyService.abort",
            side_effect=HttpError(409, "Service reached"),
        ) as service:
            response = self.request("POST", f"/api/pregnancies/{uuid4()}/abort")
            self.assertEqual(response.status_code, 403)
            service.assert_not_called()

    def test_each_writer_role_can_create_update_and_delete(self):
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN,
                     Membership.Role.VETERINARIAN, Membership.Role.OPERATOR):
            with self.subTest(role=role):
                self.membership.role = role
                self.membership.save(update_fields=["role"])
                payload = dict(self.payload, code=role, name=role)
                response = self.request("POST", "/api/farms/", payload)
                self.assertEqual(response.status_code, 200)
                farm = Farm.objects.get(pk=response.json()["id"])
                self.assertEqual(farm.organization_id, self.organization.pk)
                payload["name"] = f"Updated {role}"
                response = self.request("PUT", f"/api/farms/{farm.pk}", payload)
                self.assertEqual(response.status_code, 200)
                farm.refresh_from_db()
                self.assertEqual(farm.name, payload["name"])
                self.assertEqual(self.request("DELETE", f"/api/farms/{farm.pk}").status_code, 200)
                farm.refresh_from_db()
                self.assertFalse(farm.is_active)

    def test_invalid_authentication_stays_401_before_mutation(self):
        for token in (None, "invalid", create_refresh_token(self.user)):
            with self.subTest(token_kind="missing" if token is None else "invalid"):
                headers = {} if token is None else {"HTTP_AUTHORIZATION": f"Bearer {token}"}
                with patch("apps.farms.api.endpoints.FarmService.create") as service:
                    response = self.request("POST", "/api/farms/", self.payload, headers=headers)
                    self.assertEqual(response.status_code, 401)
                    service.assert_not_called()

    def test_non_tenant_routers_remain_accessible_without_membership(self):
        self.membership.is_active = False
        self.membership.save(update_fields=["is_active"])
        for path in ("auth/me", "organizations/", "common/context", "catalogs/species"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", f"/api/{path}").status_code, 200)

    def test_viewer_writes_are_blocked_on_every_mutating_tenant_router(self):
        # Valid schema data reaches the service without RBAC; no domain writes are needed.
        identifier = str(uuid4())
        payload = dict(self.payload, **{
            key: identifier for key in (
                "animal_id", "farm_id", "lot_id", "species_id", "breed_id",
                "gender_id", "status_id", "weighing_method_id", "movement_type_id",
                "breeding_type_id", "breeding_id", "pregnancy_id", "mother_id",
            )
        })
        payload.update(
            internal_id="RBAC", date="2025-01-01", weight="100", dose="1",
            vaccine_name="Vaccine", application_date="2025-01-01",
            diagnosis_date="2025-01-02", expected_birth="2025-10-01",
            birth_date="2025-10-01", birth_weight="30",
        )
        routers = (
            ("animals", "animals", "AnimalService", "AnimalSelector"),
            ("farms", "farms", "FarmService", "FarmSelector"),
            ("lots", "lots", "LotService", "LotSelector"),
            ("weights", "weights", "WeightService", "WeightSelector"),
            ("animal-movements", "animal_movements", "AnimalMovementService", "AnimalMovementSelector"),
            ("vaccinations", "vaccinations", "VaccinationService", "VaccinationSelector"),
            ("breeding", "breeding", "BreedingService", None),
            ("pregnancies", "pregnancy", "PregnancyService", None),
            ("births", "births", "BirthService", None),
        )
        for route, app, service_name, selector_name in routers:
            methods = ("POST", "PUT", "DELETE") if selector_name else ("POST",)
            for method in methods:
                with self.subTest(route=route, method=method):
                    path = f"/api/{route}/" if method == "POST" else f"/api/{route}/{identifier}"
                    # For PUT/DELETE the selector is the first domain call; POST calls the service.
                    target = f"{service_name}.create" if method == "POST" else f"{selector_name}.get_by_id"
                    with patch(
                        f"apps.{app}.api.endpoints.{target}",
                        side_effect=HttpError(409, "Domain reached"),
                    ) as domain:
                        response = self.request(method, path, payload)
                        self.assertEqual(response.status_code, 403)
                        domain.assert_not_called()

    def test_policy_denies_unknown_roles_methods_and_invalid_context(self):
        from apps.common.authorization import MembershipOperationPolicy
        from apps.common.context.context import RequestContext

        context = RequestContext(
            user=self.user, organization=self.organization, membership=self.membership,
        )
        for invalid_context in (None, object(), RequestContext(), RequestContext(membership=self.membership)):
            with self.subTest(context=invalid_context):
                with self.assertRaises(AuthorizationError):
                    MembershipOperationPolicy.authorize(invalid_context, "POST")
        self.membership.role = "UNKNOWN"
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                with self.assertRaises(AuthorizationError):
                    MembershipOperationPolicy.authorize(context, method)
        self.membership.role = Membership.Role.OWNER
        with self.assertRaises(AuthorizationError):
            MembershipOperationPolicy.authorize(context, "TRACE")

    def test_policy_handles_patch_as_write_without_adding_endpoints(self):
        from apps.common.authorization import MembershipOperationPolicy
        from apps.common.context.context import RequestContext

        context = RequestContext(
            user=self.user, organization=self.organization, membership=self.membership,
        )
        with self.assertRaises(AuthorizationError):
            MembershipOperationPolicy.authorize(context, "PATCH")
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN,
                     Membership.Role.VETERINARIAN, Membership.Role.OPERATOR):
            with self.subTest(role=role):
                self.membership.role = role
                MembershipOperationPolicy.authorize(context, "PATCH")
