from django.core.exceptions import  ObjectDoesNotExist, ValidationError

from django.utils import timezone
from django.db import transaction

from apps.common.exceptions import (
    BirthValidationError,
    BusinessException,
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

            if data.calf_id is None and data.calf_gender_id is None:
                raise BusinessException(
                    "Debe indicar el sexo de la crÃ­a para crearla automÃ¡ticamente."
                )

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
                    raise BirthValidationError(
                        "La madre no puede ser registrada como su propia crÃ­a."
                    )


                if (
                    calf.mother_id is not None
                    and calf.mother_id != mother.id
                ):
                    raise BirthValidationError(
                        "La crÃ­a seleccionada pertenece a otra madre."
                    )


            calf_gender = None

            if data.calf_gender_id:

                calf_gender = Gender.objects.get(
                    id=data.calf_gender_id,
                    is_active=True,
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

                try:
                    calf = CalfService.create_from_birth(
                        context=context,
                        mother=mother,
                        birth=birth,
                    )
                except ValidationError as exc:
                    raise BusinessException(
                        "No se pudo crear la crÃ­a: los datos del animal son invÃ¡lidos."
                    ) from exc

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

        if pregnancy.status != PregnancyStatus.ACTIVE:
            raise BirthValidationError(
                "Solo se puede registrar un parto para una gestaciÃ³n activa."
            )

        if pregnancy.animal_id != mother.id:
            raise BirthValidationError(
                "La gestaciÃ³n no pertenece a la madre indicada."
            )

        if Birth.objects.filter(
            pregnancy=pregnancy,
            is_active=True,
        ).exists():
            raise BirthValidationError(
                "Esta gestaciÃ³n ya tiene un parto registrado."
            )

        if data.birth_date < pregnancy.breeding.date:
            raise BirthValidationError(
                "La fecha del parto no puede ser anterior a la reproducciÃ³n."
            )

        if data.birth_date < pregnancy.diagnosis_date:
            raise BirthValidationError(
                "La fecha del parto no puede ser anterior al diagnÃ³stico de gestaciÃ³n."
            )

        if data.birth_date > timezone.localdate():
            raise BirthValidationError(
                "La fecha del parto no puede estar en el futuro."
            )

        if (
            data.birth_weight is not None
            and data.birth_weight <= 0
        ):
            raise BirthValidationError(
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
