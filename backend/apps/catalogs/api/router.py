from ninja import Router

from . import endpoints

router = Router(tags=["Catalogs"])

router.add_router(
    "",
    endpoints.router,
)