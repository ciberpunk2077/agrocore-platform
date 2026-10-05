import sqlite3

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.animals.models import Animal
from apps.catalogs.models import WeighingMethod
from apps.weights.models import Weight
from apps.common.exceptions.weight import WeightValidationError

from apps.common.services import BaseCRUDService


class WeightService:

    _duplicate_message = "Ya existe un pesaje registrado para este animal en esa fecha."

    @staticmethod
    def _is_duplicate_error(error):
        cause = error.__cause__
        constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
        if constraint is not None:
            return constraint == "unique_active_weight_per_animal_date"
        return isinstance(cause, sqlite3.IntegrityError) and str(cause) == (
            "UNIQUE constraint failed: weights.animal_id, weights.date"
        )

    @staticmethod
    def _validate_and_save(weight):
        try:
            weight.full_clean()
        except ValidationError as exc:
            if not hasattr(exc, "error_dict") or not exc.error_dict:
                raise
            recognized = {
                "weight": {"max_digits", "max_decimal_places", "max_whole_digits"},
                "__all__": {"active_weight_duplicate"},
            }
            if not all(
                errors and all(error.code in recognized.get(field, set()) for error in errors)
                for field, errors in exc.error_dict.items()
            ):
                raise
            duplicate = any(
                error.code == "active_weight_duplicate"
                for error in exc.error_dict.get("__all__", [])
            )
            message = WeightService._duplicate_message if duplicate else " ".join(exc.messages)
            raise WeightValidationError(message) from exc
        try:
            with transaction.atomic():
                weight.save()
        except IntegrityError as exc:
            if WeightService._is_duplicate_error(exc):
                raise WeightValidationError(WeightService._duplicate_message) from exc
            raise

    @staticmethod
    def create(context, data):

        try:

            relations = WeightService._load_relations(context, data)

            WeightService._validate_relations(
                context,
                relations,
            )

            WeightService._validate_business_rules(
                data,
                relations,
            )

            weight = Weight(
                organization=context.organization,
                animal=relations["animal"],
                weighing_method=relations["weighing_method"],
                date=data.date,
                weight=data.weight,
                notes="" if data.notes is None else data.notes,
            )

            WeightService._validate_and_save(weight)

            return weight

        except ObjectDoesNotExist:
            raise WeightValidationError(
                "El animal o el método de pesaje no existen."
            )

    @staticmethod
    def update(weight, context, data):

        try:

            relations = WeightService._load_relations(
                context,
                data,
            )

            WeightService._validate_relations(
                context,
                relations,
            )

            WeightService._validate_business_rules(
                data,
                relations,
                weight,
            )

            weight.animal = relations["animal"]
            weight.weighing_method = relations["weighing_method"]

            weight.date = data.date
            weight.weight = data.weight
            weight.notes = "" if data.notes is None else data.notes

            WeightService._validate_and_save(weight)

            return weight

        except ObjectDoesNotExist:
            raise WeightValidationError(
                "El animal o el método de pesaje no existen."
            )


        
    @staticmethod
    def delete(weight):

        return BaseCRUDService.soft_delete(weight)

    @staticmethod
    def _load_relations(context, data):

        return {
            "animal": Animal.objects.get(
                id=data.animal_id,
                organization=context.organization,
                is_active=True,
            ),
            "weighing_method": WeighingMethod.objects.get(
                id=data.weighing_method_id,                
                is_active=True,
            ),
        }

    @staticmethod
    def _validate_relations(context, relations):

        animal = relations["animal"]

        if animal.organization_id != context.organization.id:
            raise WeightValidationError(
                "El animal no pertenece a la organización actual."
            )

        if not animal.is_active:
            raise WeightValidationError(
                "No es posible registrar un pesaje para un animal inactivo."
            )

    @staticmethod
    def _validate_business_rules(
        data,
        relations,
        current_weight=None,
    ):

        if data.date > timezone.localdate():
            raise WeightValidationError(
                "La fecha del pesaje no puede ser futura."
            )

        if data.weight <= 0:
            raise WeightValidationError(
                "El peso debe ser mayor que cero."
            )

        animal = relations["animal"]
        if animal.birth_date is not None and data.date < animal.birth_date:
            raise WeightValidationError(
                "La fecha del pesaje no puede ser anterior al nacimiento del animal."
            )

        queryset = Weight.objects.filter(
            animal=relations["animal"],
            date=data.date,
            is_active=True,
        )

        if current_weight:
            queryset = queryset.exclude(
                id=current_weight.id,
            )

        if queryset.exists():
            raise WeightValidationError(
                "Ya existe un pesaje registrado para este animal en esa fecha."
            )
