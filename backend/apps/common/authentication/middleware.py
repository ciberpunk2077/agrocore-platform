
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.models import AnonymousUser
from apps.accounts.services.jwt import get_user_from_token
from apps.common.context.services import ContextService


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware encargado de autenticar usuarios mediante JWT.
    """

    def process_request(self, request):

        # request.user = None

        # request.user = AnonymousUser()
        # No tocar autenticación del Admin Django
        if request.path.startswith("/admin/"):
            return

        # Mantener autenticación por sesión si existe
        if request.user.is_authenticated:
            return

        request.organization = None

        authorization = request.headers.get("Authorization")

        if not authorization:
            return

        if not authorization.startswith("Bearer "):
            return

        token = authorization.replace("Bearer ", "")

        try:
            user = get_user_from_token(token)

            if user:
                request.user = user

                request.organization = ( ContextService.get_current_organization(user))

                # request.context = ContextService.build(user)

        except Exception:
            pass

        
