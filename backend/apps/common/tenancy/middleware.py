from .context import (
    set_current_organization,
    clear_current_organization,
)


class TenantMiddleware:
    """
    Middleware que establece la organización actual.
    """

    def __init__(self, get_response):
        self.get_response = get_response


    def __call__(self, request):

        # El admin no necesita tenancy
        if request.path.startswith("/admin/"):
            return self.get_response(request)

        try:

            context = getattr(request, "context", None)
            organization = getattr(context, "organization", None)
            request.organization = organization
            set_current_organization(organization)

            response = self.get_response(request)

        finally:
            clear_current_organization()

        return response