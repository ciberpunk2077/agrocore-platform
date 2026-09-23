from datetime import date
from decimal import Decimal
from uuid import UUID

from ninja import Schema


class BirthCreateSchema(Schema):

    pregnancy_id: UUID

    mother_id: UUID

    calf_id: UUID | None = None

    calf_gender_id: UUID | None = None

    birth_date: date

    birth_weight: Decimal

    alive: bool = True

    dystocia: bool = False

    notes: str | None = None


class BirthResponseSchema(Schema):

    id: UUID

    pregnancy_id: UUID

    mother_id: UUID

    calf_id: UUID | None

    calf_gender_id: UUID | None

    birth_date: date

    birth_weight: Decimal

    alive: bool

    dystocia: bool

    notes: str | None