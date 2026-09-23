from django.db import models

from apps.common.models import AuditModel


class WeighingMethod(AuditModel):
    """
    Método utilizado para registrar un pesaje.
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
        db_table = "catalog_weighing_methods"

        verbose_name = "Método de Pesaje"
        verbose_name_plural = "Métodos de Pesaje"

        ordering = ["name"]

        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name