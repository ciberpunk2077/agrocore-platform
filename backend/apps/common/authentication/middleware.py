from django.utils.deprecation import MiddlewareMixin
from apps.accounts.services.jwt import get_user_from_token
from apps.common.context.services import ContextService


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware encargado de autenticar usuarios mediante JWT
    y construir el contexto actual de la petición.
    """

    def process_request(self, request):

        # No tocar autenticación del Admin Django
        if request.path.startswith("/admin/"):
            return

        # Contexto por defecto
        request.context = None
        request.organization = None

        # Mantener autenticación por sesión si existe
        if request.user.is_authenticated:
            request.context = ContextService.build(request.user)
            request.organization = request.context.organization
            return

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

                request.context = ContextService.build(user)
                request.organization = request.context.organization

        except Exception:
            pass