from uuid import UUID

from apps.breeding.models import BreedingEvent


class BreedingSelector:

    @staticmethod
    def list(context):

        return (
            BreedingEvent.objects
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .select_related(
                "animal",
                "male",
                "breeding_type",
            )
            .order_by("-date")
        )

    @staticmethod
    def get_by_id(context, event_id: UUID):

        try:
            return (
                BreedingEvent.objects
                .select_related(
                    "animal",
                    "male",
                    "breeding_type",
                )
                .get(
                    id=event_id,
                    organization=context.organization,
                    is_active=True,
                )
            )

        except BreedingEvent.DoesNotExist:
            return None