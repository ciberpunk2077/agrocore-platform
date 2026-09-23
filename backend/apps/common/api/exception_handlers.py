from django.http import JsonResponse

from apps.common.exceptions import BusinessException


def business_exception_handler(request, exc: BusinessException):
    """
    Convierte una excepción de negocio en una respuesta HTTP 400.
    """

    return JsonResponse(
        {
            "detail": exc.message,
        },
        status=400,
    )