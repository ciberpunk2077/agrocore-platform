from ninja import Router
from django.http import HttpResponse
from ninja.errors import HttpError
from ninja.errors import AuthorizationError
from apps.accounts.api.schemas import UserSchema
from apps.common.authorization import MembershipOperationPolicy
from apps.common.tenancy import get_current_organization
from apps.common.temporal import get_business_time_snapshot
from .schemas import CurrentContextSchema

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

@router.get("/context", response=CurrentContextSchema)
def context(request, response: HttpResponse):

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

    current = request.context
    response["Cache-Control"] = "no-store"
    membership = current.membership if current else None
    capabilities = {}
    for name, method in (("can_read", "GET"), ("can_write", "POST")):
        try:
            MembershipOperationPolicy.authorize(current, method)
        except AuthorizationError:
            capabilities[name] = False
        else:
            capabilities[name] = True

    return {
        "user": request.user.email,
        "organization": organization,
        "current_user": UserSchema.model_validate(request.auth).model_dump(mode="json"),
        "membership": {"id": str(membership.pk), "is_default": membership.is_default} if membership else None,
        "role": membership.role if membership else None,
        "business_time": get_business_time_snapshot(current) if current and current.organization else None,
        **capabilities,
    }
