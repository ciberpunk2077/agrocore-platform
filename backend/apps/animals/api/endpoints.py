from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.animals.api.schemas import (
    AnimalCreateSchema,
    AnimalDetailResponseSchema,
    AnimalParentReferenceSchema,
    AnimalParentCandidateSchema,
    AnimalResponseSchema,
    AnimalUpdateSchema,
)
from apps.animals.models import Animal
from apps.animals.services import AnimalService
from apps.animals.selectors import AnimalSelector

router = Router()


def _animal_response(animal: Animal) -> AnimalResponseSchema:
    return AnimalResponseSchema(
        id=animal.id,
        internal_id=animal.internal_id,
        official_tag=animal.official_tag,
        electronic_tag=animal.electronic_tag,
        name=animal.name,
        species_id=animal.species_id,
        species=animal.species.name,
        breed_id=animal.breed_id,
        breed=animal.breed.name,
        gender_id=animal.gender_id,
        gender=animal.gender.name,
        status_id=animal.status_id,
        status=animal.status.name,
        farm_id=animal.farm_id,
        farm=animal.farm.name if animal.farm else None,
        lot_id=animal.lot_id,
        lot=animal.lot.name if animal.lot else None,
        birth_date=animal.birth_date,
        birth_weight=animal.birth_weight,
        mother_id=animal.mother_id,
        father_id=animal.father_id,
        notes=animal.notes,
        is_active=animal.is_active,
    )


@router.get(
    "/",
    response=list[AnimalResponseSchema],
)
def list_animals(request):

    animals = AnimalSelector.list(
        request.context,
    )

    return [
        _animal_response(animal)
        for animal in animals
    ]

# Two segments cannot match the single-segment animal detail route,
# regardless of registration order.
@router.get("/parents/candidates", response=list[AnimalParentCandidateSchema])
def parent_candidates(request):
    return [
        AnimalParentCandidateSchema(
            id=animal.id, internal_id=animal.internal_id, name=animal.name,
            gender_code=animal.gender.code, is_active=animal.is_active,
        )
        for animal in AnimalSelector.parent_candidates(request.context)
    ]


@router.get(
    "/{animal_id}",
    response=AnimalDetailResponseSchema,
)
def get_animal(request, animal_id: UUID):

    animal = AnimalSelector.get_by_id(
        request.context,
        animal_id,
    )

    if animal is None:
        raise HttpError(404, "Animal no encontrado.")

    def parent_reference(parent):
        if parent is None or parent.organization_id != request.context.organization.pk:
            return None
        return AnimalParentReferenceSchema(
            id=parent.id, internal_id=parent.internal_id, name=parent.name,
            is_active=parent.is_active, is_deleted=parent.deleted_at is not None,
        )

    return AnimalDetailResponseSchema(
        **_animal_response(animal).model_dump(),
        mother_reference=parent_reference(animal.mother),
        father_reference=parent_reference(animal.father),
    )

@router.post(
    "/",
    response=AnimalResponseSchema,
)
def create_animal(request, payload: AnimalCreateSchema):

    # animal = AnimalService.create(payload)
    animal = AnimalService.create(request.context, payload,)

    return _animal_response(animal)

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

    return _animal_response(animal)


@router.delete(
    "/{animal_id}",
)
def delete_animal(
    request,
    animal_id: UUID,
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
