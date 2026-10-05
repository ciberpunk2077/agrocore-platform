from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict


class BaseCatalogSchema(Schema):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str


class FarmTypeSchema(BaseCatalogSchema):
    description: str | None = None


class SpeciesSchema(BaseCatalogSchema):
    scientific_name: str | None = None


class BreedSchema(BaseCatalogSchema):
    species_id: UUID


class GenderSchema(BaseCatalogSchema):
    pass


class AnimalStatusSchema(BaseCatalogSchema):
    pass


class MovementTypeSchema(BaseCatalogSchema):
    pass


class BreedingTypeSchema(BaseCatalogSchema):
    pass


class WeighingMethodSchema(BaseCatalogSchema):
    pass


class ProductionTypeSchema(BaseCatalogSchema):
    default_unit: str
    description: str
