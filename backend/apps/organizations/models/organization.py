from django.db import models
from django.utils.text import slugify
from apps.common.models import AuditModel




class Organization(AuditModel):
    """
    Empresa propietaria de la información del sistema.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Nombre",
    )

    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name="Código",
    )

    tax_id = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="RFC / Identificación Fiscal",
    )

    email = models.EmailField(
        blank=True,
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
    )

    website = models.URLField(
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    slug = models.SlugField(
            max_length=220,
            unique=True,
            editable=False,
            blank=True,
            verbose_name="Slug",
        )
    

    def save(self, *args, **kwargs):
        # if not self.slug:
        if self.name and not self.slug:
            self.slug = slugify(self.name)

        super().save(*args, **kwargs)

    class Meta:
        db_table = "organization"
        verbose_name = "Organización"
        verbose_name_plural = "Organizaciones"
        ordering = ["name"]

        indexes = [
            models.Index(fields=["name"]),
            # models.Index(fields=["code"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name