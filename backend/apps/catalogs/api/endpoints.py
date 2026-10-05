from uuid import UUID

from ninja import Router

from apps.catalogs.api.schemas import (
    AnimalStatusSchema,
    BreedSchema,
    BreedingTypeSchema,
    FarmTypeSchema,
    GenderSchema,
    MovementTypeSchema,
    ProductionTypeSchema,
    SpeciesSchema,
    WeighingMethodSchema,
)
from apps.catalogs.services import CatalogService


router = Router()


@router.get(
    "/production-types",
    response=list[ProductionTypeSchema],
)
def production_types(request):

    return CatalogService.get_production_types()


@router.get(
    "/farm-types",
    response=list[FarmTypeSchema],
)
def farm_types(request):

    return CatalogService.get_farm_types()


@router.get(
    "/species",
    response=list[SpeciesSchema],
)
def species(request):

    return CatalogService.get_species()


@router.get(
    "/breeds",
    response=list[BreedSchema],
)
def breeds(
    request,
    species_id: UUID | None = None,
):

    return CatalogService.get_breeds(
        species_id=species_id,
    )


@router.get(
    "/genders",
    response=list[GenderSchema],
)
def genders(request):

    return CatalogService.get_genders()


@router.get(
    "/animal-statuses",
    response=list[AnimalStatusSchema],
)
def animal_statuses(request):

    return CatalogService.get_animal_statuses()


@router.get(
    "/movement-types",
    response=list[MovementTypeSchema],
)
def movement_types(request):

    return CatalogService.get_movement_types()


@router.get(
    "/breeding-types",
    response=list[BreedingTypeSchema],
)
def breeding_types(request):

    return CatalogService.get_breeding_types()


@router.get(
    "/weighing-methods",
    response=list[WeighingMethodSchema],
)
def weighing_methods(request):

    return CatalogService.get_weighing_methods()
