from django.db import models

from apps.common.models import AuditModel


class Species(AuditModel):
    """
    Especie animal.
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

    scientific_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Nombre científico",
    )

    class Meta:
        db_table = "catalog_species"

        verbose_name = "Especie"

        verbose_name_plural = "Especies"

        ordering = ["name"]

        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name