from uuid import UUID

from ninja import Schema


class FarmCreateSchema(Schema):

    name: str
    code: str
    farm_type_id: UUID
    description: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    country: str = "México"


class FarmUpdateSchema(Schema):

    name: str
    code: str
    farm_type_id: UUID
    description: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    country: str = "México"


class FarmResponseSchema(Schema):

    id: UUID
    name: str
    code: str

    farm_type_id: UUID
    farm_type: str

    description: str
    address: str
    city: str
    state: str
    country: str

    @staticmethod
    def resolve_farm_type(obj):
        return obj.farm_type.name