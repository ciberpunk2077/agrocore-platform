from apps.vaccinations.models import Vaccination


class VaccinationDashboardService:

    @staticmethod
    def vaccinations_due(context, today):

        return Vaccination.objects.filter(
            organization=context.organization,
            is_active=True,
            next_application_date__isnull=False,
            next_application_date__lte=today,
        ).count()