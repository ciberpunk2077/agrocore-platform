from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone

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

            BreedingService._validate_business_rules(data)

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

        except ValidationError:
            raise BreedingValidationError(
                "Los datos del evento reproductivo son inválidos."
            )

    @staticmethod
    def update(event, context, data):

        try:

            if event.organization_id != context.organization.id:
                raise BreedingValidationError(
                    "El evento reproductivo no pertenece a la organización actual."
                )

            relations = BreedingService._load_relations(
                context,
                data,
            )

            BreedingService._validate_relations(
                context,
                relations,
            )

            BreedingService._validate_business_rules(data)

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

        except ObjectDoesNotExist:
            raise BreedingValidationError(
                "La hembra, el macho o el tipo de reproducción no existen."
            )


        except ValidationError:
            event.refresh_from_db()
            
            raise BreedingValidationError(
                "Los datos del evento reproductivo son inválidos."
            )


    @staticmethod
    def delete(event, context):

        if event.organization_id != context.organization.id:
            raise BreedingValidationError(
                "El evento reproductivo no pertenece a la organización actual."
            )

        return BaseCRUDService.soft_delete(
            event,
        )

    @staticmethod
    def _validate_business_rules(data):
        if data.date > timezone.localdate():
            raise BreedingValidationError(
                "La fecha del evento reproductivo no puede ser futura."
            )

        if data.expected_birth is not None and data.expected_birth <= data.date:
            raise BreedingValidationError(
                "La fecha estimada de parto debe ser posterior a la fecha del evento reproductivo."
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


        if animal.gender.code != "F":
            raise BreedingValidationError(
                "El animal reproductor principal debe ser una hembra."
            )

        if male and male.gender.code != "M":
            raise BreedingValidationError(
                "El animal seleccionado como macho debe ser un macho."
            )


        if animal.organization_id != context.organization.id:
            raise BreedingValidationError(
                "La hembra no pertenece a la organización actual."
            )

        if (
            male
            and male.organization_id != context.organization.id
        ):
            raise BreedingValidationError(
                "El macho no pertenece a la organización actual."
            )

        if male and animal.id == male.id:
            raise BreedingValidationError(
                "La hembra y el macho no pueden ser el mismo animal."
            )
