from jwt import PyJWTError
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
