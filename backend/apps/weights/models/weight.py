from django.db import models

from apps.common.models import AuditModel
from apps.organizations.models import Organization
from apps.animals.models import Animal
from apps.catalogs.models import WeighingMethod

from django.core.exceptions import ValidationError
from django.utils import timezone

class Weight(AuditModel):
    """
    Registro de pesaje de un animal.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="weights",
        verbose_name="Organización",
    )

    animal = models.ForeignKey(
        Animal,
        on_delete=models.CASCADE,
        related_name="weights",
        verbose_name="Animal",
    )

    weighing_method = models.ForeignKey(
        WeighingMethod,
        on_delete=models.PROTECT,
        related_name="weights",
        verbose_name="Método de pesaje",
    )

    date = models.DateField(
        verbose_name="Fecha",
    )

    weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        verbose_name="Peso (kg)",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Observaciones",
    )

    class Meta:
        db_table = "weights"

        verbose_name = "Pesaje"
        verbose_name_plural = "Pesajes"

        ordering = ["-date"]

        constraints = [
            models.UniqueConstraint(
                fields=["animal", "date"],
                condition=models.Q(is_active=True),
                name="unique_active_weight_per_animal_date",
                violation_error_code="active_weight_duplicate",
                violation_error_message="Ya existe un pesaje registrado para este animal en esa fecha.",
            ),
        ]

        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["animal"]),
            models.Index(fields=["date"]),
            models.Index(fields=["is_active"]),
        ]

    def clean(self):
        """
        Validaciones de negocio para el pesaje.
        """

        super().clean()

        if self.weight <= 0:
            raise ValidationError({
                "weight": "El peso debe ser mayor que cero."
            })

        if self.date > timezone.localdate():
            raise ValidationError({
                "date": "La fecha del pesaje no puede ser futura."
            })

        if self.animal.organization_id != self.organization_id:
            raise ValidationError({
                "animal": (
                    "El animal no pertenece a la organización seleccionada."
                )
            })

        if self.animal.birth_date is not None and self.date < self.animal.birth_date:
            raise ValidationError({
                "date": "La fecha del pesaje no puede ser anterior al nacimiento del animal."
            })

    def __str__(self):
        return f"{self.animal} - {self.weight} kg"
