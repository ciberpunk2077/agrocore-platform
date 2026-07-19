from django.db import models

from apps.common.models import AuditModel


class FarmType(AuditModel):
    """
    Catálogo de tipos de unidades productivas.
    """


    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
    )


    name = models.CharField(
        max_length=100,
        verbose_name="Nombre",
    )


    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )


    class Meta:

        db_table = "catalog_farm_types"

        verbose_name = "Tipo de unidad productiva"

        verbose_name_plural = "Tipos de unidades productivas"

        ordering = [
            "name"
        ]

        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]


    def __str__(self):
        return self.name