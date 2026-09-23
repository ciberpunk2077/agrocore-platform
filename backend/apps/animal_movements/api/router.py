from ninja import Router

from .endpoints import router as movement_router

router = Router()

router.add_router(
    "",
    movement_router,
)