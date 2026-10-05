from ninja import NinjaAPI

from apps.organizations.api.router import router as organizations_router
from apps.common.api.router import router as common_router
from apps.accounts.api.router import router as accounts_router
from apps.catalogs.api.router import router as catalogs_router
from apps.animals.api.router import router as animals_router
from apps.weights.api.router import router as weights_router
from apps.animal_movements.api import router as animal_movements_router
from apps.vaccinations.api import router as vaccinations_router
from apps.timeline.api import router as timeline_router
from apps.dashboard.api import router as dashboard_router
from apps.breeding.api import router as breeding_router
from apps.pregnancy.api import router as pregnancy_router
from apps.births.api import router as births_router
from apps.production.api import router as production_router
from apps.lots.api import router as lots_router
from apps.common.authentication.ninja_auth import JWTBearer
from apps.common.authorization import TenantMembershipAccess
from apps.common.exceptions import BusinessException
from apps.common.api.exception_handlers import business_exception_handler
from apps.farms.api import router as farms_router

api = NinjaAPI(
    title="AgroCore Platform API",
    version="1.0.0",
    description="API oficial de AgroCore Platform",
    auth=JWTBearer(),
)

api.add_exception_handler(
    BusinessException,
    business_exception_handler,
)

api.add_router("/auth", accounts_router,)

api.add_router("/organizations", organizations_router,)

api.add_router("/common", common_router,)

api.add_router("/catalogs", catalogs_router,)

api.add_router("/animals", animals_router, auth=TenantMembershipAccess())

api.add_router("/farms", farms_router, auth=TenantMembershipAccess())

api.add_router("/lots", lots_router, auth=TenantMembershipAccess())

api.add_router("/weights", weights_router, auth=TenantMembershipAccess())

api.add_router("/animal-movements", animal_movements_router, auth=TenantMembershipAccess())

api.add_router("/vaccinations", vaccinations_router, auth=TenantMembershipAccess())

api.add_router("/timeline", timeline_router, auth=TenantMembershipAccess())

api.add_router("/dashboard", dashboard_router, auth=TenantMembershipAccess())

api.add_router("/breeding", breeding_router, auth=TenantMembershipAccess())

api.add_router("/pregnancies", pregnancy_router, auth=TenantMembershipAccess())

api.add_router("/births", births_router, auth=TenantMembershipAccess())

api.add_router("/production", production_router, auth=TenantMembershipAccess())
