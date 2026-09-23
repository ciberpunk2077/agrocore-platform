from datetime import timedelta

from apps.births.models import Birth
from apps.pregnancy.models import (
    Pregnancy,
    PregnancyStatus,
)


class ReproductionDashboardService:

    @staticmethod
    def active_pregnancies(context):

        return Pregnancy.objects.filter(
            organization=context.organization,
            status=PregnancyStatus.ACTIVE,
            is_active=True,
        ).count()

    @staticmethod
    def births_this_month(context, today):

        return Birth.objects.filter(
            organization=context.organization,
            birth_date__year=today.year,
            birth_date__month=today.month,
            is_active=True,
        ).count()

    @staticmethod
    def upcoming_birth_details(
        context,
        today,
        days=7,
    ):

        end_date = today + timedelta(
            days=days,
        )

        pregnancies = (
            Pregnancy.objects
            .filter(
                organization=context.organization,
                status=PregnancyStatus.ACTIVE,
                is_active=True,
                expected_birth__gte=today,
                expected_birth__lte=end_date,
            )
            .select_related(
                "animal",
            )
            .order_by(
                "expected_birth",
            )
        )

        return [
            {
                "animal_id": pregnancy.animal_id,
                "animal": str(pregnancy.animal),
                "expected_birth": pregnancy.expected_birth,
            }
            for pregnancy in pregnancies
        ]