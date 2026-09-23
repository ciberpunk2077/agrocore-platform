from apps.animals.models import Animal


class AnimalSelector:

    @staticmethod
    def list(context):

        return (
            Animal.objects
            .select_related(
                "species",
                "breed",
                "gender",
                "status",
                "farm",
                "lot",
            )
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .order_by("internal_id")
        )

    @staticmethod
    def get_by_id(context, animal_id):

        return (
            Animal.objects
            .select_related(
                "species",
                "breed",
                "gender",
                "status",
                "farm",
                "lot",
            )
            .filter(
                id=animal_id,
                organization=context.organization,
                is_active=True,
            )
            .first()
        )