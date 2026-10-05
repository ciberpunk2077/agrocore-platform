import sqlite3

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.common.exceptions.lot import LotValidationError
from apps.common.services import BaseCRUDService
from apps.farms.models import Farm
from apps.lots.models import Lot


class LotService:
    _reserved_code_message = "El código ya está reservado por un lote de esta organización."

    @staticmethod
    def _load_farm(context, farm_id):
        try:
            return Farm.objects.get(
                id=farm_id, organization=context.organization, is_active=True,
            )
        except Farm.DoesNotExist as error:
            raise LotValidationError(
                "La unidad productiva no existe o no pertenece a la organización actual."
            ) from error

    @staticmethod
    def _validate_lot(lot, context):
        organization = getattr(context, "organization", None)
        if (
            organization is None
            or lot.organization_id != organization.pk
            or lot.is_active is not True
            or not Lot.objects.filter(
                pk=lot.pk, organization=organization, is_active=True,
            ).exists()
        ):
            raise LotValidationError("El lote no existe o no pertenece a la organización actual.")

    @staticmethod
    def _validate_reserved_code(context, code, current_lot=None):
        reserved = Lot._base_manager.filter(organization=context.organization, code=code)
        if current_lot is not None:
            reserved = reserved.exclude(pk=current_lot.pk)
        if reserved.exists():
            raise LotValidationError(LotService._reserved_code_message)

    @staticmethod
    def _is_reserved_code_error(error):
        cause = error.__cause__
        constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
        if constraint is not None:
            return constraint == "unique_lot_code_per_organization"
        return isinstance(cause, sqlite3.IntegrityError) and str(cause) == (
            "UNIQUE constraint failed: lots.organization_id, lots.code"
        )

    @staticmethod
    def _save(lot):
        try:
            with transaction.atomic():
                lot.save()
        except IntegrityError as error:
            # The savepoint has rolled back before the caller refreshes the lot.
            if LotService._is_reserved_code_error(error):
                raise LotValidationError(LotService._reserved_code_message) from error
            raise

    @staticmethod
    @transaction.atomic
    def create(context, data):
        farm = LotService._load_farm(context, data.farm_id)
        LotService._validate_reserved_code(context, data.code)
        lot = Lot(
            organization=context.organization, farm=farm, code=data.code,
            name=data.name, description=data.description, capacity=data.capacity,
        )
        try:
            lot.full_clean()
            LotService._save(lot)
        except ValidationError as error:
            raise LotValidationError(" ".join(error.messages)) from error
        return lot

    @staticmethod
    @transaction.atomic
    def update(lot, context, data):
        LotService._validate_lot(lot, context)
        farm = LotService._load_farm(context, data.farm_id)
        LotService._validate_reserved_code(context, data.code, lot)
        if farm.pk != lot.farm_id and lot.animals.filter(is_active=True).exists():
            raise LotValidationError(
                "No se puede cambiar la unidad productiva del lote mientras tenga animales activos asociados."
            )
        lot.farm = farm
        lot.code = data.code
        lot.name = data.name
        lot.description = data.description
        lot.capacity = data.capacity
        try:
            lot.full_clean()
            LotService._save(lot)
        except ValidationError as error:
            lot.refresh_from_db()
            raise LotValidationError(" ".join(error.messages)) from error
        except LotValidationError:
            lot.refresh_from_db()
            raise
        return lot

    @staticmethod
    def delete(lot, context):
        LotService._validate_lot(lot, context)
        return BaseCRUDService.soft_delete(lot)
