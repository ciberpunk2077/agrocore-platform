from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict


class FarmTypeSchema(Schema):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None = None