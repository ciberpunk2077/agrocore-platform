import sqlite3

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction

from apps.common.services import BaseCRUDService
from apps.catalogs.models import FarmType
from apps.farms.models import Farm
from apps.common.exceptions import BusinessException
from apps.common.exceptions.farm import FarmValidationError


class FarmService:

    _reserved_code_message = (
        "El código ya está reservado por una unidad productiva de esta organización."
    )

    @staticmethod
    def _validate_reserved_code(context, code, current_farm=None):
        reserved = Farm._base_manager.filter(
            organization=context.organization, code=code,
        )
        if current_farm is not None:
            reserved = reserved.exclude(pk=current_farm.pk)
        if reserved.exists():
            raise FarmValidationError(FarmService._reserved_code_message)

    @staticmethod
    def _is_reserved_code_error(error):
        cause = error.__cause__
        constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
        if constraint is not None:
            return constraint == "unique_farm_code_per_organization"
        # SQLite reports columns rather than the declared constraint name.
        return isinstance(cause, sqlite3.IntegrityError) and str(cause) == (
            "UNIQUE constraint failed: farms.organization_id, farms.code"
        )

    @staticmethod
    def _save(farm):
        try:
            with transaction.atomic():
                farm.save()
        except IntegrityError as error:
            # The inner savepoint has rolled back before callers can refresh/query.
            if FarmService._is_reserved_code_error(error):
                raise FarmValidationError(FarmService._reserved_code_message) from error
            raise

    @staticmethod
    @transaction.atomic
    def create(context, data):

        try:
            farm_type = FarmType.objects.get(
                id=data.farm_type_id,
                is_active=True,
            )

            FarmService._validate_reserved_code(context, data.code)
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
            FarmService._save(farm)

            return farm

        except ValidationError as error:
            raise FarmValidationError(" ".join(error.messages)) from error

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

            FarmService._validate_reserved_code(context, data.code, farm)
            farm.name = data.name
            farm.code = data.code
            farm.farm_type = farm_type
            farm.description = data.description
            farm.address = data.address
            farm.city = data.city
            farm.state = data.state
            farm.country = data.country

            farm.full_clean()
            FarmService._save(farm)

            return farm

        except ValidationError as error:
            farm.refresh_from_db()
            raise FarmValidationError(" ".join(error.messages)) from error

        except FarmValidationError:
            farm.refresh_from_db()
            raise

        except ObjectDoesNotExist:
            raise BusinessException(
                "El tipo de unidad productiva no existe o no está activo."
            )

    @staticmethod
    def delete(farm):

        return BaseCRUDService.soft_delete(
            farm,
        )
