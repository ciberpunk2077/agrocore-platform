from datetime import date
from decimal import Decimal
from uuid import UUID

from ninja import Schema


class AnimalCreateSchema(Schema):
    # organization_id: UUID
    farm_id: UUID
    lot_id: UUID

    species_id: UUID
    breed_id: UUID
    gender_id: UUID
    status_id: UUID

    internal_id: str

    official_tag: str = ""
    electronic_tag: str = ""
    name: str = ""

    birth_date: date | None = None
    birth_weight: Decimal | None = None

    mother_id: UUID | None = None
    father_id: UUID | None = None

    notes: str | None = None


class AnimalResponseSchema(Schema):
    id: UUID
    internal_id: str | None
    official_tag: str | None
    electronic_tag: str | None
    name: str | None

    species_id: UUID
    species: str
    breed_id: UUID
    breed: str
    gender_id: UUID
    gender: str
    status_id: UUID
    status: str

    farm_id: UUID | None
    farm: str | None
    lot_id: UUID | None
    lot: str | None

    birth_date: date | None
    birth_weight: Decimal | None
    mother_id: UUID | None
    father_id: UUID | None
    notes: str | None
    is_active: bool


class AnimalParentReferenceSchema(Schema):
    id: UUID
    internal_id: str | None
    name: str | None
    is_active: bool
    is_deleted: bool


class AnimalDetailResponseSchema(AnimalResponseSchema):
    mother_reference: AnimalParentReferenceSchema | None
    father_reference: AnimalParentReferenceSchema | None


class AnimalUpdateSchema(Schema):
    farm_id: UUID | None
    lot_id: UUID | None

    species_id: UUID
    breed_id: UUID
    gender_id: UUID
    status_id: UUID

    internal_id: str

    official_tag: str | None = None
    electronic_tag: str | None = None
    name: str | None = None

    birth_date: date | None = None
    birth_weight: Decimal | None = None

    mother_id: UUID | None = None
    father_id: UUID | None = None

    notes: str | None = None

class AnimalParentCandidateSchema(Schema):
    id: UUID
    internal_id: str | None
    name: str | None
    gender_code: str
    is_active: bool
