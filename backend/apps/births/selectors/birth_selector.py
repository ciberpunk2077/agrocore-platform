from apps.births.models import Birth


class BirthSelector:

    @staticmethod
    def list(context):

        return (
            Birth.objects
            .select_related(
                "mother",
                "calf",
                "pregnancy",
                "calf_gender",
            )
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .order_by(
                "-birth_date",
            )
        )


    @staticmethod
    def history(context, animal_id):

        return (
            Birth.objects
            .select_related(
                "mother",
                "calf",
                "pregnancy",
                "calf_gender",
            )
            .filter(
                organization=context.organization,
                mother_id=animal_id,
                is_active=True,
            )
            .order_by("-birth_date")
        )
    @staticmethod
    def get_by_id(context, birth_id):

        return (
            Birth.objects
            .select_related(
                "mother",
                "calf",
                "pregnancy",
                "calf_gender",
            )
            .filter(
                id=birth_id,
                organization=context.organization,
                is_active=True,
            )
            .first()
        )
