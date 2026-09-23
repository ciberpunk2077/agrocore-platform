from datetime import date
from uuid import UUID

from ninja import Schema


class PregnancyCreateSchema(Schema):

    breeding_id: UUID

    animal_id: UUID

    diagnosis_date: date

    expected_birth: date

    confirmed: bool = True

    notes: str | None = None


class PregnancyResponseSchema(Schema):

    id: UUID

    breeding_id: UUID

    animal_id: UUID

    diagnosis_date: date

    expected_birth: date

    confirmed: bool

    notes: str | None

    status: str