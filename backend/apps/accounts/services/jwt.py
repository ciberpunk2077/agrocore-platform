from datetime import datetime, timezone

import jwt
from apps.accounts.models import User

from django.conf import settings


def create_access_token(user):
    """
    Genera un Access Token JWT.
    """

    expires_at = (
        datetime.now(timezone.utc)
        + settings.JWT["ACCESS_TOKEN_LIFETIME"]
    )

    payload = {
        "sub": str(user.id),
        "email": user.email,
        "type": "access",
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.JWT["SECRET_KEY"],
        algorithm=settings.JWT["ALGORITHM"],
    )

def create_refresh_token(user):
    """
    Genera un Refresh Token JWT.
    """

    expires_at = (
        datetime.now(timezone.utc)
        + settings.JWT["REFRESH_TOKEN_LIFETIME"]
    )

    payload = {
        "sub": str(user.id),
        "type": "refresh",
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.JWT["SECRET_KEY"],
        algorithm=settings.JWT["ALGORITHM"],
    )


def decode_token(token: str):
    """
    Decodifica un JWT.
    """

    return jwt.decode(
        token,
        settings.JWT["SECRET_KEY"],
        algorithms=[settings.JWT["ALGORITHM"]],
    )


def get_user_from_token(token: str):
    """
    Obtiene el usuario a partir de un JWT.
    """

    payload = decode_token(token)

    return User.objects.filter(
        id=payload["sub"],
        is_active=True,
    ).first()