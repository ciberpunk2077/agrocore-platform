# from .soft_delete import SoftDeleteModel


# class AuditModel(SoftDeleteModel):
#     """
#     Modelo base para auditoría.

#     En una etapa posterior agregaremos:
#     - created_by
#     - updated_by

#     cuando exista el modelo User.
#     """

#     class Meta:
#         abstract = True

import uuid

from django.db import models

from .soft_delete import SoftDeleteModel


class AuditModel(SoftDeleteModel):
    """
    Modelo base para todas las entidades del sistema.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        abstract = True