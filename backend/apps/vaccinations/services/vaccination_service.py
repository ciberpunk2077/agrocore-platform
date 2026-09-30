from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)
from django.db import transaction
from apps.common.exceptions.vaccination import VaccinationValidationError
from apps.animals.models import Animal
from apps.vaccinations.models import Vaccination
from django.utils import timezone

from apps.common.services import BaseCRUDService


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

            VaccinationService._validate_business_rules(data)

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
            vaccination.full_clean()
            vaccination.save()

            return vaccination

        except ObjectDoesNotExist:
            raise VaccinationValidationError(
                "El animal no existe."
            )

        except ValidationError:
            raise VaccinationValidationError(
                "Los datos de la vacunación son inválidos."
            )

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
            raise ValidationError(
                "El animal no pertenece a la organización actual."
            )

        if not animal.is_active:
            raise ValidationError(
                "No es posible registrar una vacunación para un animal inactivo."
            )


    @staticmethod
    def _validate_business_rules(data):

        if data.application_date > timezone.localdate():
            raise VaccinationValidationError(
                "La fecha de aplicación no puede ser futura."
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

            VaccinationService._validate_business_rules(data)

            vaccination.animal = relations["animal"]

            vaccination.vaccine_name = data.vaccine_name
            vaccination.application_date = data.application_date
            vaccination.next_application_date = data.next_application_date

            vaccination.dose = data.dose
            vaccination.batch = data.batch
            vaccination.veterinarian = data.veterinarian
            vaccination.notes = data.notes

            VaccinationService._normalize_optional_text(vaccination)
            vaccination.full_clean()
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
