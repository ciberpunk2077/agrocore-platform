from django.db import models

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.common.models import AuditModel
from apps.organizations.models import Organization
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.catalogs.models import (
    Species,
    Breed,
    Gender,
    AnimalStatus,
)


class Animal(AuditModel):
    """
    Representa un animal dentro del sistema.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="animals",
        verbose_name="Organización",
    )

    farm = models.ForeignKey(
        Farm,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="animals",
        verbose_name="Unidad productiva",
    )

    lot = models.ForeignKey(
        Lot,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="animals",
        verbose_name="Lote",
    )

    species = models.ForeignKey(
        Species,
        on_delete=models.PROTECT,
        related_name="animals",
        verbose_name="Especie",
    )

    breed = models.ForeignKey(
        Breed,
        on_delete=models.PROTECT,
        related_name="animals",
        verbose_name="Raza",
    )

    gender = models.ForeignKey(
        Gender,
        on_delete=models.PROTECT,
        related_name="animals",
        verbose_name="Sexo",
    )

    status = models.ForeignKey(
        AnimalStatus,
        on_delete=models.PROTECT,
        related_name="animals",
        verbose_name="Estado",
    )

    internal_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Identificador interno",
    )

    official_tag = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Arete oficial",
    )

    electronic_tag = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="RFID",
    )

    name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Nombre",
    )

    birth_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de nacimiento",
    )

    birth_weight = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Peso al nacimiento",
    )

    mother = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offspring_from_mother",
        verbose_name="Madre",
    )

    father = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="offspring_from_father",
        verbose_name="Padre",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Observaciones",
    )

    class Meta:
        db_table = "animals"

        verbose_name = "Animal"
        verbose_name_plural = "Animales"

        ordering = ["internal_id"]

        constraints = [
            models.UniqueConstraint(
                fields=["organization", "internal_id"],
                name="unique_internal_id_per_organization",
            )
        ]

    def __str__(self):
        return self.internal_id


    def clean(self):
        """
        Reglas de negocio del modelo Animal.
        """

        # La raza debe pertenecer a la especie
        if self.breed and self.species:

            if self.breed.species_id != self.species_id:
                raise ValidationError(
                    {
                        "breed": (
                            "La raza seleccionada "
                            "no pertenece a la especie."
                        )
                    }
                )

        # Fecha futura
        if self.birth_date:

            if self.birth_date > timezone.now().date():

                raise ValidationError(
                    {
                        "birth_date": (
                            "La fecha de nacimiento "
                            "no puede ser futura."
                        )
                    }
                )


        self._validate_genealogy_cycles()

    def _validate_genealogy_cycles(self):
        """Reject ancestry paths back to this animal, including inactive ancestors."""
        errors = {}
        ancestors = Animal._base_manager.using(self._state.db).order_by()
        messages = {
            "mother": (
                "Un animal no puede ser su propia madre.",
                "La madre seleccionada genera un ciclo genealógico.",
            ),
            "father": (
                "Un animal no puede ser su propio padre.",
                "El padre seleccionado genera un ciclo genealógico.",
            ),
        }

        for field in ("mother", "father"):
            parent_id = getattr(self, f"{field}_id")
            if parent_id is None:
                continue
            if parent_id == self.pk:
                errors[field] = ValidationError(
                    messages[field][0], code="self_reference",
                )
                continue

            stack = [parent_id]
            visited = set()
            while stack:
                ancestor_id = stack.pop()
                if ancestor_id == self.pk:
                    errors[field] = ValidationError(
                        messages[field][1], code="genealogy_cycle",
                    )
                    break
                if ancestor_id in visited:
                    continue
                visited.add(ancestor_id)

                ancestor = ancestors.filter(pk=ancestor_id).values_list(
                    "id", "mother_id", "father_id",
                ).first()
                if ancestor is not None:
                    stack.extend(
                        parent for parent in ancestor[1:] if parent is not None
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):

        self.full_clean()

        super().save(*args, **kwargs)
