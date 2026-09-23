from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.weights.api.schemas import (
    WeightCreateSchema,
    WeightUpdateSchema,
    WeightResponseSchema,
    WeightHistorySchema,
    PerformanceSchema,
)
from apps.weights.selectors.weight_selector import WeightSelector
from apps.weights.services.weight_service import WeightService
from apps.weights.calculators.adg_calculator import ADGCalculator


router = Router(tags=["Weights"])


@router.get(
    "/",
    response=list[WeightResponseSchema],
    summary="List Weights",
)
def list_weights(request):

    return WeightSelector.list(
        request.context,
    )


@router.get(
    "/{weight_id}",
    response=WeightResponseSchema,
    summary="Get Weight",
)
def get_weight(request, weight_id: UUID):

    weight = WeightSelector.get_by_id(
        request.context,
        weight_id,
    )

    if weight is None:
        raise HttpError(
            404,
            "Pesaje no encontrado.",
        )

    return weight


@router.post(
    "/",
    response=WeightResponseSchema,
    summary="Create Weight",
)
def create_weight(
    request,
    payload: WeightCreateSchema,
):

    return WeightService.create(
        request.context,
        payload,
    )


@router.get(
    "/animal/{animal_id}/history",
    response=list[WeightHistorySchema],
    summary="Weight History",
)
def weight_history(request, animal_id: UUID):

    return WeightSelector.history(
        request.context,
        animal_id,
    )


@router.get(
    "/animal/{animal_id}/performance",
    response=PerformanceSchema | None,
    summary="Animal Performance",
)
def animal_performance(request, animal_id: UUID):

    current = WeightSelector.last_weight(
        request.context,
        animal_id,
    )

    if current is None:
        return None

    previous = WeightSelector.previous_weight(
        request.context,
        animal_id,
        current.date,
    )

    return ADGCalculator.calculate(
        previous,
        current,
    )


@router.put(
    "/{weight_id}",
    response=WeightResponseSchema,
    summary="Update Weight",
)
def update_weight(
    request,
    weight_id: UUID,
    payload: WeightUpdateSchema,
):

    weight = WeightSelector.get_by_id(
        request.context,
        weight_id,
    )

    if weight is None:
        raise HttpError(
            404,
            "Pesaje no encontrado.",
        )

    return WeightService.update(
        weight,
        request.context,
        payload,
    )


@router.delete(
    "/{weight_id}",
    summary="Delete Weight",
)
def delete_weight(
    request,
    weight_id: UUID,
):

    weight = WeightSelector.get_by_id(
        request.context,
        weight_id,
    )

    if weight is None:
        raise HttpError(
            404,
            "Pesaje no encontrado.",
        )

    WeightService.delete(
        weight,
    )

    return {
        "success": True,
    }