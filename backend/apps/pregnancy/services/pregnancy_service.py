import sqlite3

from django.db import IntegrityError, transaction
from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)
from django.utils import timezone

from apps.animals.models import Animal
from apps.breeding.models import BreedingEvent
from apps.common.exceptions.pregnancy import PregnancyValidationError
from apps.common.temporal import get_business_today
from apps.pregnancy.models import Pregnancy, PregnancyStatus


class PregnancyService:

    _active_message = "El animal ya tiene una gestación activa."
    _breeding_message = "Este evento reproductivo ya tiene una gestación registrada."

    @staticmethod
    def _validate_no_active_pregnancy(context, animal):
        if Pregnancy.objects.filter(
            organization=context.organization, animal=animal,
            status=PregnancyStatus.ACTIVE, is_active=True,
        ).exists():
            raise PregnancyValidationError(PregnancyService._active_message)

    @staticmethod
    def _is_active_pregnancy_error(error):
        cause = error.__cause__
        constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
        if constraint is not None:
            return constraint == "unique_active_pregnancy_per_animal"
        return isinstance(cause, sqlite3.IntegrityError) and str(cause) == (
            "UNIQUE constraint failed: pregnancies.animal_id"
        )

    @staticmethod
    def _is_breeding_collision(error):
        # The migration uses unnamed UNIQUE; do not assume a PostgreSQL name.
        cause = error.__cause__
        return isinstance(cause, sqlite3.IntegrityError) and str(cause) == (
            "UNIQUE constraint failed: pregnancies.breeding_id"
        )

    @staticmethod
    def _save(pregnancy):
        try:
            with transaction.atomic():
                pregnancy.save()
        except IntegrityError as exc:
            if PregnancyService._is_active_pregnancy_error(exc):
                raise PregnancyValidationError(PregnancyService._active_message) from exc
            if PregnancyService._is_breeding_collision(exc):
                raise PregnancyValidationError(PregnancyService._breeding_message) from exc
            raise

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
                context,
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
            except ValidationError as exc:
                errors = exc.error_dict.get("__all__", []) if hasattr(exc, "error_dict") else []
                if any(error.code == "active_pregnancy" for error in errors):
                    raise PregnancyValidationError(PregnancyService._active_message) from exc
                raise PregnancyValidationError(
                    "Los datos de la gestación son inválidos."
                ) from exc
            PregnancyService._save(pregnancy)

            return pregnancy

        except ObjectDoesNotExist:
            raise PregnancyValidationError(
                "Uno de los registros relacionados no existe."
            )

    @staticmethod
    @transaction.atomic
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
        updated_at = timezone.now()
        affected_rows = Pregnancy.objects.filter(
            id=pregnancy_id, organization=context.organization,
            is_active=True, status=PregnancyStatus.ACTIVE,
        ).update(status=PregnancyStatus.ABORTED, updated_at=updated_at)
        if affected_rows != 1:
            raise PregnancyValidationError("Solo se puede abortar una gestación activa.")
        pregnancy.updated_at = updated_at

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

        PregnancyService._validate_no_active_pregnancy(context, animal)


    @staticmethod
    def _validate_pregnancy_data(
        context,
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

        if data.diagnosis_date > get_business_today(context):
            raise PregnancyValidationError(
                "La fecha de diagnóstico no puede ser futura."
            )

        if data.expected_birth <= data.diagnosis_date:
            raise PregnancyValidationError(
                "La fecha estimada de parto debe ser posterior "
                "a la fecha de diagnóstico."
            )
