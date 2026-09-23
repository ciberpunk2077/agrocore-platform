from django.db import models

from apps.common.models import AuditModel


class MovementType(AuditModel):
    """
    Catálogo de tipos de movimiento de animales.
    """

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

    class Meta:
        db_table = "catalog_movement_types"

        verbose_name = "Tipo de Movimiento"
        verbose_name_plural = "Tipos de Movimiento"

        ordering = ["name"]

        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name