from dataclasses import dataclass

from apps.accounts.models import User, Membership
from apps.organizations.models import Organization


@dataclass
class RequestContext:
    """
    Contexto actual de la petición.
    """

    user: User | None = None

    organization: Organization | None = None

    membership: Membership | None = None