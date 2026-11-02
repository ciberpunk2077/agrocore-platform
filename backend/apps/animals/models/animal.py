from django.db import models
from django.apps import apps

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

            today = getattr(self, "_birth_business_today", None)
            if today is None:
                today = timezone.now().date()
            if self.birth_date > today:

                raise ValidationError(
                    {
                        "birth_date": (
                            "La fecha de nacimiento "
                            "no puede ser futura."
                        )
                    }
                )


        errors = {}
        if self.birth_weight is not None and self.birth_weight <= 0:
            errors["birth_weight"] = ValidationError(
                "El peso al nacimiento debe ser mayor que cero.",
                code="invalid_birth_weight",
            )

        for field, message in (
            ("mother", "La madre debe pertenecer a la misma organización que el animal."),
            ("father", "El padre debe pertenecer a la misma organización que el animal."),
        ):
            if getattr(self, f"{field}_id") is None:
                continue
            try:
                parent = getattr(self, field)
            except Animal.DoesNotExist:
                # FK existence is checked by full_clean().
                continue
            if parent.organization_id != self.organization_id:
                errors[field] = ValidationError(message, code="parent_organization")


        for field, expected_gender, message, code in (
            (
                "mother",
                "F",
                "El animal seleccionado como madre debe ser una hembra.",
                "invalid_mother_gender",
            ),
            (
                "father",
                "M",
                "El animal seleccionado como padre debe ser un macho.",
                "invalid_father_gender",
            ),
        ):
            if getattr(self, f"{field}_id") is None:
                continue

            try:
                parent = getattr(self, field)
            except Animal.DoesNotExist:
                # FK existence is checked by full_clean().
                continue

            if parent.gender.code != expected_gender:
                errors[field] = ValidationError(
                    message,
                    code=code,
                )


        try:
            self._validate_genealogy_cycles()
        except ValidationError as error:
            errors = error.update_error_dict(errors)
        try:
            self._validate_dependent_history()
        except ValidationError as error:
            errors = error.update_error_dict(errors)
        if errors:
            raise ValidationError(errors)

    def _validate_dependent_history(self):
        """Protect historical references only when persisted fields change."""
        if self._state.adding:
            return
        database = self._state.db
        persisted = Animal._base_manager.using(database).filter(pk=self.pk).values(
            "gender_id", "birth_date",
        ).first()
        if persisted is None:
            return
        errors = {}
        if persisted["gender_id"] != self.gender_id:
            gender_code = Gender._base_manager.using(database).filter(pk=self.gender_id).values_list(
                "code", flat=True,
            ).first()
            # Missing foreign keys are reported by clean_fields().
            if gender_code is not None:
                breeding = apps.get_model("breeding", "BreedingEvent")._base_manager.using(database)
                animals = Animal._base_manager.using(database)
                if gender_code != "F" and (
                    animals.filter(mother_id=self.pk).exists()
                    or breeding.filter(animal_id=self.pk).exists()
                ):
                    errors["gender"] = ValidationError(
                        "El sexo debe seguir siendo F porque el animal tiene referencias históricas como madre o hembra reproductora.",
                        code="dependent_gender",
                    )
                if gender_code != "M" and (
                    animals.filter(father_id=self.pk).exists()
                    or breeding.filter(male_id=self.pk).exists()
                ):
                    errors["gender"] = ValidationError(
                        "El sexo debe seguir siendo M porque el animal tiene referencias históricas como padre o macho reproductor.",
                        code="dependent_gender",
                    )
        if persisted["birth_date"] != self.birth_date and self.birth_date is not None:
            weights = apps.get_model("weights", "Weight")._base_manager.using(database)
            if weights.filter(animal_id=self.pk, date__lt=self.birth_date).exists():
                errors["birth_date"] = ValidationError(
                    "La fecha de nacimiento no puede ser posterior a un pesaje histórico del animal.",
                    code="dependent_birth_date",
                )
            else:
                records = apps.get_model("production", "ProductionRecord")._base_manager.using(database)
                # Match ProductionRecord.clean() exactly, including the active
                # timezone, without relying on backend-specific date truncation.
                timestamps = records.filter(animal_id=self.pk).values_list("recorded_at", flat=True)
                if any(timezone.localdate(timestamp) < self.birth_date for timestamp in timestamps.iterator()):
                    errors["birth_date"] = ValidationError(
                        "La fecha de nacimiento no puede ser posterior a un registro histórico de producción del animal.",
                        code="dependent_birth_date",
                    )
        if errors:
            raise ValidationError(errors)

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
        # Only the automatic Birth path supplies a tenant civil day. Ordinary
        # Animal writes retain their existing temporal contract.
        business_today = kwargs.pop("_birth_business_today", None)
        if business_today is not None:
            self._birth_business_today = business_today
        try:
            self.full_clean()
            super().save(*args, **kwargs)
        finally:
            if business_today is not None:
                del self._birth_business_today
