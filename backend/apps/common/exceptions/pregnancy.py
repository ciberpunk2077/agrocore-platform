from .base import BusinessException


class PregnancyValidationError(BusinessException):
    default_message = "La gestaciÃ³n no es vÃ¡lida."