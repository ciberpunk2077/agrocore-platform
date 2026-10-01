from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)
from django.utils import timezone

from apps.animals.models import Animal
from apps.breeding.models import BreedingEvent
from apps.common.exceptions.pregnancy import PregnancyValidationError
from apps.pregnancy.models import Pregnancy, PregnancyStatus


class PregnancyService:

    @staticmethod
    def create(context, data):

        try:

            relations = PregnancyService._load_relations(
                context,
                data,
            )

            PregnancyService._validate_relations(
                context,
                relations,
            )

            PregnancyService._validate_pregnancy_data(
                data,
                relations,
            )

            pregnancy = Pregnancy(
                organization=context.organization,
                breeding=relations["breeding"],
                animal=relations["animal"],
                diagnosis_date=data.diagnosis_date,
                expected_birth=data.expected_birth,
                confirmed=data.confirmed,
                notes=data.notes,
            )

            try:
                pregnancy.full_clean()
            except ValidationError:
                raise PregnancyValidationError(
                    "Los datos de la gestación son inválidos."
                )
            pregnancy.save()

            return pregnancy

        except ObjectDoesNotExist:
            raise PregnancyValidationError(
                "Uno de los registros relacionados no existe."
            )

    @staticmethod
    def abort(context, pregnancy_id):

        try:
            pregnancy = Pregnancy.objects.get(
                id=pregnancy_id,
                organization=context.organization,
                is_active=True,
            )
        except Pregnancy.DoesNotExist:
            raise PregnancyValidationError(
                "La gestación no existe."
            )

        if pregnancy.organization_id != context.organization.id:
            raise PregnancyValidationError(
                "La gestación no pertenece a la organización."
            )

        if pregnancy.status != PregnancyStatus.ACTIVE:
            raise PregnancyValidationError(
                "Solo se puede abortar una gestación activa."
            )

        pregnancy.status = PregnancyStatus.ABORTED
        try:
            pregnancy.full_clean()
        except ValidationError:
            raise PregnancyValidationError(
                "Los datos de la gestación son inválidos."
            )
        pregnancy.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return pregnancy


    @staticmethod
    def _load_relations(context, data):

        return {
            "animal": Animal.objects.get(
                id=data.animal_id,
                organization=context.organization,
                is_active=True,
            ),
            "breeding": BreedingEvent.objects.get(
                id=data.breeding_id,
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
        breeding = relations["breeding"]

        if animal.organization_id != context.organization.id:
            raise PregnancyValidationError(
                "El animal no pertenece a la organización."
            )

        if breeding.organization_id != context.organization.id:
            raise PregnancyValidationError(
                "El evento reproductivo no pertenece a la organización."
            )

        if breeding.animal_id != animal.id:
            raise PregnancyValidationError(
                "El evento reproductivo no pertenece al animal."
            )

        # OneToOne also reserves the breeding event after soft deletion.
        if Pregnancy._base_manager.filter(
            breeding=breeding,
        ).exists():
            raise PregnancyValidationError(
                "Este evento reproductivo ya tiene una gestación registrada."
            )


    @staticmethod
    def _validate_pregnancy_data(
        data,
        relations,
    ):
        breeding = relations["breeding"]

        if not data.confirmed:
            raise PregnancyValidationError(
                "Solo se puede registrar una gestación confirmada."
            )

        if data.diagnosis_date < breeding.date:
            raise PregnancyValidationError(
                "La fecha de diagnóstico no puede ser anterior "
                "al evento reproductivo."
            )

        if data.diagnosis_date > timezone.localdate():
            raise PregnancyValidationError(
                "La fecha de diagnóstico no puede ser futura."
            )

        if data.expected_birth <= data.diagnosis_date:
            raise PregnancyValidationError(
                "La fecha estimada de parto debe ser posterior "
                "a la fecha de diagnóstico."
            )
