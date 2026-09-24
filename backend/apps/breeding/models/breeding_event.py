from django.db import models
from django.core.exceptions import ValidationError
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

    def clean(self):
        """
        Valida la coherencia del evento reproductivo.
        """

        super().clean()

        if self.animal_id and self.organization_id:

            if self.animal.organization_id != self.organization_id:
                raise ValidationError({
                    "animal": (
                        "La hembra no pertenece a la organización "
                        "del evento reproductivo."
                    )
                })

            if self.animal.gender.code != "F":
                raise ValidationError({
                    "animal": (
                        "El animal reproductor principal debe ser una hembra."
                    )
                })

        if self.male_id:

            if (
                self.organization_id
                and self.male.organization_id != self.organization_id
            ):
                raise ValidationError({
                    "male": (
                        "El macho no pertenece a la organización "
                        "del evento reproductivo."
                    )
                })

            if self.male.gender.code != "M":
                raise ValidationError({
                    "male": (
                        "El animal seleccionado como macho debe ser un macho."
                    )
                })

            if self.animal_id and self.male_id == self.animal_id:
                raise ValidationError({
                    "male": (
                        "La hembra y el macho no pueden ser el mismo animal."
                    )
                })



    def __str__(self):

        return (
            f"{self.animal} - "
            f"{self.breeding_type.name} - "
            f"{self.date}"
        )