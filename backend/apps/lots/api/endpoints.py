from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.lots.api.schemas import (
    LotCreateSchema,
    LotResponseSchema,
    LotUpdateSchema,
)
from apps.lots.selectors import LotSelector
from apps.lots.services import LotService


router = Router(tags=["Lots"])


@router.get(
    "/",
    response=list[LotResponseSchema],
    summary="List Lots",
)
def list_lots(request):

    return LotSelector.list(
        request.context,
    )


@router.get(
    "/{lot_id}",
    response=LotResponseSchema,
    summary="Get Lot",
)
def get_lot(request, lot_id: UUID):

    lot = LotSelector.get_by_id(
        request.context,
        lot_id,
    )

    if lot is None:
        raise HttpError(
            404,
            "Lote no encontrado.",
        )

    return lot


@router.post(
    "/",
    response=LotResponseSchema,
    summary="Create Lot",
)
def create_lot(
    request,
    payload: LotCreateSchema,
):

    return LotService.create(
        request.context,
        payload,
    )


@router.put(
    "/{lot_id}",
    response=LotResponseSchema,
    summary="Update Lot",
)
def update_lot(
    request,
    lot_id: UUID,
    payload: LotUpdateSchema,
):

    lot = LotSelector.get_by_id(
        request.context,
        lot_id,
    )

    if lot is None:
        raise HttpError(
            404,
            "Lote no encontrado.",
        )

    return LotService.update(
        lot,
        request.context,
        payload,
    )


@router.delete(
    "/{lot_id}",
    summary="Delete Lot",
)
def delete_lot(
    request,
    lot_id: UUID,
):

    lot = LotSelector.get_by_id(
        request.context,
        lot_id,
    )

    if lot is None:
        raise HttpError(
            404,
            "Lote no encontrado.",
        )

    LotService.delete(
        lot,
    )

    return {
        "success": True,
    }