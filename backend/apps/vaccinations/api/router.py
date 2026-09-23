from ninja import Router

from .endpoints import router as vaccination_router

router = Router()

router.add_router(
    "",
    vaccination_router,
)