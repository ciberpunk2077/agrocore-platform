from django.db import models

from apps.common.models import AuditModel
from apps.organizations.models import Organization

from apps.animals.models import Animal
from apps.breeding.models import BreedingEvent


class PregnancyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Activa"
    FINISHED = "FINISHED", "Finalizada"
    ABORTED = "ABORTED", "Abortada"


class Pregnancy(AuditModel):

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="pregnancies",
    )

    breeding = models.OneToOneField(
        BreedingEvent,
        on_delete=models.PROTECT,
        related_name="pregnancy",
    )

    animal = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="pregnancies",
    )

    diagnosis_date = models.DateField()

    expected_birth = models.DateField()

    confirmed = models.BooleanField(
        default=True,
    )

    status = models.CharField(
        max_length=20,
        choices=PregnancyStatus.choices,
        default=PregnancyStatus.ACTIVE,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:

        db_table = "pregnancies"

        ordering = [
            "-diagnosis_date",
        ]

        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["animal"]),
            models.Index(fields=["confirmed"]),
            models.Index(fields=["status"]),
            models.Index(fields=["expected_birth"]),
        ]

    def __str__(self):

        return (
            f"{self.animal} - "
            f"{self.expected_birth}"
        )