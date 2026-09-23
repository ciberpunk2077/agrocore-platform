from apps.animal_movements.models import AnimalMovement


class AnimalMovementSelector:

    @staticmethod
    def list(context):

        return (
            AnimalMovement.objects
            .select_related(
                "animal",
                "movement_type",
                "origin_farm",
                "origin_lot",
                "destination_farm",
                "destination_lot",
            )
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .order_by("-date")
        )

    @staticmethod
    def get_by_id(context, movement_id):

        return (
            AnimalMovement.objects
            .select_related(
                "animal",
                "movement_type",
                "origin_farm",
                "origin_lot",
                "destination_farm",
                "destination_lot",
            )
            .filter(
                id=movement_id,
                organization=context.organization,
                is_active=True,
            )
            .first()
        )

    @staticmethod
    def history(context, animal_id):

        return (
            AnimalMovement.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .order_by("-date", "-created_at")
        )

    @staticmethod
    def last(context, animal_id):

        return (
            AnimalMovement.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .order_by("-date", "-created_at")
            .first()
        )