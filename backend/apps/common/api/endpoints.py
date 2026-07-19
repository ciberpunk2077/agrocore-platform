from ninja import Router
from ninja.errors import HttpError
from apps.common.tenancy import get_current_organization

router = Router()


@router.get("/tenant")
def current_tenant(request):
    organization = get_current_organization()

    if organization is None:
        return {
            "organization": None,
        }

    return {
        "organization": organization.name,
        "code": organization.code,
    }

@router.get("/context")
def context(request):

    # if request.user is None:
    if not request.user.is_authenticated:
        raise HttpError(
            401,
            "No autenticado."
        )

    organization = None

    if request.organization:
        organization = {
            "id": str(request.organization.id),
            "name": request.organization.name,
            "code": request.organization.code,
        }

    return {
        "user": request.user.email,
        "organization": organization,
    }