from .base import BusinessException


class ProductionValidationError(BusinessException):
    default_message = "El registro de producción no es válido."
