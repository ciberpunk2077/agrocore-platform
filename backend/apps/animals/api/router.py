from ninja import Router

from . import endpoints

router = Router(
    tags=["Animals"],
)

router.add_router(
    "",
    endpoints.router,
)