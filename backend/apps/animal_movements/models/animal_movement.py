from django.db import models

from apps.common.models import AuditModel
from apps.organizations.models import Organization
from apps.animals.models import Animal
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.catalogs.models import MovementType, AnimalStatus


class AnimalMovement(AuditModel):
    """
    Registro de movimientos de animales.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="animal_movements",
        verbose_name="Organización",
    )

    animal = models.ForeignKey(
        Animal,
        on_delete=models.CASCADE,
        related_name="movements",
        verbose_name="Animal",
    )

    movement_type = models.ForeignKey(
        MovementType,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name="Tipo de movimiento",
    )

    origin_status = models.ForeignKey(
        AnimalStatus,
        on_delete=models.PROTECT,
        related_name="origin_status_movements",
        null=True,
        blank=True,
        verbose_name="Estado anterior",
    )

    origin_farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="origin_movements",
        null=True,
        blank=True,
        verbose_name="Unidad productiva origen",
    )

    origin_lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        related_name="origin_movements",
        null=True,
        blank=True,
        verbose_name="Lote origen",
    )

    destination_farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="destination_movements",
        null=True,
        blank=True,
        verbose_name="Unidad productiva destino",
    )

    destination_lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        related_name="destination_movements",
        null=True,
        blank=True,
        verbose_name="Lote destino",
    )

    date = models.DateField(
        verbose_name="Fecha",
    )

    reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Motivo",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Observaciones",
    )

    class Meta:
        db_table = "animal_movements"

        verbose_name = "Movimiento de Animal"
        verbose_name_plural = "Movimientos de Animales"

        ordering = ["-date"]

        indexes = [
            models.Index(fields=["organization"]),
            models.Index(fields=["animal"]),
            models.Index(fields=["date"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.animal} - {self.movement_type} - {self.date}"