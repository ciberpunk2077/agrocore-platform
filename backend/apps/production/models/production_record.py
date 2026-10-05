from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.utils import timezone

from apps.animals.models import Animal
from apps.catalogs.models import ProductionType
from apps.common.models import AuditModel
from apps.organizations.models import Organization


class ProductionRecord(AuditModel):
    """Producción obtenida de un animal, con su unidad histórica."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="production_records",
        verbose_name="Organización",
    )
    animal = models.ForeignKey(
        Animal,
        on_delete=models.PROTECT,
        related_name="production_records",
        verbose_name="Animal",
    )
    production_type = models.ForeignKey(
        ProductionType,
        on_delete=models.PROTECT,
        related_name="production_records",
        verbose_name="Tipo de producción",
    )
    recorded_at = models.DateTimeField(verbose_name="Fecha y hora de producción")
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="Cantidad",
    )
    unit = models.CharField(max_length=20, verbose_name="Unidad")
    notes = models.TextField(blank=True, verbose_name="Observaciones")

    class Meta:
        db_table = "production_records"
        verbose_name = "Registro de producción"
        verbose_name_plural = "Registros de producción"
        ordering = ["-recorded_at", "-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "is_active", "recorded_at"]),
            models.Index(fields=["organization", "animal", "is_active", "recorded_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="production_quantity_positive",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.notes is None:
            errors["notes"] = "Las observaciones no pueden ser nulas; use texto vacío."

        # Invalid scalar values and absent FKs are reported by clean_fields().
        if isinstance(self.quantity, Decimal) and self.quantity.is_finite() and self.quantity <= 0:
            errors["quantity"] = "La cantidad debe ser mayor que cero."

        recorded_date = None
        if isinstance(self.recorded_at, datetime):
            if timezone.is_naive(self.recorded_at):
                errors["recorded_at"] = "La fecha y hora de producción debe incluir zona horaria."
            else:
                if self.recorded_at > timezone.now():
                    errors["recorded_at"] = "La fecha y hora de producción no puede ser futura."
                try:
                    recorded_date = timezone.localdate(self.recorded_at)
                except OverflowError as error:
                    raise ValidationError({
                        "recorded_at": ValidationError(
                            "La fecha y hora de producción no puede convertirse a la zona horaria activa.",
                            code="recorded_at_timezone_overflow",
                        ),
                    }) from error

        try:
            animal = self.animal
        except ObjectDoesNotExist:
            animal = None

        if animal is not None:
            if self.organization_id is not None and animal.organization_id != self.organization_id:
                errors["animal"] = "El animal no pertenece a la organización seleccionada."
            elif self.is_active and not animal.is_active:
                errors["animal"] = "No es posible registrar producción para un animal inactivo."

            if recorded_date is not None and animal.birth_date is not None and recorded_date < animal.birth_date:
                errors["recorded_at"] = "La fecha de producción no puede ser anterior al nacimiento del animal."

        if self.is_active:
            try:
                production_type = self.production_type
            except ObjectDoesNotExist:
                production_type = None
            if production_type is not None and not production_type.is_active:
                errors["production_type"] = "El tipo de producción debe estar activo."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.animal_id} - {self.quantity} {self.unit} - {self.recorded_at}"
