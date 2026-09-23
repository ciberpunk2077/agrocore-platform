
from apps.animals.models import Animal
from django.db import models

from datetime import timedelta

from apps.births.models import Birth
from apps.pregnancy.models import (
    Pregnancy,
    PregnancyStatus,
)



class AnimalDashboardService:

    @staticmethod
    def total_animals(context):

        return Animal.objects.filter(
            organization=context.organization,
            is_active=True,
        ).count()

    @staticmethod
    def active_animals(context):

        return Animal.objects.filter(
            organization=context.organization,
            is_active=True,
            status__code="ACTIVE",
        ).count()


    @staticmethod
    def animals_by_status(context):

        queryset = (
            Animal.objects
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .values(
                "status__code",
                "status__name",
            )
            .annotate(
                total=models.Count("id"),
            )
            .order_by("status__name")
        )

        return list(queryset)


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
    def upcoming_births(
        context,
        today,
        days=7,
    ):

        end_date = today + timedelta(
            days=days,
        )

        return Pregnancy.objects.filter(
            organization=context.organization,
            status=PregnancyStatus.ACTIVE,
            is_active=True,
            expected_birth__gte=today,
            expected_birth__lte=end_date,
        ).count()