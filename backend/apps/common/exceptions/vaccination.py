from .base import BusinessException


class VaccinationValidationError(BusinessException):
    default_message = "La vacunación no es válida."