"""HTTP operation authorization for an already authenticated tenant context."""

from ninja.errors import AuthorizationError

from apps.accounts.models import Membership
from apps.common.authentication.ninja_auth import JWTBearerTenant


class MembershipOperationPolicy:
    read_methods = frozenset({"GET", "HEAD", "OPTIONS"})
    write_methods = frozenset({"POST", "PUT", "PATCH", "DELETE"})
    write_roles = frozenset({
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.VETERINARIAN,
        Membership.Role.OPERATOR,
    })
    read_roles = write_roles | {Membership.Role.VIEWER}

    @classmethod
    def authorize(cls, context, method):
        # Authentication validates tenancy first. A missing/unknown role grants nothing.
        membership = getattr(context, "membership", None)
        user = getattr(context, "user", None)
        organization = getattr(context, "organization", None)
        role = getattr(membership, "role", None)
        if (
            getattr(membership, "is_active", None) is not True
            or getattr(user, "is_active", None) is not True
            or getattr(organization, "is_active", None) is not True
            or getattr(membership, "user_id", None) != getattr(user, "pk", None)
            or getattr(membership, "organization_id", None) != getattr(organization, "pk", None)
        ):
            raise AuthorizationError()
        allowed_roles = (
            cls.read_roles if method in cls.read_methods
            else cls.write_roles if method in cls.write_methods
            else frozenset()
        )
        if role not in allowed_roles:
            raise AuthorizationError()


class TenantMembershipAccess(JWTBearerTenant):
    """Ninja adapter: authenticate the tenant, then authorize the HTTP operation."""

    def authenticate(self, request, token):
        user = super().authenticate(request, token)
        if user is None:
            return None
        MembershipOperationPolicy.authorize(
            getattr(request, "context", None), request.method,
        )
        return user
