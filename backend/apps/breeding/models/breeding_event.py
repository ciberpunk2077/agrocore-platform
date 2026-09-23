from django.db import models

from apps.common.models import AuditModel

from apps.animals.models import Animal
from apps.catalogs.models import BreedingType


class BreedingEvent(AuditModel):
    """
    Evento reproductivo.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="breeding_events",
        verbose_name="Organización",
    )

    animal = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="breeding_events",
        verbose_name="Hembra",
    )

    male = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="breeding_services",
        null=True,
        blank=True,
        verbose_name="Macho",
    )

    breeding_type = models.ForeignKey(
        BreedingType,
        on_delete=models.PROTECT,
        related_name="breeding_events",
        verbose_name="Tipo de reproducción",
    )

    date = models.DateField(
        verbose_name="Fecha",
    )

    expected_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha estimada de parto",
    )

    technician = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Técnico",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Observaciones",
    )

    class Meta:

        db_table = "breeding_events"

        verbose_name = "Evento Reproductivo"

        verbose_name_plural = "Eventos Reproductivos"

        ordering = [
            "-date",
        ]

        indexes = [
            models.Index(fields=["animal"]),
            models.Index(fields=["date"]),
            models.Index(fields=["organization"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):

        return (
            f"{self.animal} - "
            f"{self.breeding_type.name} - "
            f"{self.date}"
        )