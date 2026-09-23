from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError,
)

from django.db import transaction

from apps.common.exceptions import (
    RelatedObjectNotFound,
)

from apps.births.models import Birth
from apps.pregnancy.models import (
    Pregnancy,
    PregnancyStatus,
)
from apps.animals.models import Animal
from apps.catalogs.models import Gender
from apps.births.services.calf_service import CalfService


class BirthService:

    @staticmethod
    @transaction.atomic
    def create(context, data):

        try:

            pregnancy = Pregnancy.objects.get(
                id=data.pregnancy_id,
                organization=context.organization,
                is_active=True,
            )

            mother = Animal.objects.get(
                id=data.mother_id,
                organization=context.organization,
                is_active=True,
            )

            BirthService._validate_business_rules(
                data,
                pregnancy,
                mother,
            )

            calf = None

            if data.calf_id:

                calf = Animal.objects.get(
                    id=data.calf_id,
                    organization=context.organization, 
                    is_active=True,
                )

                if calf.id == mother.id:
                    raise ValidationError(
                        "La madre no puede ser registrada como su propia cría."
                    )


                if (
                    calf.mother_id is not None
                    and calf.mother_id != mother.id
                ):
                    raise ValidationError(
                        "La cría seleccionada pertenece a otra madre."
                    )


            calf_gender = None

            if data.calf_gender_id:

                calf_gender = Gender.objects.get(
                    id=data.calf_gender_id,
                    is_active=True,
                    organization=context.organization,
                )

            birth = Birth(
                organization=context.organization,
                pregnancy=pregnancy,
                mother=mother,
                calf=calf,
                calf_gender=calf_gender,
                birth_date=data.birth_date,
                birth_weight=data.birth_weight,
                alive=data.alive,
                dystocia=data.dystocia,
                notes=data.notes,
            )

            birth.full_clean()
            birth.save()

            if birth.calf is None:

                calf = CalfService.create_from_birth(
                    context=context,
                    mother=mother,
                    birth=birth,
                )

                birth.calf = calf

                birth.save(
                    update_fields=[
                        "calf",
                    ]
                )

            BirthService._finish_pregnancy(
                pregnancy,
            )

            return birth

        except ObjectDoesNotExist:

            raise RelatedObjectNotFound(
                "Uno de los registros relacionados no existe."
            )


    @staticmethod
    def _validate_business_rules(
        data,
        pregnancy,
        mother,
    ):

        if pregnancy.animal_id != mother.id:
            raise ValidationError("La gestación no pertenece a la madre indicada.")

        if Birth.objects.filter(
            pregnancy=pregnancy,
            is_active=True,
        ).exists():
            raise ValidationError(
                "Esta gestación ya tiene un parto registrado."
            )

       
        if (
            data.birth_weight is not None
            and data.birth_weight <= 0
        ):
            raise ValidationError(
                "El peso al nacimiento debe ser mayor que cero."
            )


    @staticmethod
    def _finish_pregnancy(pregnancy):

        pregnancy.status = PregnancyStatus.FINISHED

        pregnancy.save(
            update_fields=[
                "status",
            ]
        )

