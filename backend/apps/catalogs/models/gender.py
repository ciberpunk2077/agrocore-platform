from django.db import models

from apps.common.models import AuditModel


class Gender(AuditModel):
    """
    Género/Sexo biológico del animal.
    """

    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="Código",
    )

    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Nombre",
    )

    class Meta:
        db_table = "catalog_genders"

        verbose_name = "Género"

        verbose_name_plural = "Géneros"

        ordering = ["name"]

        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name
    