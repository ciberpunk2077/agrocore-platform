from apps.weights.models import Weight


class WeightSelector:

    @staticmethod
    def list(context):

        return (
            Weight.objects
            .select_related(
                "animal",
                "weighing_method",
            )
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .order_by("-date")
        )

    @staticmethod
    def get_by_id(context, weight_id):

        return (
            Weight.objects
            .select_related(
                "animal",
                "weighing_method",
            )
            .filter(
                id=weight_id,
                organization=context.organization,
                is_active=True,
            )
            .first()
        )

    @staticmethod
    def history(context, animal_id):

        return (
            Weight.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .order_by("date")
        )

    @staticmethod
    def last_weight(context, animal_id):

        return (
            Weight.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .order_by("-date")
            .first()
        )

    @staticmethod
    def previous_weight(
        context,
        animal_id,
        current_date,
    ):

        return (
            Weight.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                date__lt=current_date,
                is_active=True,
            )
            .order_by("-date")
            .first()
        )