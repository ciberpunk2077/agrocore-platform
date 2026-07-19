from django.contrib.auth import authenticate

from apps.accounts.services.jwt import (
    create_access_token,
    create_refresh_token,
)


class AuthenticationService:
    """
    Servicio encargado de la autenticación de usuarios.
    """

    @staticmethod
    def login(email: str, password: str):
        """
        Autentica un usuario mediante email y contraseña.
        """

        return authenticate(
            username=email,
            password=password,
        )
    

    @staticmethod
    def create_tokens(user):
        """
        Genera el Access Token y Refresh Token.
        """

        return {
            "access": create_access_token(user),
            "refresh": create_refresh_token(user),
        }