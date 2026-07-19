from ninja import Router

from .endpoints import router as endpoints_router

router = Router()

router.add_router("", endpoints_router)