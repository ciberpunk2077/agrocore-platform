from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.breeding.api.schemas import (
    BreedingCreateSchema,
    BreedingResponseSchema,
)

from apps.breeding.services import BreedingService
from apps.breeding.selectors import BreedingSelector

router = Router(tags=["Breeding"])


@router.get(
    "/",
    response=list[BreedingResponseSchema],
    summary="List Breeding Events",
)
def list_breeding(request):

    return BreedingSelector.list(
        request.context,
    )


@router.get(
    "/{event_id}",
    response=BreedingResponseSchema,
    summary="Get Breeding Event",
)
def get_breeding(request, event_id: UUID):

    event = BreedingSelector.get_by_id(
        request.context,
        event_id,
    )

    if event is None:
        raise HttpError(
            404,
            "Evento de reproducción no encontrado.",
        )

    return event


@router.post(
    "/",
    response=BreedingResponseSchema,
    summary="Create Breeding Event",
)
def create_breeding(
    request,
    payload: BreedingCreateSchema,
):

    return BreedingService.create(
        request.context,
        payload,
    )