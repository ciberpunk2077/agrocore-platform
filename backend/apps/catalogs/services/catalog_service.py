from apps.catalogs.models import (
    AnimalStatus,
    Breed,
    BreedingType,
    FarmType,
    Gender,
    MovementType,
    Species,
    WeighingMethod,
)


class CatalogService:

    @staticmethod
    def get_farm_types():

        return FarmType.objects.filter(
            is_active=True,
        ).order_by(
            "name",
        )

    @staticmethod
    def get_species():

        return Species.objects.filter(
            is_active=True,
        ).order_by(
            "name",
        )

    @staticmethod
    def get_breeds(species_id=None):

        queryset = Breed.objects.filter(
            is_active=True,
            species__is_active=True,
        ).select_related(
            "species",
        )

        if species_id is not None:
            queryset = queryset.filter(
                species_id=species_id,
            )

        return queryset.order_by(
            "species__name",
            "name",
        )

    @staticmethod
    def get_genders():

        return Gender.objects.filter(
            is_active=True,
        ).order_by(
            "name",
        )

    @staticmethod
    def get_animal_statuses():

        return AnimalStatus.objects.filter(
            is_active=True,
        ).order_by(
            "name",
        )

    @staticmethod
    def get_movement_types():

        return MovementType.objects.filter(
            is_active=True,
        ).order_by(
            "name",
        )

    @staticmethod
    def get_breeding_types():

        return BreedingType.objects.filter(
            is_active=True,
        ).order_by(
            "name",
        )

    @staticmethod
    def get_weighing_methods():

        return WeighingMethod.objects.filter(
            is_active=True,
        ).order_by(
            "name",
        )