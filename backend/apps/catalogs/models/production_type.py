from django.db import models

from apps.common.models import AuditModel


class ProductionType(AuditModel):
    """Catálogo global de tipos de producción animal."""

    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nombre",
    )

    default_unit = models.CharField(
        max_length=20,
        verbose_name="Unidad predeterminada",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )

    class Meta:
        db_table = "catalog_production_types"
        verbose_name = "Tipo de Producción"
        verbose_name_plural = "Tipos de Producción"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name
