from django.db import models

from apps.common.models import AuditModel

from apps.organizations.models import Organization

from apps.animals.models import Animal
from apps.pregnancy.models import Pregnancy
from apps.catalogs.models.gender import Gender


class Birth(AuditModel):

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="births",
    )

    pregnancy = models.OneToOneField(
        Pregnancy,
        on_delete=models.PROTECT,
        related_name="birth",
    )

    mother = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="births",
    )

    calf_gender = models.ForeignKey(
        Gender,
        on_delete=models.PROTECT,
        related_name="births",
        null=True,
        blank=True,
        verbose_name="Sexo de la cría",
    )

    calf = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="birth_record",
        null=True,
        blank=True,
    )

    birth_date = models.DateField()

    birth_weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    alive = models.BooleanField(
        default=True,
    )

    dystocia = models.BooleanField(
        default=False,
    )

    notes = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:

        db_table = "births"

        ordering = [
            "-birth_date",
        ]

        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["mother"]),
            models.Index(fields=["birth_date"]),
            models.Index(fields=["alive"]),
        ]

    def __str__(self):

        return (
            f"{self.mother} - {self.birth_date}"
        )