from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.pregnancy.api.schemas import (
    PregnancyCreateSchema,
    PregnancyResponseSchema,
)

from apps.pregnancy.services import PregnancyService
from apps.pregnancy.selectors import PregnancySelector

router = Router(tags=["Pregnancy"])


@router.get(
    "/",
    response=list[PregnancyResponseSchema],
    summary="List Pregnancies",
)
def list_pregnancies(request):

    # return PregnancySelector.list()
    return PregnancySelector.list(
        request.context,
    )


@router.get(
    "/{pregnancy_id}",
    response=PregnancyResponseSchema,
    summary="Get Pregnancy",
)
def get_pregnancy(request, pregnancy_id: UUID):

    pregnancy = PregnancySelector.get_by_id(
        request.context,
        pregnancy_id,
    )

    if pregnancy is None:
        raise HttpError(
            404,
            "Gestación no encontrada.",
        )

    return pregnancy


@router.post(
    "/",
    response=PregnancyResponseSchema,
    summary="Create Pregnancy",
)
def create_pregnancy(
    request,
    payload: PregnancyCreateSchema,
):

    return PregnancyService.create(
        request.context,
        payload,
    )


@router.post(
    "/{pregnancy_id}/abort",
    response=PregnancyResponseSchema,
    summary="Abort Pregnancy",
)
def abort_pregnancy(
    request,
    pregnancy_id: UUID,
):

    return PregnancyService.abort(
        request.context,
        pregnancy_id,
    )