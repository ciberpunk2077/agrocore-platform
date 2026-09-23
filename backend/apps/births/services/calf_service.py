from apps.animals.models import Animal
from apps.catalogs.models import AnimalStatus


class CalfService:

    @staticmethod
    def create_from_birth(
        context,
        mother,
        birth,
    ):
        """
        Crea automáticamente la cría a partir del parto.
        """

        father = birth.pregnancy.breeding.male

        active_status = AnimalStatus.objects.get(
            code="ACTIVE",
        )

        internal_id = CalfService._generate_internal_id(
            context.organization,
        )

        calf = Animal(
            organization=context.organization,

            farm=mother.farm,
            lot=mother.lot,

            species=mother.species,
            breed=mother.breed,

            # gender=mother.gender,
            gender=birth.calf_gender,
            status=mother.status,

            birth_date=birth.birth_date,
            birth_weight=birth.birth_weight,

            mother=mother,
            father=father,

            internal_id=internal_id,

            official_tag="",
            electronic_tag="",
            name="",

            notes="Creado automáticamente desde el registro del parto.",
        )

        calf.full_clean()
        calf.save()

        return calf


    @staticmethod
    def _generate_internal_id(organization):
        """
        Genera un identificador interno único para una cría.
        """

        prefix = "CRIA-"

        last_calf = (
            Animal.objects
            .filter(
                organization=organization,
                internal_id__startswith=prefix,
            )
            .order_by("-internal_id")
            .first()
        )

        if last_calf is None:
            next_number = 1
        else:
            last_number = int(
                last_calf.internal_id.replace(
                    prefix,
                    "",
                )
            )

            next_number = last_number + 1

        return f"{prefix}{next_number:05d}"