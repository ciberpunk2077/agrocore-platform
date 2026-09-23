from django.db import models

from apps.common.models import AuditModel

from apps.organizations.models import Organization
from apps.animals.models import Animal


class Vaccination(AuditModel):

    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="vaccinations",
    )

    animal = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="vaccinations",
    )

    vaccine_name = models.CharField(
        max_length=150,
    )

    application_date = models.DateField()

    next_application_date = models.DateField(
        null=True,
        blank=True,
    )

    dose = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )

    batch = models.CharField(
        max_length=50,
        blank=True,
    )

    veterinarian = models.CharField(
        max_length=150,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    class Meta:

        db_table = "vaccinations"

        ordering = [
            "-application_date",
        ]

    def __str__(self):
        return f"{self.animal} - {self.vaccine_name}"