from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.farms.api.schemas import (
    FarmCreateSchema,
    FarmResponseSchema,
    FarmUpdateSchema,
)
from apps.farms.selectors import FarmSelector
from apps.farms.services import FarmService


router = Router(tags=["Farms"])


@router.get(
    "/",
    response=list[FarmResponseSchema],
    summary="List Farms",
)
def list_farms(request):

    return FarmSelector.list(
        request.context,
    )


@router.get(
    "/{farm_id}",
    response=FarmResponseSchema,
    summary="Get Farm",
)
def get_farm(request, farm_id: UUID):

    farm = FarmSelector.get_by_id(
        request.context,
        farm_id,
    )

    if farm is None:
        raise HttpError(
            404,
            "Unidad productiva no encontrada.",
        )

    return farm


@router.post(
    "/",
    response=FarmResponseSchema,
    summary="Create Farm",
)
def create_farm(
    request,
    payload: FarmCreateSchema,
):

    return FarmService.create(
        request.context,
        payload,
    )


@router.put(
    "/{farm_id}",
    response=FarmResponseSchema,
    summary="Update Farm",
)
def update_farm(
    request,
    farm_id: UUID,
    payload: FarmUpdateSchema,
):

    farm = FarmSelector.get_by_id(
        request.context,
        farm_id,
    )

    if farm is None:
        raise HttpError(
            404,
            "Unidad productiva no encontrada.",
        )

    return FarmService.update(
        farm,
        request.context,
        payload,
    )


@router.delete(
    "/{farm_id}",
    summary="Delete Farm",
)
def delete_farm(
    request,
    farm_id: UUID,
):

    farm = FarmSelector.get_by_id(
        request.context,
        farm_id,
    )

    if farm is None:
        raise HttpError(
            404,
            "Unidad productiva no encontrada.",
        )

    FarmService.delete(
        farm,
    )

    return {
        "success": True,
    }