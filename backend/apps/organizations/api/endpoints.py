from ninja import Router

from apps.organizations.selectors import get_organization_by_id, list_organizations
from .schemas import OrganizationSchema
from uuid import UUID

from django.http import Http404


router = Router()


@router.get(
    "/",
    response=list[OrganizationSchema],
)
def list_organizations_endpoint(request):

    return list_organizations()


@router.get(
    "/{organization_id}",
    response=OrganizationSchema,
)
def get_organization(
    request,
    organization_id: UUID,
):

    organization = get_organization_by_id(
        organization_id
    )

    if not organization:
        raise Http404(
            "Organización no encontrada"
        )

    return organization