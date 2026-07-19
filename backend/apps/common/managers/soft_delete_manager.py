from django.db import models


class SoftDeleteManager(models.Manager):
    """
    Manager que devuelve únicamente registros activos.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)