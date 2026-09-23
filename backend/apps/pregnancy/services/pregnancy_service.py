from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)

from apps.animals.models import Animal
from apps.breeding.models import BreedingEvent
from apps.pregnancy.models import Pregnancy


class PregnancyService:

    @staticmethod
    def create(context, data):

        try:

            relations = PregnancyService._load_relations(
                data,
            )

            PregnancyService._validate_relations(
                context,
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

            pregnancy.full_clean()
            pregnancy.save()

            return pregnancy

        except ObjectDoesNotExist:
            raise ValidationError(
                "Uno de los registros relacionados no existe."
            )


    @staticmethod
    def _load_relations(data):

        return {
            "animal": Animal.objects.get(
                id=data.animal_id,
            ),
            "breeding": BreedingEvent.objects.get(
                id=data.breeding_id,
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
            raise ValidationError(
                "El animal no pertenece a la organización."
            )

        if breeding.organization_id != context.organization.id:
            raise ValidationError(
                "El evento reproductivo no pertenece a la organización."
            )

        if breeding.animal_id != animal.id:
            raise ValidationError(
                "El evento reproductivo no pertenece al animal."
            )

        if Pregnancy.objects.filter(
            breeding=breeding,
            is_active=True,
        ).exists():
            raise ValidationError(
                "Este evento reproductivo ya tiene una gestación registrada."
            )