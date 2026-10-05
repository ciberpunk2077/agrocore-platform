from datetime import timedelta

from django.db.models import Avg, OuterRef, Subquery
from django.utils import timezone

from apps.animals.models import Animal
from apps.weights.models import Weight
from apps.vaccinations.models import Vaccination
from apps.pregnancy.models import Pregnancy, PregnancyStatus
from apps.births.models import Birth


class DashboardSelector:

    @staticmethod
    def summary(context):

        organization = context.organization
        today = timezone.localdate()
        next_30_days = today + timedelta(days=30)

        total_animals = Animal.objects.filter(
            organization=organization,
            is_active=True,
        ).count()

        active_animals = Animal.objects.filter(
            organization=organization,
            is_active=True,
            status__code="ACTIVE",
        ).count()

        pregnancies = Pregnancy.objects.filter(
            organization=organization,
            is_active=True,
            status=PregnancyStatus.ACTIVE,
            confirmed=True,
        ).count()

        births_this_month = Birth.objects.filter(
            organization=organization,
            is_active=True,
            birth_date__year=today.year,
            birth_date__month=today.month,
        ).count()

        upcoming_births = Pregnancy.objects.filter(
            organization=organization,
            is_active=True,
            status=PregnancyStatus.ACTIVE,
            confirmed=True,
            expected_birth__gte=today,
            expected_birth__lte=next_30_days,
        ).count()

        vaccinations_due = Vaccination.objects.filter(
            organization=organization,
            is_active=True,
            next_application_date__lte=today,
        ).count()

        latest_weight = (
            Weight.objects
            .filter(
                organization=organization,
                animal_id=OuterRef("pk"),
                is_active=True,
            )
            .order_by("-date")
            .values("weight")[:1]
        )

        average_weight = (
            Animal.objects
            .filter(
                organization=organization,
                is_active=True,
            )
            .annotate(latest_weight=Subquery(latest_weight))
            .aggregate(
                average=Avg("latest_weight"),
            )
            ["average"]
        )

        return {
            "total_animals": total_animals,
            "active_animals": active_animals,
            "pregnancies": pregnancies,
            "births_this_month": births_this_month,
            "upcoming_births": upcoming_births,
            "vaccinations_due": vaccinations_due,
            "average_weight": average_weight,
        }

    @staticmethod
    def upcoming_births(context):

        organization = context.organization
        today = timezone.localdate()
        next_30_days = today + timedelta(days=30)

        pregnancies = (
            Pregnancy.objects
            .select_related("animal")
            .filter(
                organization=organization,
                is_active=True,
                status=PregnancyStatus.ACTIVE,
                confirmed=True,
                expected_birth__gte=today,
                expected_birth__lte=next_30_days,
            )
            .order_by("expected_birth")
        )

        return [
            {
                "animal_id": pregnancy.animal_id,
                "animal": str(pregnancy.animal),
                "expected_birth": pregnancy.expected_birth,
            }
            for pregnancy in pregnancies
        ]
