from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.animal_movements.api.schemas import (
    AnimalMovementCreateSchema,
    AnimalMovementResponseSchema,
    AnimalMovementUpdateSchema,
)

from apps.animal_movements.services import AnimalMovementService
from apps.animal_movements.selectors import AnimalMovementSelector

router = Router(tags=["Animal Movements"])


@router.get(
    "/",
    response=list[AnimalMovementResponseSchema],
    summary="List Animal Movements",
)
def list_movements(request):

    return AnimalMovementSelector.list(
        request.context,
    )


@router.get(
    "/animal/{animal_id}/history",
    response=list[AnimalMovementResponseSchema],
    summary="Animal Movement History",
)
def animal_movement_history(
    request,
    animal_id: UUID,
):

    return AnimalMovementSelector.history(
        request.context,
        animal_id,
    )


@router.get(
    "/{movement_id}",
    response=AnimalMovementResponseSchema,
    summary="Get Animal Movement",
)
def get_movement(
    request,
    movement_id: UUID,
):

    movement = AnimalMovementSelector.get_by_id(
        request.context,
        movement_id,
    )

    if movement is None:
        raise HttpError(
            404,
            "Movimiento no encontrado.",
        )

    return movement

@router.post(
    "/",
    response=AnimalMovementResponseSchema,
    summary="Create Animal Movement",
)
def create_movement(
    request,
    payload: AnimalMovementCreateSchema,
):

    return AnimalMovementService.create(
        request.context,
        payload,
    )


@router.put(
    "/{movement_id}",
    response=AnimalMovementResponseSchema,
    summary="Update Animal Movement",
)
def update_movement(
    request,
    movement_id: UUID,
    payload: AnimalMovementUpdateSchema,
):

    movement = AnimalMovementSelector.get_by_id(
        request.context,
        movement_id,
    )

    if movement is None:
        raise HttpError(
            404,
            "Movimiento no encontrado.",
        )

    return AnimalMovementService.update(
        movement,
        request.context,
        payload,
    )


@router.delete(
    "/{movement_id}",
    summary="Delete Animal Movement",
)
def delete_movement(
    request,
    movement_id: UUID,
):

    movement = AnimalMovementSelector.get_by_id(
        request.context,
        movement_id,
    )

    if movement is None:
        raise HttpError(
            404,
            "Movimiento no encontrado.",
        )

    AnimalMovementService.delete(
        movement,
    )

    return {
        "success": True,
    }