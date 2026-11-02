import sqlite3

from django.db import IntegrityError, transaction

from apps.animals.models import Animal
from apps.catalogs.models import AnimalStatus
from apps.common.exceptions import BirthValidationError
from apps.common.temporal import get_business_today


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
            status=active_status,

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

        try:
            with transaction.atomic():
                calf.save(_birth_business_today=get_business_today(context))
        except IntegrityError as exc:
            if CalfService._is_internal_id_collision(exc):
                raise BirthValidationError(
                    "El identificador interno de la cría ya está reservado en esta organización."
                ) from exc
            raise

        return calf


    @staticmethod
    def _is_internal_id_collision(error):
        cause = error.__cause__
        constraint = getattr(getattr(cause, "diag", None), "constraint_name", None)
        if constraint is not None:
            return constraint == "unique_internal_id_per_organization"
        # Same constraint-identification pattern as Farms/Lots for SQLite.
        return isinstance(cause, sqlite3.IntegrityError) and str(cause) == (
            "UNIQUE constraint failed: animals.organization_id, animals.internal_id"
        )

    @staticmethod
    def _generate_internal_id(organization):
        """
        Genera un identificador interno único para una cría.
        """

        prefix = "CRIA-"

        # Inactive/soft-deleted rows still reserve their internal IDs in the DB.
        reserved_ids = (
            Animal._base_manager
            .filter(
                organization=organization,
                internal_id__startswith=prefix,
            )
            .order_by()
            .values_list("internal_id", flat=True)
        )

        maximum = 0
        for internal_id in reserved_ids:
            # Check Python-side too: backend prefix matching may be case-insensitive.
            if not internal_id.startswith(prefix):
                continue
            suffix = internal_id[len(prefix):]
            if suffix and suffix.isascii() and suffix.isdigit():
                maximum = max(maximum, int(suffix))

        next_number = maximum + 1

        return f"{prefix}{next_number:05d}"
