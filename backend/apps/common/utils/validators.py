from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError


def validate_iana_timezone(value):
    """Validate an IANA key without silently trimming or accepting offsets."""
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 64:
        raise ValidationError("Introduce una zona horaria IANA válida.", code="invalid_timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationError("Introduce una zona horaria IANA válida.", code="invalid_timezone") from None
