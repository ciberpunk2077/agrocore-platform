from uuid import UUID

from ninja import Schema


class LotCreateSchema(Schema):

    farm_id: UUID

    code: str

    name: str

    description: str = ""

    capacity: int = 0


class LotUpdateSchema(Schema):

    farm_id: UUID

    code: str

    name: str

    description: str = ""

    capacity: int = 0


class LotResponseSchema(Schema):

    id: UUID

    organization_id: UUID

    farm_id: UUID

    code: str

    name: str

    description: str

    capacity: int