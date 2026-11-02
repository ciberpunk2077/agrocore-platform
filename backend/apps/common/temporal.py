"""Tenant civil dates. UTC timestamps and Django's active timezone stay unchanged."""
import logging
from datetime import datetime, timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.common.exceptions.base import BusinessException
from apps.common.utils.validators import validate_iana_timezone

logger = logging.getLogger(__name__)


class TenantTimezoneUnavailable(BusinessException):
    default_message = "La fecha operativa de la organización no está disponible."
    status_code = 503
    code = "tenant_timezone_unavailable"


def get_business_timezone(context):
    organization = getattr(context, "organization", None)
    if organization is None:
        raise TenantTimezoneUnavailable()
    try:
        validate_iana_timezone(organization.timezone)
    except ValidationError:
        logger.error("Invalid tenant timezone for organization %s", organization.pk)
        raise TenantTimezoneUnavailable() from None
    return ZoneInfo(organization.timezone)


def _instant(at):
    instant = timezone.now() if at is None else at
    if not isinstance(instant, datetime) or timezone.is_naive(instant):
        raise ValueError("A business time instant must be an aware datetime.")
    return instant.astimezone(datetime_timezone.utc)


def get_business_today(context, *, at=None):
    return _instant(at).astimezone(get_business_timezone(context)).date()


def get_business_time_snapshot(context, *, at=None):
    zone = get_business_timezone(context)
    instant = _instant(at)
    today = instant.astimezone(zone).date()
    valid_until = instant + timedelta(seconds=60)
    # IANA transitions and civil midnight occur on whole UTC seconds. Inspect
    # only our short validity window, including backward/forward date jumps.
    # This avoids assuming a 24-hour day or constructing an imaginary midnight.
    boundary = instant.replace(microsecond=0) + timedelta(seconds=1)
    while boundary <= valid_until:
        if boundary.astimezone(zone).date() != today:
            valid_until = boundary
            break
        boundary += timedelta(seconds=1)
    return {
        "effective_timezone": zone.key,
        "business_today": today,
        "server_now": instant,
        "valid_until": valid_until,
    }
