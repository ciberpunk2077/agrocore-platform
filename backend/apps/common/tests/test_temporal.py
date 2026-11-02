from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.common.temporal import (
    TenantTimezoneUnavailable, get_business_timezone,
    get_business_today, get_business_time_snapshot,
)
from apps.common.utils.validators import validate_iana_timezone


class BusinessTemporalTests(SimpleTestCase):
    def context(self, zone="America/Mexico_City", user_zone="UTC"):
        return SimpleNamespace(organization=SimpleNamespace(pk=1, timezone=zone), user=SimpleNamespace(timezone=user_zone))

    def at(self, value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def test_mexico_day_boundaries_and_utc_tenant(self):
        for instant, expected in (
            ("2026-10-05T23:30:00Z", date(2026, 10, 5)),
            ("2026-10-06T00:30:00Z", date(2026, 10, 5)),
            ("2026-10-06T05:59:59Z", date(2026, 10, 5)),
            ("2026-10-06T06:00:00Z", date(2026, 10, 6)),
        ):
            with self.subTest(instant=instant):
                self.assertEqual(get_business_today(self.context(), at=self.at(instant)), expected)
        self.assertEqual(get_business_today(self.context("UTC"), at=self.at("2026-10-06T00:30:00Z")), date(2026, 10, 6))

    def test_user_preference_never_changes_tenant_day(self):
        for user_zone in ("UTC", "Asia/Tokyo", "invalid"):
            self.assertEqual(get_business_today(self.context(user_zone=user_zone), at=self.at("2026-10-06T00:30:00Z")), date(2026, 10, 5))

    def test_validators_and_corrupt_tenant_fail_closed(self):
        for zone in ("", " UTC", "UTC ", "UTC-6", "Not/AZone", None):
            with self.subTest(zone=zone):
                with self.assertRaises(ValidationError):
                    validate_iana_timezone(zone)
                with self.assertRaises(TenantTimezoneUnavailable):
                    get_business_today(self.context(zone), at=self.at("2026-10-06T00:30:00Z"))
        for zone in ("UTC", "America/Mexico_City", "Asia/Tokyo", "Etc/GMT+6"):
            validate_iana_timezone(zone)
            self.assertEqual(get_business_timezone(self.context(zone)).key, zone)

    def test_missing_organization_and_naive_instant(self):
        context = SimpleNamespace(organization=None)
        for helper in (get_business_timezone, get_business_today, get_business_time_snapshot):
            with self.assertRaises(TenantTimezoneUnavailable):
                helper(context)
        for helper in (get_business_today, get_business_time_snapshot):
            with self.assertRaises(ValueError):
                helper(self.context(), at=datetime(2026, 10, 6))

    def test_snapshot_uses_one_now_and_has_maximum_sixty_second_lifetime(self):
        instant = self.at("2026-10-06T00:30:00Z")
        with patch("apps.common.temporal.timezone.now", return_value=instant) as clock:
            snapshot = get_business_time_snapshot(self.context())
        clock.assert_called_once_with()
        self.assertEqual(snapshot, {
            "effective_timezone": "America/Mexico_City", "business_today": date(2026, 10, 5),
            "server_now": instant, "valid_until": instant + timedelta(seconds=60),
        })
        instant = self.at("2026-10-06T05:59:59.500000Z")
        self.assertEqual(get_business_time_snapshot(self.context(), at=instant)["valid_until"], self.at("2026-10-06T06:00:00Z"))

    def test_snapshot_handles_skipped_and_repeated_iana_midnight(self):
        # Sao Paulo skipped midnight at the start of DST in 2018.
        self.assertEqual(get_business_time_snapshot(self.context("America/Sao_Paulo"), at=self.at("2018-11-04T02:59:59Z"))["valid_until"], self.at("2018-11-04T03:00:00Z"))
        # Havana repeats midnight in November: the second midnight is still
        # the same civil day, so it must not fabricate a date change.
        instant = self.at("2026-11-01T04:59:59Z")
        self.assertEqual(get_business_time_snapshot(self.context("America/Havana"), at=instant)["valid_until"], instant + timedelta(seconds=60))
        # Apia skipped an entire civil date in 2011.
        self.assertEqual(get_business_time_snapshot(self.context("Pacific/Apia"), at=self.at("2011-12-30T09:59:59Z"))["valid_until"], self.at("2011-12-30T10:00:00Z"))
