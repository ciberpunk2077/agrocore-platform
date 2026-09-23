from apps.farms.models import Farm


class FarmSelector:

    @staticmethod
    def list(context):

        return (
            Farm.objects
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .select_related(
                "farm_type",
            )
            .order_by("name")
        )

    @staticmethod
    def get_by_id(context, farm_id):

        return (
            Farm.objects
            .filter(
                organization=context.organization,
                id=farm_id,
                is_active=True,
            )
            .select_related(
                "farm_type",
            )
            .first()
        )