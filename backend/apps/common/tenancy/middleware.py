# from apps.accounts.models import Membership

# from .context import (
#     set_current_organization,
#     clear_current_organization,
# )


# class TenantMiddleware:
#     """
#     Middleware que establece la organización actual.
#     """

#     def __init__(self, get_response):
#         self.get_response = get_response


#     def __call__(self, request):

#         try:

#             if request.user.is_authenticated:

#                 membership = (
#                     Membership.objects
#                     .select_related(
#                         "organization"
#                     )
#                     .filter(
#                         user=request.user,
#                         is_default=True,
#                     )
#                     .first()
#                 )

#                 if membership:
#                     set_current_organization(
#                         membership.organization
#                     )

#             response = self.get_response(request)

#         finally:

#             clear_current_organization()


#         return response

from apps.accounts.models import Membership

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

            if request.user.is_authenticated:

                membership = (
                    Membership.objects
                    .select_related("organization")
                    .filter(
                        user=request.user,
                        is_default=True,
                    )
                    .first()
                )

                if membership:
                    set_current_organization(
                        membership.organization
                    )

            response = self.get_response(request)

        finally:
            clear_current_organization()

        return response