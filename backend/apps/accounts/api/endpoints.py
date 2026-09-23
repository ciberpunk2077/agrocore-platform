from ninja import Router

from ninja.errors import HttpError

from .schemas import (
    LoginSchema,
    LoginResponseSchema,
    UserSchema,
)

from apps.accounts.services.authentication import AuthenticationService

router = Router()


@router.get("/health", auth=None)
def health(request):
    return {
        "status": "ok",
        "module": "accounts",
    }

@router.post(
    "/login",
    response=LoginResponseSchema,
    auth=None,
)
def login(request, payload: LoginSchema):

    user = AuthenticationService.login(
        payload.email,
        payload.password,
    )

    if user is None:
        raise HttpError(401, "Credenciales inválidas.")
    
    tokens = AuthenticationService.create_tokens(user)

    return {
        "access": tokens["access"],
        "refresh": tokens["refresh"],
        "user": UserSchema.model_validate(user),
    }

@router.get("/me",response=UserSchema,)
def me(request):

    # if request.user is None:
    if not request.user.is_authenticated:
        raise HttpError( 401, "No autenticado.",)

    return request.user