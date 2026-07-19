# from django.db import models

# from apps.common.managers import SoftDeleteManager
# from .timestamp import TimeStampedModel


# class SoftDeleteModel(TimeStampedModel):
#     """
#     Modelo abstracto con borrado lógico.
#     """

#     is_active = models.BooleanField(
#         default=True,
#         verbose_name="Activo",
#     )

#     deleted_at = models.DateTimeField(
#         blank=True,
#         null=True,
#         verbose_name="Fecha de eliminación",
#     )

#     objects = SoftDeleteManager()

#     class Meta:
#         abstract = True


from django.db import models
from django.utils import timezone

from apps.common.managers import SoftDeleteManager
from .timestamp import TimeStampedModel


class SoftDeleteModel(TimeStampedModel):
    """
    Modelo abstracto que implementa borrado lógico.
    """

    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo",
    )

    deleted_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Fecha de eliminación",
    )

    objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        Realiza un borrado lógico.
        """
        self.is_active = False
        self.deleted_at = timezone.now()

        self.save(
            update_fields=[
                "is_active",
                "deleted_at",
                "updated_at",
            ]
        )

    def restore(self):
        """
        Restaura un registro eliminado.
        """
        self.is_active = True
        self.deleted_at = None

        self.save(
            update_fields=[
                "is_active",
                "deleted_at",
                "updated_at",
            ]
        )