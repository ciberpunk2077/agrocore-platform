from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction

from apps.animals.models import Animal
from apps.catalogs.models import ProductionType
from apps.common.exceptions.production import ProductionValidationError
from apps.common.services import BaseCRUDService
from apps.production.models import ProductionRecord


class ProductionService:

    @staticmethod
    @transaction.atomic
    def create(context, data):
        ProductionService._validate_context(context)
        try:
            relations = ProductionService._load_relations(context, data)
            record = ProductionRecord(organization=context.organization)
            ProductionService._assign_fields(record, data, relations)
            record.save()
            return record
        except ObjectDoesNotExist as error:
            raise ProductionValidationError(
                "El animal o el tipo de producción no existen o no están disponibles."
            ) from error
        except ValidationError as error:
            raise ProductionValidationError(ProductionService._validation_message(error)) from error

    @staticmethod
    @transaction.atomic
    def update(context, record, data):
        ProductionService._validate_record(context, record)
        try:
            relations = ProductionService._load_relations(context, data)
            ProductionService._assign_fields(record, data, relations)
            record.save()
            return record
        except ObjectDoesNotExist as error:
            raise ProductionValidationError(
                "El animal o el tipo de producción no existen o no están disponibles."
            ) from error
        except ValidationError as error:
            record.refresh_from_db()
            raise ProductionValidationError(ProductionService._validation_message(error)) from error

    @staticmethod
    def delete(context, record):
        ProductionService._validate_record(context, record)
        try:
            return BaseCRUDService.soft_delete(record)
        except ValidationError as error:
            record.refresh_from_db()
            raise ProductionValidationError(" ".join(error.messages)) from error

    @staticmethod
    def _validation_message(error):
        fields = getattr(error, "error_dict", {})
        if set(fields) == {"recorded_at"} and len(fields["recorded_at"]) == 1:
            boundary_error = fields["recorded_at"][0]
            if boundary_error.code == "recorded_at_timezone_overflow":
                return boundary_error.message
        # Preserve the existing broad translation until the separate H5-H2 fix.
        return " ".join(error.messages)

    @staticmethod
    def _validate_context(context):
        if context.organization is None:
            raise ProductionValidationError("Se requiere una organización actual.")

    @staticmethod
    def _validate_record(context, record):
        ProductionService._validate_context(context)
        if (
            record.organization_id != context.organization.pk
            or not record.is_active
            or not ProductionRecord.objects.filter(
                pk=record.pk, organization=context.organization, is_active=True,
            ).exists()
        ):
            raise ProductionValidationError("Registro de producción no encontrado.")

    @staticmethod
    def _load_relations(context, data):
        return {
            "animal": Animal.objects.get(
                id=data.animal_id, organization=context.organization, is_active=True,
            ),
            "production_type": ProductionType.objects.get(
                id=data.production_type_id, is_active=True,
            ),
        }

    @staticmethod
    def _assign_fields(record, data, relations):
        record.animal = relations["animal"]
        record.production_type = relations["production_type"]
        record.recorded_at = data.recorded_at
        record.quantity = data.quantity
        record.unit = relations["production_type"].default_unit
        notes = getattr(data, "notes", None)
        record.notes = "" if notes is None else notes
