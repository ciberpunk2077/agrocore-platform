from apps.accounts.models import Membership
from .context import RequestContext

class ContextService:
    """
    Servicio encargado de resolver el contexto del usuario.
    """

    @staticmethod
    def get_current_membership(user):
        if user is None:
            return None

        return (
            Membership.objects
            .select_related("organization")
            .filter(
                user=user,
                is_default=True,
                is_active=True,
                organization__is_active=True,
            )
            .first()
        )

    @staticmethod
    def get_current_organization(user):
        membership = ContextService.get_current_membership(user)

        if membership is None:
            return None

        return membership.organization
    

    @staticmethod
    def build(user):

        membership = ContextService.get_current_membership(user)

        organization = None

        if membership:
            organization = membership.organization

        return RequestContext(
            user=user,
            organization=organization,
            membership=membership,
        )