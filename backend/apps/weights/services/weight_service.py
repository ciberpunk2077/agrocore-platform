from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from apps.animals.models import Animal
from apps.catalogs.models import WeighingMethod
from apps.weights.models import Weight
from apps.common.exceptions.weight import WeightValidationError

from apps.common.services import BaseCRUDService


class WeightService:

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
                notes=data.notes,
            )

            weight.full_clean()
            weight.save()

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
            weight.notes = data.notes

            weight.full_clean()
            weight.save()

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