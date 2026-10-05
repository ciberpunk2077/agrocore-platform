from uuid import UUID

from ninja import Router
from ninja.errors import HttpError

from apps.production.api.schemas import (
    ProductionCreateSchema,
    ProductionResponseSchema,
    ProductionUpdateSchema,
)
from apps.production.selectors import ProductionSelector
from apps.production.services import ProductionService


router = Router(tags=["Production"])


@router.get("/", response=list[ProductionResponseSchema], summary="List Production Records")
def list_production(request):
    return ProductionSelector.list(request.context)


@router.get("/history/{animal_id}", response=list[ProductionResponseSchema], summary="Production History")
def production_history(request, animal_id: UUID):
    return ProductionSelector.history(request.context, animal_id)


@router.get("/{record_id}", response=ProductionResponseSchema, summary="Get Production Record")
def get_production(request, record_id: UUID):
    record = ProductionSelector.get_by_id(request.context, record_id)
    if record is None:
        raise HttpError(404, "Registro de producción no encontrado.")
    return record


@router.post("/", response=ProductionResponseSchema, summary="Create Production Record")
def create_production(request, payload: ProductionCreateSchema):
    return ProductionService.create(request.context, payload)


@router.put("/{record_id}", response=ProductionResponseSchema, summary="Update Production Record")
def update_production(request, record_id: UUID, payload: ProductionUpdateSchema):
    record = ProductionSelector.get_by_id(request.context, record_id)
    if record is None:
        raise HttpError(404, "Registro de producción no encontrado.")
    return ProductionService.update(request.context, record, payload)


@router.delete("/{record_id}", summary="Delete Production Record")
def delete_production(request, record_id: UUID):
    record = ProductionSelector.get_by_id(request.context, record_id)
    if record is None:
        raise HttpError(404, "Registro de producción no encontrado.")
    ProductionService.delete(request.context, record)
    return {"success": True}
