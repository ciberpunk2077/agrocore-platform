from datetime import date, datetime
from uuid import UUID

from ninja import Schema

from apps.accounts.api.schemas import UserSchema


class BusinessTimeSchema(Schema):
    effective_timezone: str
    business_today: date
    server_now: datetime
    valid_until: datetime


class ContextOrganizationSchema(Schema):
    id: UUID
    name: str
    code: str


class ContextMembershipSchema(Schema):
    id: UUID
    is_default: bool


class CurrentContextSchema(Schema):
    user: str
    current_user: UserSchema
    organization: ContextOrganizationSchema | None
    membership: ContextMembershipSchema | None
    role: str | None
    can_read: bool
    can_write: bool
    business_time: BusinessTimeSchema | None
