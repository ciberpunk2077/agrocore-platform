from datetime import datetime
from uuid import UUID

from ninja import Schema


class OrganizationSchema(Schema):
    id: UUID
    name: str
    code: str
    slug: str
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime