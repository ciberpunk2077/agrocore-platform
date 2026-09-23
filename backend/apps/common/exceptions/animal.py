from .base import BusinessException


class FarmDoesNotBelongToOrganization(BusinessException):
    default_message = (
        "La unidad productiva no pertenece a la organización actual."
    )


class LotDoesNotBelongToFarm(BusinessException):
    default_message = (
        "El lote no pertenece a la unidad productiva seleccionada."
    )


class BreedDoesNotBelongToSpecies(BusinessException):
    default_message = (
        "La raza no pertenece a la especie seleccionada."
    )


class RelatedObjectNotFound(BusinessException):
    default_message = (
        "Uno de los registros relacionados no existe."
    )