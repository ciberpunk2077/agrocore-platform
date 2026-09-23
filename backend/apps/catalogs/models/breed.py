from django.db import models

from apps.common.models import AuditModel
from apps.catalogs.models.species import Species


class Breed(AuditModel):
    """
    Raza de una especie animal.
    """

    species = models.ForeignKey(
        Species,
        on_delete=models.CASCADE,
        related_name="breeds",
        verbose_name="Especie",
    )

    code = models.CharField(
        max_length=20,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=100,
        verbose_name="Nombre",
    )

    class Meta:
        db_table = "catalog_breeds"

        verbose_name = "Raza"
        verbose_name_plural = "Razas"

        ordering = ["species", "name"]

        constraints = [
            models.UniqueConstraint(
                fields=["species", "code"],
                name="unique_breed_code_per_species",
            ),
            models.UniqueConstraint(
                fields=["species", "name"],
                name="unique_breed_name_per_species",
            ),
        ]

        indexes = [
            models.Index(fields=["species"]),
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.species.name} - {self.name}"