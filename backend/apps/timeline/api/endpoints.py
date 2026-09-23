from uuid import UUID

from ninja import Router

from apps.timeline.schemas import TimelineEventSchema
from apps.timeline.selectors import TimelineSelector

router = Router(tags=["Timeline"])


@router.get(
    "/animal/{animal_id}",
    response=list[TimelineEventSchema],
    summary="Animal Timeline",
)
def animal_timeline(request, animal_id: UUID):

    return TimelineSelector.history(
        request.context,
        animal_id,
    )