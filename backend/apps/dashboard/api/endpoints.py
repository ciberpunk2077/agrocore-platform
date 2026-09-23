
from ninja import Router

from apps.dashboard.schemas import (
    DashboardSummarySchema,
    UpcomingBirthSchema,
)

from apps.dashboard.selectors import DashboardSelector


router = Router(
    tags=["Dashboard"],
)


@router.get(
    "/summary",
    response=DashboardSummarySchema,
)
def summary(request):

    return DashboardSelector.summary(request.context,)


@router.get(
    "/upcoming-births",
    response=list[UpcomingBirthSchema],
)
def upcoming_births(request):

    return DashboardSelector.upcoming_births(request.context,)