from django.core.exceptions import ObjectDoesNotExist

from apps.common.exceptions import (
    FarmDoesNotBelongToOrganization,
    LotDoesNotBelongToFarm,
    BreedDoesNotBelongToSpecies,
    RelatedObjectNotFound,
)

from apps.common.services import BaseCRUDService

from apps.animals.models import Animal
from apps.farms.models import Farm
from apps.lots.models import Lot

from apps.catalogs.models import (
    Species,
    Breed,
    Gender,
    AnimalStatus,
)



class AnimalService:

    @staticmethod
    def create(context, data):
        """
        Crea un animal.
        """
        try:

            relations = AnimalService._load_relations(context, data)

            AnimalService._validate_relations(
                context,
                relations,
            )

            animal = Animal(
                organization=context.organization,
            )

            AnimalService._assign_fields(
                animal,
                data,
                relations,
            )

            animal.full_clean()
            animal.save()

            return animal

        except ObjectDoesNotExist:
            raise RelatedObjectNotFound(
                "Uno de los registros relacionados no existe."
            )

    @staticmethod
    def update(animal, context, data):
        """
        Actualiza un animal existente.
        """
        try:

            relations = AnimalService._load_relations(context, data)

            AnimalService._validate_relations(
                context,
                relations,
            )

            AnimalService._assign_fields(
                animal,
                data,
                relations,
            )

            animal.full_clean()
            animal.save()

            return animal

        except ObjectDoesNotExist:
            raise RelatedObjectNotFound(
                "Uno de los registros relacionados no existe."
            )

    @staticmethod
    def _load_relations(context, data):
        """
        Obtiene todas las entidades relacionadas activas.
        """
        return {
            "farm": Farm.objects.get(
                id=data.farm_id,
                organization=context.organization,
                is_active=True,
            ),
            "lot": Lot.objects.get(
                id=data.lot_id,
                organization=context.organization,
                is_active=True,
            ),
            "species": Species.objects.get(
                id=data.species_id,
                is_active=True,
            ),
            "breed": Breed.objects.get(
                id=data.breed_id,
                is_active=True,
            ),
            "gender": Gender.objects.get(
                id=data.gender_id,
                is_active=True,
            ),
            "status": AnimalStatus.objects.get(
                id=data.status_id,
                is_active=True,
            ),
        }

    @staticmethod
    def _validate_relations(context, relations):
        """
        Valida las relaciones entre las entidades.
        """

        farm = relations["farm"]
        lot = relations["lot"]
        species = relations["species"]
        breed = relations["breed"]

        if farm.organization_id != context.organization.id:
            raise FarmDoesNotBelongToOrganization()

        if lot.farm_id != farm.id:
            raise LotDoesNotBelongToFarm()
            
        if breed.species_id != species.id:
            raise BreedDoesNotBelongToSpecies()

    @staticmethod
    def _assign_fields(animal, data, relations):
        """
        Asigna todos los campos del animal.
        """

        animal.farm = relations["farm"]
        animal.lot = relations["lot"]

        animal.species = relations["species"]
        animal.breed = relations["breed"]
        animal.gender = relations["gender"]
        animal.status = relations["status"]

        animal.internal_id = data.internal_id
        animal.official_tag = data.official_tag
        animal.electronic_tag = data.electronic_tag
        animal.name = data.name

        animal.birth_date = data.birth_date
        animal.birth_weight = data.birth_weight

        animal.notes = data.notes

        animal.mother_id = data.mother_id
        animal.father_id = data.father_id


    # @staticmethod
    # def delete(animal):

    #     animal.is_active = False

    #     animal.save(
    #         update_fields=[
    #             "is_active",
    #         ]
    #     )

    #     return animal

    @staticmethod
    def delete(animal):

        return BaseCRUDService.soft_delete(
            animal,
        )