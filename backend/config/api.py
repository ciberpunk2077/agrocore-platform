from ninja import NinjaAPI

from apps.organizations.api.router import router as organizations_router
from apps.common.api.router import router as common_router
from apps.accounts.api.router import router as accounts_router


api = NinjaAPI(
    title="AgroCore Platform API",
    version="1.0.0",
    description="API oficial de AgroCore Platform",
)

api.add_router(
    "/auth",
    accounts_router,
)

api.add_router(
    "/organizations",
    organizations_router,
)

api.add_router(
    "/common",
    common_router,
)