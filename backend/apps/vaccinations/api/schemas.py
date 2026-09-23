from datetime import date
from decimal import Decimal
from uuid import UUID

from ninja import Schema


class VaccinationCreateSchema(Schema):

    animal_id: UUID

    vaccine_name: str

    application_date: date

    next_application_date: date | None = None

    dose: Decimal

    batch: str | None = None

    veterinarian: str | None = None

    notes: str | None = None


class VaccinationUpdateSchema(Schema):

    animal_id: UUID

    vaccine_name: str

    application_date: date

    next_application_date: date | None = None

    dose: Decimal

    batch: str | None = None

    veterinarian: str | None = None

    notes: str | None = None


class VaccinationResponseSchema(Schema):

    id: UUID

    animal_id: UUID

    vaccine_name: str

    application_date: date

    next_application_date: date | None

    dose: Decimal

    batch: str | None

    veterinarian: str | None

    notes: str | None

    is_active: bool