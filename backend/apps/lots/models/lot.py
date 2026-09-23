from django.db import models

from apps.common.models import AuditModel
from apps.organizations.models import Organization
from apps.farms.models import Farm


class Lot(AuditModel):
    """
    Representa un lote o corral dentro de una unidad productiva.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="lots",
        verbose_name="Organización",
    )

    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name="lots",
        verbose_name="Unidad productiva",
    )

    code = models.CharField(
        max_length=30,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )

    capacity = models.PositiveIntegerField(
        default=0,
        verbose_name="Capacidad",
    )

    class Meta:
        db_table = "lots"

        verbose_name = "Lote"

        verbose_name_plural = "Lotes"

        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_lot_code_per_organization",
            )
        ]

        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["farm"]),
            models.Index(fields=["code"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"