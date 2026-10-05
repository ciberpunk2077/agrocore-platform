import sqlite3

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction

from apps.common.exceptions import (
    BusinessException,
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

    _internal_id_message = "El identificador interno ya está reservado en esta organización."
    _input_error_codes = {
        "internal_id": {"max_length"},
        "official_tag": {"max_length"},
        "electronic_tag": {"max_length"},
        "name": {"max_length"},
        "birth_date": {"invalid", "dependent_birth_date"},
        "birth_weight": {
            "invalid", "invalid_birth_weight", "max_digits",
            "max_decimal_places", "max_whole_digits",
        },
        "farm": {"invalid"},
        "lot": {"invalid"},
        "species": {"invalid"},
        "breed": {"invalid"},
        "gender": {"invalid", "dependent_gender"},
        "status": {"invalid"},
        "mother": {"invalid", "parent_organization", "invalid_mother_gender", "self_reference", "genealogy_cycle"},
        "father": {"invalid", "parent_organization", "invalid_father_gender", "self_reference", "genealogy_cycle"},
    }

    @staticmethod
    def _is_internal_id_validation(field, error):
        params = error.params or {}
        return (
            field == "__all__" and error.code == "unique_together"
            and params.get("model_class") is Animal
            and params.get("unique_check") == ("organization", "internal_id")
        )

    @staticmethod
    def _is_input_validation(error):
        if not getattr(error, "error_dict", None):
            return False
        for field, errors in error.error_dict.items():
            for item in errors:
                if item.code in AnimalService._input_error_codes.get(field, set()):
                    continue
                if AnimalService._is_internal_id_validation(field, item):
                    continue
                # Existing clean() emits these two rules without an error code.
                # Field plus exact message avoids treating arbitrary uncoded
                # ValidationErrors as client input errors.
                if item.code is None and (field, item.message) in {
                    ("birth_date", "La fecha de nacimiento no puede ser futura."),
                    ("breed", "La raza seleccionada no pertenece a la especie."),
                }:
                    continue
                return False
        return True

    @staticmethod
    def _is_internal_id_collision(error):
        cause = error.__cause__
        constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
        if constraint is not None:
            return constraint == "unique_internal_id_per_organization"
        return isinstance(cause, sqlite3.IntegrityError) and str(cause) == (
            "UNIQUE constraint failed: animals.organization_id, animals.internal_id"
        )

    @staticmethod
    def _save(animal):
        try:
            with transaction.atomic():
                animal.save()
        except IntegrityError as error:
            if AnimalService._is_internal_id_collision(error):
                raise BusinessException(AnimalService._internal_id_message) from error
            raise

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
            AnimalService._save(animal)

            return animal

        except ValidationError as error:
            if AnimalService._is_input_validation(error):
                raise BusinessException(" ".join(error.messages)) from error
            raise

        except ObjectDoesNotExist:
            raise RelatedObjectNotFound(
                "Uno de los registros relacionados no existe."
            )

    @staticmethod
    def update(animal, context, data):
        """
        Actualiza un animal existente.
        """
        if animal.organization_id != context.organization.pk:
            raise BusinessException("El animal no pertenece a la organización actual.")
        try:

            relations = AnimalService._load_relations(context, data, animal=animal)

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
            AnimalService._save(animal)

            return animal

        except ValidationError as error:
            if AnimalService._is_input_validation(error):
                raise BusinessException(" ".join(error.messages)) from error
            raise

        except ObjectDoesNotExist:
            raise RelatedObjectNotFound(
                "Uno de los registros relacionados no existe."
            )

    @staticmethod
    def _load_relations(context, data, *, animal=None):
        """
        Obtiene relaciones activas y progenitores elegibles del tenant.
        """
        if animal is not None and ((data.farm_id is None) != (data.lot_id is None)):
            raise BusinessException("Debe indicar finca y lote juntos o dejar ambos sin ubicación.")
        without_location = animal is not None and data.farm_id is None and data.lot_id is None
        return {
            "mother": AnimalService._load_parent(
                context, data.mother_id,
                existing_parent_id=animal.mother_id if animal is not None else None,
            ),
            "father": AnimalService._load_parent(
                context, data.father_id,
                existing_parent_id=animal.father_id if animal is not None else None,
            ),
            "farm": None if without_location else Farm.objects.get(
                id=data.farm_id,
                organization=context.organization,
                is_active=True,
            ),
            "lot": None if without_location else Lot.objects.get(
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
    def _load_parent(context, parent_id, *, existing_parent_id=None):
        if parent_id is None:
            return None
        # Activity does not determine eligibility. Only an unchanged historical
        # relation may resolve a deleted parent. Tenant and full_clean invariants
        # still apply to both historical references and new assignments.
        parents = Animal._base_manager.filter(
            id=parent_id,
            organization=context.organization,
        )
        if parent_id != existing_parent_id:
            parents = parents.filter(deleted_at__isnull=True)
        return parents.get()

    @staticmethod
    def _validate_relations(context, relations):
        """
        Valida las relaciones entre las entidades.
        """

        farm = relations["farm"]
        lot = relations["lot"]
        species = relations["species"]
        breed = relations["breed"]

        if farm is not None and farm.organization_id != context.organization.id:
            raise FarmDoesNotBelongToOrganization()

        if lot is not None and (farm is None or lot.farm_id != farm.id):
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
        animal.official_tag = "" if data.official_tag is None else data.official_tag
        animal.electronic_tag = "" if data.electronic_tag is None else data.electronic_tag
        animal.name = "" if data.name is None else data.name

        animal.birth_date = data.birth_date
        animal.birth_weight = data.birth_weight

        animal.notes = "" if data.notes is None else data.notes

        animal.mother = relations["mother"]
        animal.father = relations["father"]


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
