from django.core.exceptions import ObjectDoesNotExist, ValidationError

from apps.animals.models import Animal
from apps.catalogs.models import BreedingType
from apps.breeding.models import BreedingEvent
from apps.common.exceptions.breeding import BreedingValidationError

from apps.common.services import BaseCRUDService


class BreedingService:

    @staticmethod
    def create(context, data):

        try:

            relations = BreedingService._load_relations(context, data)

            BreedingService._validate_relations(
                context,
                relations,
            )

            event = BreedingEvent(
                organization=context.organization,
                animal=relations["animal"],
                male=relations["male"],
                breeding_type=relations["breeding_type"],
                date=data.date,
                expected_birth=data.expected_birth,
                technician=data.technician,
                notes=data.notes,
            )

            event.full_clean()
            event.save()

            return event

        except ObjectDoesNotExist:
            raise BreedingValidationError(
                "La hembra, el macho o el tipo de reproducción no existen."
            )

    @staticmethod
    def update(event, context, data):

        relations = BreedingService._load_relations(data)

        BreedingService._validate_relations(
            context,
            relations,
        )

        event.animal = relations["animal"]
        event.male = relations["male"]
        event.breeding_type = relations["breeding_type"]

        event.date = data.date
        event.expected_birth = data.expected_birth
        event.technician = data.technician
        event.notes = data.notes

        event.full_clean()
        event.save()

        return event

    @staticmethod
    def delete(event):

        return BaseCRUDService.soft_delete(
            event,
        )

    @staticmethod
    def _load_relations(context, data):

        return {
            "animal": Animal.objects.get(
                id=data.animal_id,
                organization=context.organization,
                is_active=True,
            ),
            "male": (
                Animal.objects.get(
                    id=data.male_id,
                    organization=context.organization,
                    is_active=True,
                )
                if data.male_id
                else None
            ),
            "breeding_type": BreedingType.objects.get(
                id=data.breeding_type_id,
                is_active=True,
            ),
        }



    @staticmethod
    def _validate_relations(
        context,
        relations,
    ):

        animal = relations["animal"]
        male = relations["male"]

        if animal.organization_id != context.organization.id:
            raise ValidationError(
                "La hembra no pertenece a la organización."
            )

        if (
            male
            and male.organization_id != context.organization.id
        ):
            raise ValidationError(
                "El macho no pertenece a la organización."
            )

        if male and animal.id == male.id:
            raise ValidationError(
                "La hembra y el macho no pueden ser el mismo animal."
            )