from django.http import JsonResponse

from apps.common.exceptions import BusinessException


def business_exception_handler(request, exc: BusinessException):
    """
    Mantiene HTTP 400 para negocio y permite errores de configuración controlados.
    """

    payload = {"detail": exc.message}
    if getattr(exc, "code", None):
        payload["code"] = exc.code
    response = JsonResponse(payload, status=getattr(exc, "status_code", 400))
    response["Cache-Control"] = "no-store"
    return response
