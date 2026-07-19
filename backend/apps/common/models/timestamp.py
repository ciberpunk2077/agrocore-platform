from django.db import models


class TimeStampedModel(models.Model):
    """
    Modelo abstracto que agrega fechas de creación y actualización.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de creación",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Fecha de actualización",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]