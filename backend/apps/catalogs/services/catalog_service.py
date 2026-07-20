from apps.catalogs.models import FarmType


class CatalogService:

    @staticmethod
    def get_farm_types():

        return FarmType.objects.filter(
            is_active=True
        ).order_by("name")