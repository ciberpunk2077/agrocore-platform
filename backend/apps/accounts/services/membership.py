from apps.accounts.models import Membership


class MembershipService:

    @staticmethod
    def get_default_membership(user):
        """
        Obtiene la membresía por defecto del usuario.
        """
        return (
            Membership.objects
            .select_related("organization")
            .filter(
                user=user,
                is_default=True,
                is_active=True,
            )
            .first()
        )