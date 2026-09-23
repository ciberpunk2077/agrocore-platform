# from datetime import date
# from uuid import UUID

# from ninja import Schema


# class BreedingCreateSchema(Schema):

#     animal_id: UUID

#     male_id: UUID | None = None

#     breeding_type_id: UUID

#     date: date

#     expected_birth: date | None = None

#     technician: str | None = None

#     notes: str | None = None


# class BreedingResponseSchema(Schema):

#     id: UUID

#     animal_id: UUID

#     male_id: UUID | None

#     breeding_type_id: UUID

#     date: date

#     expected_birth: date | None

#     technician: str | None

#     notes: str | None


from datetime import date
from uuid import UUID

from ninja import Schema


class BreedingCreateSchema(Schema):

    animal_id: UUID

    male_id: UUID | None = None

    breeding_type_id: UUID

    date: date

    expected_birth: date | None = None

    technician: str | None = None

    notes: str | None = None


class BreedingResponseSchema(Schema):

    id: UUID

    animal_id: UUID

    male_id: UUID | None

    breeding_type_id: UUID

    date: date

    expected_birth: date | None

    technician: str | None

    notes: str | None