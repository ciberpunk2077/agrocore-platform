from .base import BusinessException


class FarmValidationError(BusinessException):
    default_message = "Los datos de la unidad productiva son inválidos."
