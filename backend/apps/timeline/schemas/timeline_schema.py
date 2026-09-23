from datetime import date
from uuid import UUID

from ninja import Schema


class TimelineEventSchema(Schema):

    id: UUID

    date: date

    event_type: str

    title: str

    description: str
    