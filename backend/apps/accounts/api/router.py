from ninja import Router

from . import endpoints

router = Router(tags=["Authentication"])

router.add_router(
    "",
    endpoints.router,
)