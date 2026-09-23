from datetime import date
from decimal import Decimal
from uuid import UUID

from ninja import Schema


class WeightCreateSchema(Schema):

    animal_id: UUID
    weighing_method_id: UUID

    date: date

    weight: Decimal

    notes: str | None = None


class WeightUpdateSchema(Schema):

    animal_id: UUID

    weighing_method_id: UUID

    date: date

    weight: Decimal

    notes: str | None = None


class WeightResponseSchema(Schema):

    id: UUID

    animal_id: UUID

    weighing_method_id: UUID

    date: date

    weight: Decimal

    notes: str | None


class WeightHistorySchema(Schema):

    id: UUID

    date: date

    weight: Decimal

    weighing_method_id: UUID


class PerformanceSchema(Schema):

    previous_weight: Decimal

    current_weight: Decimal

    gain: Decimal

    days: int

    adg: Decimal