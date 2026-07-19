from ninja import Router

from . import endpoints


router = Router(
    tags=["Organizations"]
)


router.add_router(
    "",
    endpoints.router,
)