from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.vaccinations.api.schemas import (
    VaccinationCreateSchema,
    VaccinationUpdateSchema,
    VaccinationResponseSchema,
)

from apps.vaccinations.selectors import VaccinationSelector
from apps.vaccinations.services import VaccinationService

router = Router(tags=["Vaccinations"])


@router.get(
    "/",
    response=list[VaccinationResponseSchema],
    summary="List Vaccinations",
)
def list_vaccinations(request):

    return VaccinationSelector.list(request.context)


@router.get(
    "/animal/{animal_id}/history",
    response=list[VaccinationResponseSchema],
    summary="Vaccination History",
)
def vaccination_history(request, animal_id: UUID):

    return VaccinationSelector.history(request.context, animal_id)


@router.get(
    "/{vaccination_id}",
    response=VaccinationResponseSchema,
    summary="Get Vaccination",
)
def get_vaccination(request, vaccination_id: UUID):

    vaccination = VaccinationSelector.get_by_id(
        request.context,
        vaccination_id,
    )

    if vaccination is None:
        raise HttpError(
            404,
            "Vacunación no encontrada.",
        )

    return vaccination


@router.post(
    "/",
    response=VaccinationResponseSchema,
    summary="Create Vaccination",
)
def create_vaccination(
    request,
    payload: VaccinationCreateSchema,
):

    return VaccinationService.create(
        request.context,
        payload,
    )


@router.put(
    "/{vaccination_id}",
    response=VaccinationResponseSchema,
    summary="Update Vaccination",
)
def update_vaccination(
    request,
    vaccination_id: UUID,
    payload: VaccinationUpdateSchema,
):

    vaccination = VaccinationSelector.get_by_id(
        request.context,
        vaccination_id,
    )

    if vaccination is None:
        raise HttpError(
            404,
            "Vacunación no encontrada.",
        )

    return VaccinationService.update(
        vaccination,
        request.context,
        payload,
    )


@router.delete(
    "/{vaccination_id}",
    summary="Delete Vaccination",
)
def delete_vaccination(
    request,
    vaccination_id: UUID,
):

    vaccination = VaccinationSelector.get_by_id(
        request.context,
        vaccination_id,
    )

    if vaccination is None:
        raise HttpError(
            404,
            "Vacunación no encontrada.",
        )

    VaccinationService.delete(
        vaccination,
    )

    return {
        "success": True,
    }
