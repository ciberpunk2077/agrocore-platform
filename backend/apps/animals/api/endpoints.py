from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.animals.api.schemas import (
    AnimalCreateSchema,
    AnimalResponseSchema,
    AnimalUpdateSchema,
)
from apps.animals.services import AnimalService
from apps.animals.selectors import AnimalSelector

router = Router()


@router.get(
    "/",
    response=list[AnimalResponseSchema],
)
def list_animals(request):

    animals = AnimalSelector.list(
        request.context,
    )

    return [
        AnimalResponseSchema(
            id=animal.id,
            internal_id=animal.internal_id,
            official_tag=animal.official_tag,
            electronic_tag=animal.electronic_tag,
            name=animal.name,
            species=animal.species.name,
            breed=animal.breed.name,
            gender=animal.gender.name,
            status=animal.status.name,
            farm=animal.farm.name if animal.farm else None,
            lot=animal.lot.name if animal.lot else None,
            is_active=animal.is_active,
        )
        for animal in animals
    ]

@router.get(
    "/{animal_id}",
    response=AnimalResponseSchema,
)
def get_animal(request, animal_id: UUID):

    animal = AnimalSelector.get_by_id(
        request.context,
        animal_id,
    )

    if animal is None:
        raise HttpError(404, "Animal no encontrado.")

    return AnimalResponseSchema(
        id=animal.id,
        internal_id=animal.internal_id,
        official_tag=animal.official_tag,
        electronic_tag=animal.electronic_tag,
        name=animal.name,
        species=animal.species.name,
        breed=animal.breed.name,
        gender=animal.gender.name,
        status=animal.status.name,
        farm=animal.farm.name if animal.farm else None,
        lot=animal.lot.name if animal.lot else None,
        is_active=animal.is_active,
    )

@router.post(
    "/",
    response=AnimalResponseSchema,
)
def create_animal(request, payload: AnimalCreateSchema):

    # animal = AnimalService.create(payload)
    animal = AnimalService.create(request.context, payload,)

    return AnimalResponseSchema(
        id=animal.id,
        internal_id=animal.internal_id,
        official_tag=animal.official_tag,
        electronic_tag=animal.electronic_tag,
        name=animal.name,
        species=animal.species.name,
        breed=animal.breed.name,
        gender=animal.gender.name,
        status=animal.status.name,
        farm=animal.farm.name if animal.farm else None,
        lot=animal.lot.name if animal.lot else None,
        is_active=animal.is_active,
    )

@router.put(
    "/{animal_id}",
    response=AnimalResponseSchema,
)
def update_animal(request, animal_id: UUID, payload: AnimalUpdateSchema):

    animal = AnimalSelector.get_by_id(
        request.context,
        animal_id,
    )

    if animal is None:
        raise HttpError(
            404,
            "Animal no encontrado.",
        )

    animal = AnimalService.update(
        animal,
        request.context,
        payload,
    )

    return AnimalResponseSchema(
        id=animal.id,
        internal_id=animal.internal_id,
        official_tag=animal.official_tag,
        electronic_tag=animal.electronic_tag,
        name=animal.name,
        species=animal.species.name,
        breed=animal.breed.name,
        gender=animal.gender.name,
        status=animal.status.name,
        farm=animal.farm.name if animal.farm else None,
        lot=animal.lot.name if animal.lot else None,
        is_active=animal.is_active,
    )


@router.delete(
    "/{animal_id}",
)
def delete_animal(
    request,
    animal_id,
):

    animal = AnimalSelector.get_by_id(
        request.context,
        animal_id,
    )

    if animal is None:
        raise HttpError(
            404,
            "Animal no encontrado.",
        )

    AnimalService.delete(
        animal,
    )

    return {
        "success": True,
    }