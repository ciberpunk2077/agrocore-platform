from django.db import models

from apps.common.models import AuditModel
from apps.organizations.models import Organization
from .user import User


class Membership(AuditModel):
    """
    Relación entre usuarios y organizaciones.
    """

    class Role(models.TextChoices):
        OWNER = "OWNER", "Propietario"
        ADMIN = "ADMIN", "Administrador"
        VETERINARIAN = "VETERINARIAN", "Veterinario"
        OPERATOR = "OPERATOR", "Operador"
        VIEWER = "VIEWER", "Consulta"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.VIEWER,
    )

    is_default = models.BooleanField(
        default=False,
        help_text="Organización principal del usuario.",
    )


    class Meta:
        db_table = "memberships"
        verbose_name = "Membresía"
        verbose_name_plural = "Membresías"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "user",
                    "organization",
                ],
                name="unique_user_organization",
            )
        ]


    def __str__(self):
        return f"{self.user.email} - {self.organization.name}"