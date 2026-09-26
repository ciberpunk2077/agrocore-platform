from jwt import PyJWTError
from ninja.errors import AuthorizationError
from ninja.security import HttpBearer

from apps.accounts.services.jwt import get_user_from_token


class JWTBearer(HttpBearer):

    def authenticate(self, request, token):

        try:
            user = get_user_from_token(token)

        except PyJWTError:
            return None

        if not user:
            return None

        if request.user.is_authenticated and request.user.pk != user.pk:
            return None

        return user


class JWTBearerTenant(JWTBearer):
    def authenticate(self, request, token):
        user = super().authenticate(request, token)
        if user is None:
            return None

        context = getattr(request, "context", None)
        context_user = getattr(context, "user", None)
        membership = getattr(context, "membership", None)
        organization = getattr(context, "organization", None)
        request_organization = getattr(request, "organization", None)

        if (
            context is None
            or context_user is None
            or context_user.pk != user.pk
            or membership is None
            or organization is None
            or membership.user_id != user.pk
            or membership.is_active is not True
            or membership.is_default is not True
            or organization.is_active is not True
            or membership.organization_id != organization.pk
            or request_organization is None
            or request_organization.pk != organization.pk
        ):
            raise AuthorizationError()

        return user
