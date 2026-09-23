from django.db import models

from apps.common.models import AuditModel


class AnimalStatus(AuditModel):
    """
    Estado actual del animal.
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
        db_table = "catalog_animal_statuses"

        verbose_name = "Estado Animal"
        verbose_name_plural = "Estados de Animales"

        ordering = ["name"]

        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name