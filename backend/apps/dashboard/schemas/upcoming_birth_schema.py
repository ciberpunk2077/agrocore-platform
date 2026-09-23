from datetime import date
from uuid import UUID

from ninja import Schema


class UpcomingBirthSchema(Schema):

    animal_id: UUID
    animal: str
    expected_birth: date