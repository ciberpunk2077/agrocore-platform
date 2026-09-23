# from ninja import Router

# from apps.dashboard.schemas import (
#     DashboardSummarySchema,
#     UpcomingBirthSchema,
# )

# from apps.dashboard.services import (
#     DashboardService,
# )

# from apps.common.context import RequestContext


# router = Router(
#     tags=["Dashboard"],
# )


# @router.get(
#     "/summary",
#     response=DashboardSummarySchema,
# )
# def summary(request):

#     context = RequestContext.from_request(
#         request,
#     )

#     return DashboardService.get_summary(
#         context,
#     )


# @router.get(
#     "/upcoming-births",
#     response=list[UpcomingBirthSchema],
# )
# def upcoming_births(request):

#     context = RequestContext.from_request(
#         request,
#     )

#     return DashboardService.get_upcoming_births(
#         context,
#     )