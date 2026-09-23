from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.common.services import BaseCRUDService
from apps.catalogs.models import FarmType
from apps.farms.models import Farm
from apps.common.exceptions import BusinessException


class FarmService:

    @staticmethod
    @transaction.atomic
    def create(context, data):

        try:
            farm_type = FarmType.objects.get(
                id=data.farm_type_id,
                is_active=True,
            )

            farm = Farm(
                organization=context.organization,
                name=data.name,
                code=data.code,
                farm_type=farm_type,
                description=data.description,
                address=data.address,
                city=data.city,
                state=data.state,
                country=data.country,
            )

            farm.full_clean()
            farm.save()

            return farm

        except ObjectDoesNotExist:
            raise BusinessException(
                "El tipo de unidad productiva no existe o no está activo."
            )

    @staticmethod
    @transaction.atomic
    def update(farm, context, data):

        try:
            farm_type = FarmType.objects.get(
                id=data.farm_type_id,
                is_active=True,
            )

            farm.name = data.name
            farm.code = data.code
            farm.farm_type = farm_type
            farm.description = data.description
            farm.address = data.address
            farm.city = data.city
            farm.state = data.state
            farm.country = data.country

            farm.full_clean()
            farm.save()

            return farm

        except ObjectDoesNotExist:
            raise BusinessException(
                "El tipo de unidad productiva no existe o no está activo."
            )

    @staticmethod
    def delete(farm):

        return BaseCRUDService.soft_delete(
            farm,
        )