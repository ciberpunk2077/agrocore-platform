from django.utils import timezone

from apps.dashboard.services.animal_dashboard_service import (
    AnimalDashboardService,
)

from apps.dashboard.services.weight_dashboard_service import (
    WeightDashboardService,
)

from apps.dashboard.services.reproduction_dashboard_service import (
    ReproductionDashboardService,
)

from apps.dashboard.services.vaccination_dashboard_service import (
    VaccinationDashboardService,
)


class DashboardService:

    @staticmethod
    def get_summary(context):

        today = timezone.localdate()

        return {
            "total_animals": (
                AnimalDashboardService.total_animals(
                    context,
                )
            ),

            "active_animals": (
                AnimalDashboardService.active_animals(
                    context,
                )
            ),

            "pregnancies": (
                ReproductionDashboardService.active_pregnancies(
                    context,
                )
            ),

            "births_this_month": (
                ReproductionDashboardService.births_this_month(
                    context,
                    today,
                )
            ),

            "upcoming_births": (
                ReproductionDashboardService.upcoming_births(
                    context,
                    today,
                )
            ),

            "vaccinations_due": (
                VaccinationDashboardService.vaccinations_due(
                    context,
                    today,
                )
            ),

            "average_weight": (
                WeightDashboardService.average_weight(
                    context,
                )
            ),
        }


    @staticmethod
    def get_upcoming_births(
        context,
        days=7,
    ):

        today = timezone.localdate()

        return ReproductionDashboardService.upcoming_birth_details(
            context,
            today,
            days,
        )