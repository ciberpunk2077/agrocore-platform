from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)
from django.db import transaction
from apps.common.exceptions.vaccination import VaccinationValidationError
from apps.animals.models import Animal
from apps.vaccinations.models import Vaccination
from django.utils import timezone
from zoneinfo import ZoneInfo

from apps.common.services import BaseCRUDService

VACCINATION_TIME_ZONE = ZoneInfo("America/Mexico_City")


class VaccinationService:

    @staticmethod
    @transaction.atomic
    def create(context, data):

        try:

            relations = VaccinationService._load_relations(context, data)

            VaccinationService._validate_relations(
                context,
                relations,
            )

            VaccinationService._validate_business_rules(data, relations["animal"])

            vaccination = Vaccination(
                organization=context.organization,
                animal=relations["animal"],
                vaccine_name=data.vaccine_name,
                application_date=data.application_date,
                next_application_date=data.next_application_date,
                dose=data.dose,
                batch=data.batch,
                veterinarian=data.veterinarian,
                notes=data.notes,
            )

            VaccinationService._normalize_optional_text(vaccination)
            VaccinationService._full_clean(vaccination)
            vaccination.save()

            return vaccination

        except ObjectDoesNotExist:
            raise VaccinationValidationError(
                "El animal no existe."
            )

    @staticmethod
    def _full_clean(vaccination):
        try:
            vaccination.full_clean()
        except ValidationError as exc:
            recognized = {
                "vaccine_name": {"blank", "max_length"},
                "batch": {"max_length"},
                "veterinarian": {"max_length"},
                "dose": {"max_digits", "max_decimal_places", "max_whole_digits"},
            }
            if not hasattr(exc, "error_dict") or not exc.error_dict:
                raise
            if not all(
                errors and all(error.code in recognized.get(field, set()) for error in errors)
                for field, errors in exc.error_dict.items()
            ):
                raise
            raise VaccinationValidationError(" ".join(exc.messages)) from exc

    @staticmethod
    def _normalize_optional_text(vaccination):
        for field in ("batch", "veterinarian", "notes"):
            if getattr(vaccination, field) is None:
                setattr(vaccination, field, "")

    @staticmethod
    def _load_relations(context, data):

        return {
            "animal": Animal.objects.get(
                id=data.animal_id,
                organization=context.organization,
                is_active=True,
            ),
        }


    @staticmethod
    def _validate_relations(
        context,
        relations,
    ):

        animal = relations["animal"]

        if animal.organization_id != context.organization.id:
            raise VaccinationValidationError(
                "El animal no pertenece a la organización actual."
            )

        if not animal.is_active:
            raise VaccinationValidationError(
                "No es posible registrar una vacunación para un animal inactivo."
            )


    @staticmethod
    def _validate_business_rules(data, animal):

        if data.application_date > timezone.localdate(timezone=VACCINATION_TIME_ZONE):
            raise VaccinationValidationError(
                "La fecha de aplicación no puede ser futura."
            )

        if animal.birth_date is not None and data.application_date < animal.birth_date:
            raise VaccinationValidationError(
                "La fecha de aplicación no puede ser anterior al nacimiento del animal."
            )

        if data.dose <= 0:
            raise VaccinationValidationError(
                "La dosis debe ser mayor que cero."
            )

        if (
            data.next_application_date is not None
            and data.next_application_date <= data.application_date
        ):
            raise VaccinationValidationError(
                "La próxima fecha de aplicación debe ser posterior a la fecha de aplicación."
            )

        


    @staticmethod
    @transaction.atomic
    def update(vaccination, context, data):

        try:

            relations = VaccinationService._load_relations(
                context,
                data,
            )

            VaccinationService._validate_relations(
                context,
                relations,
            )

            VaccinationService._validate_business_rules(data, relations["animal"])

            vaccination.animal = relations["animal"]

            vaccination.vaccine_name = data.vaccine_name
            vaccination.application_date = data.application_date
            vaccination.next_application_date = data.next_application_date

            vaccination.dose = data.dose
            vaccination.batch = data.batch
            vaccination.veterinarian = data.veterinarian
            vaccination.notes = data.notes

            VaccinationService._normalize_optional_text(vaccination)
            VaccinationService._full_clean(vaccination)
            vaccination.save()

            return vaccination

        except ObjectDoesNotExist:
            raise VaccinationValidationError(
                "El animal no existe."
            )

     
    @staticmethod
    def delete(vaccination):

        return BaseCRUDService.soft_delete(
            vaccination,
        )
