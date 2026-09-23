from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction

from apps.common.services import BaseCRUDService
from apps.farms.models import Farm
from apps.lots.models import Lot


class LotService:

    @staticmethod
    @transaction.atomic
    def create(context, data):

        try:
            farm = Farm.objects.get(
                id=data.farm_id,
                organization=context.organization,
                is_active=True,
            )

            lot = Lot(
                organization=context.organization,
                farm=farm,
                code=data.code,
                name=data.name,
                description=data.description,
                capacity=data.capacity,
            )

            lot.full_clean()
            lot.save()

            return lot

        except ObjectDoesNotExist:
            raise ValidationError(
                "La unidad productiva no existe o no pertenece a la organización actual."
            )

    @staticmethod
    @transaction.atomic
    def update(lot, context, data):

        try:
            farm = Farm.objects.get(
                id=data.farm_id,
                organization=context.organization,
                is_active=True,
            )

            lot.farm = farm
            lot.code = data.code
            lot.name = data.name
            lot.description = data.description
            lot.capacity = data.capacity

            lot.full_clean()
            lot.save()

            return lot

        except ObjectDoesNotExist:
            raise ValidationError(
                "La unidad productiva no existe o no pertenece a la organización actual."
            )

    @staticmethod
    def delete(lot):

        return BaseCRUDService.soft_delete(
            lot,
        )