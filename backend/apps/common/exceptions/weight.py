from .base import BusinessException


class WeightValidationError(BusinessException):
    default_message = "El pesaje no es válido."