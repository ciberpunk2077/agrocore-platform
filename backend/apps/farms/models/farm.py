from django.db import models

from apps.common.models import AuditModel
from apps.organizations.models import Organization
from apps.catalogs.models import FarmType


# class FarmType(models.TextChoices):
#     RANCH = "RANCH", "Rancho"
#     DAIRY = "DAIRY", "Lechería"
#     FEEDLOT = "FEEDLOT", "Engorda"
#     STABLE = "STABLE", "Establo"
#     FARM = "FARM", "Granja"

class Farm(AuditModel):
    """
    Unidad productiva perteneciente a una organización.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="farms",
        verbose_name="Organización",
    )

    name = models.CharField(
        max_length=200,
        verbose_name="Nombre",
    )

    code = models.CharField(
        max_length=30,
        verbose_name="Código",
    )

    # farm_type = models.CharField(
    #     max_length=20,
    #     choices=FarmType.choices,
    #     default=FarmType.RANCH,
    #     verbose_name="Tipo",
    # )

    farm_type = models.ForeignKey(
        FarmType,
        on_delete=models.PROTECT,
        related_name="farms",
        verbose_name="Tipo de unidad productiva",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Descripción",
    )

    address = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Dirección",
    )

    city = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Ciudad",
    )

    state = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Estado",
    )

    country = models.CharField(
        max_length=120,
        default="México",
        verbose_name="País",
    )

    class Meta:
        db_table = "farms"

        verbose_name = "Unidad Productiva"
        verbose_name_plural = "Unidades Productivas"

        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="unique_farm_code_per_organization",
            )
        ]

        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["name"]),
            models.Index(fields=["farm_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"