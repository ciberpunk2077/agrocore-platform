from ninja import Router

from apps.catalogs.api.schemas import FarmTypeSchema
from apps.catalogs.services import CatalogService

router = Router()


@router.get(
    "/farm-types",
    response=list[FarmTypeSchema],
)
def farm_types(request):

    return CatalogService.get_farm_types()