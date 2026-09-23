from datetime import date
from uuid import UUID

from ninja import Schema


class AnimalMovementCreateSchema(Schema):

    animal_id: UUID

    movement_type_id: UUID

    origin_farm_id: UUID | None = None
    origin_lot_id: UUID | None = None

    destination_farm_id: UUID | None = None
    destination_lot_id: UUID | None = None

    date: date

    reason: str | None = None

    notes: str | None = None


class AnimalMovementUpdateSchema(Schema):

    animal_id: UUID

    movement_type_id: UUID

    origin_farm_id: UUID | None = None
    origin_lot_id: UUID | None = None

    destination_farm_id: UUID | None = None
    destination_lot_id: UUID | None = None

    date: date

    reason: str | None = None

    notes: str | None = None


class AnimalMovementResponseSchema(Schema):

    id: UUID

    animal_id: UUID

    movement_type_id: UUID

    origin_status_id: UUID | None

    origin_farm_id: UUID | None

    origin_lot_id: UUID | None

    destination_farm_id: UUID | None

    destination_lot_id: UUID | None

    date: date

    reason: str | None

    notes: str | None