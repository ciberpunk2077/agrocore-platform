from .base import BusinessException


class BreedingValidationError(BusinessException):
    default_message = "El evento reproductivo no es válido."