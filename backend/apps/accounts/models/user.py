
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.models import AuditModel
from apps.accounts.managers import UserManager


class User(AuditModel, AbstractUser):
    """
    Modelo de usuario personalizado.
    """

    username = None

    email = models.EmailField(
        unique=True,
        db_index=True,
        verbose_name="Correo electrónico",
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Teléfono",
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
    )

    language = models.CharField(
        max_length=10,
        default="es",
    )

    timezone = models.CharField(
        max_length=50,
        default="America/Mexico_City",
    )

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = [
        "first_name",
        "last_name",
    ]

    objects = UserManager()

    class Meta:
        db_table = "user"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return self.email