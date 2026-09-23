from apps.lots.models import Lot


class LotSelector:

    @staticmethod
    def list(context):

        return (
            Lot.objects
            .select_related(
                "organization",
                "farm",
            )
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .order_by("name")
        )

    @staticmethod
    def get_by_id(context, lot_id):

        return (
            Lot.objects
            .select_related(
                "organization",
                "farm",
            )
            .filter(
                id=lot_id,
                organization=context.organization,
                is_active=True,
            )
            .first()
        )