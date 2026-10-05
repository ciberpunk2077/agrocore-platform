from .base import BusinessException


class LotValidationError(BusinessException):
    default_message = "Los datos del lote son inválidos."
