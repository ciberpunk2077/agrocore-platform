from apps.vaccinations.models import Vaccination


class VaccinationSelector:

    @staticmethod
    def list(context):

        return (
            Vaccination.objects
            .select_related("animal")
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .order_by("-application_date")
        )

    @staticmethod
    def history(context, animal_id):

        return (
            Vaccination.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .order_by("-application_date")
        )

    @staticmethod
    def get_by_id(context, vaccination_id):

        return (
            Vaccination.objects
            .select_related("animal")
            .filter(
                id=vaccination_id,
                organization=context.organization,
                is_active=True,
            )
            .first()
        )
