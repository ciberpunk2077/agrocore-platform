from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema
from pydantic import AwareDatetime, ConfigDict


class ProductionCreateSchema(Schema):
    model_config = ConfigDict(extra="forbid")

    animal_id: UUID
    production_type_id: UUID
    recorded_at: AwareDatetime
    quantity: Decimal
    notes: str | None = None


class ProductionUpdateSchema(Schema):
    model_config = ConfigDict(extra="forbid")

    animal_id: UUID
    production_type_id: UUID
    recorded_at: AwareDatetime
    quantity: Decimal
    notes: str | None = None


class ProductionResponseSchema(Schema):
    id: UUID
    animal_id: UUID
    production_type_id: UUID
    recorded_at: datetime
    quantity: Decimal
    unit: str
    notes: str
    is_active: bool
