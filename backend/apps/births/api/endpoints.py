from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.births.api.schemas import (
    BirthCreateSchema,
    BirthResponseSchema,
)

from apps.births.selectors import BirthSelector
from apps.births.services import BirthService

router = Router(tags=["Births"])


@router.get(
    "/",
    response=list[BirthResponseSchema],
    summary="List Births",
)
def list_births(request):

    return BirthSelector.list(
        request.context,
    )


@router.get(
    "/{birth_id}",
    response=BirthResponseSchema,
    summary="Get Birth",
)
def get_birth(request, birth_id: UUID):

    birth = BirthSelector.get_by_id(
        request.context,
        birth_id,
    )

    if birth is None:
        raise HttpError(
            404,
            "Parto no encontrado.",
        )

    return birth


@router.post(
    "/",
    response=BirthResponseSchema,
    summary="Create Birth",
)
def create_birth(
    request,
    payload: BirthCreateSchema,
):

    return BirthService.create(
        request.context,
        payload,
    )