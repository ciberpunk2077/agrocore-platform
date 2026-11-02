from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token, create_refresh_token
from apps.animals.models import Animal
from apps.births.api.schemas import BirthCreateSchema
from apps.births.models import Birth
from apps.births.services import BirthService
from apps.breeding.models import BreedingEvent
from apps.catalogs.models import AnimalStatus, Breed, BreedingType, Gender, Species, WeighingMethod
from apps.common.context.context import RequestContext
from apps.common.temporal import TenantTimezoneUnavailable
from apps.dashboard.selectors import DashboardSelector
from apps.organizations.models import Organization
from apps.pregnancy.api.schemas import PregnancyCreateSchema
from apps.pregnancy.models import Pregnancy, PregnancyStatus
from apps.pregnancy.services import PregnancyService
from apps.vaccinations.models import Vaccination
from apps.weights.models import Weight


class DashboardAverageWeightTests(TestCase):
    today = date(2026, 5, 20)

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="DASHBOARD", name="Dashboard")
        cls.other_organization = Organization.objects.create(code="DASHBOARD_OTHER", name="Other dashboard")
        cls.species = Species.objects.create(code="DASHBOARD", name="Dashboard species")
        cls.breed = Breed.objects.create(species=cls.species, code="DASHBOARD", name="Dashboard breed")
        cls.gender = Gender.objects.get(code="F")
        cls.status = AnimalStatus.objects.get(code="ACTIVE")
        cls.method = WeighingMethod.objects.create(code="DASHBOARD", name="Dashboard method")

    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        clock = patch("django.utils.timezone.now", return_value=datetime(
            2026, 5, 20, 18, tzinfo=datetime_timezone.utc,
        ))
        clock.start()
        self.addCleanup(clock.stop)

    def animal(self, internal_id, **changes):
        fields = dict(organization=self.organization, species=self.species,
                      breed=self.breed, gender=self.gender, status=self.status,
                      internal_id=internal_id)
        fields.update(changes)
        return Animal.objects.create(**fields)

    def weight(self, animal, value, days_ago=0, **changes):
        fields = dict(organization=animal.organization, animal=animal,
                      weighing_method=self.method, weight=Decimal(value),
                      date=self.today - timedelta(days=days_ago))
        fields.update(changes)
        return Weight.objects.create(**fields)

    def average(self):
        return DashboardSelector.summary(self.context)["average_weight"]

    def test_single_animal_uses_latest_date_not_insertion_order_or_maximum(self):
        animal = self.animal("A")
        self.weight(animal, "400", days_ago=1)
        self.weight(animal, "500", days_ago=3)
        self.weight(animal, "350", days_ago=2)
        self.assertEqual(self.average(), Decimal("400"))

    def test_multiple_animals_average_only_latest_weights(self):
        a, b = self.animal("A"), self.animal("B")
        for days, value in ((3, "300"), (2, "350"), (1, "400")):
            self.weight(a, value, days)
        self.weight(b, "450", 2)
        self.weight(b, "500", 1)
        self.assertEqual(self.average(), Decimal("450"))

    def test_active_animal_without_weights_does_not_participate(self):
        self.weight(self.animal("A"), "400")
        self.animal("NO_WEIGHTS")
        self.assertEqual(self.average(), Decimal("400"))

    def test_inactive_animal_is_ignored(self):
        self.weight(self.animal("A"), "400")
        self.weight(self.animal("INACTIVE", is_active=False), "900")
        self.assertEqual(self.average(), Decimal("400"))

    def test_deleted_latest_weight_falls_back_to_previous_active_weight(self):
        animal = self.animal("A")
        self.weight(animal, "400", 2)
        latest = self.weight(animal, "500", 1)
        latest.delete()
        self.assertEqual(self.average(), Decimal("400"))

    def test_other_tenant_and_inconsistent_weight_organizations_are_ignored(self):
        animal = self.animal("A")
        foreign = self.animal("OTHER", organization=self.other_organization)
        self.weight(animal, "400", 2)
        self.weight(foreign, "900")
        # Simulate legacy inconsistent rows to protect both tenant boundaries.
        self.weight(foreign, "800", 1, organization=self.organization)
        self.weight(animal, "700", 1, organization=self.other_organization)
        self.assertEqual(self.average(), Decimal("400"))

    def test_no_animals_returns_none(self):
        self.assertIsNone(self.average())

    def test_no_eligible_active_weights_returns_none(self):
        self.animal("NO_WEIGHTS")
        self.weight(self.animal("DELETED_WEIGHT"), "400", is_active=False)
        self.weight(self.animal("INACTIVE", is_active=False), "500")
        self.weight(self.animal("OTHER", organization=self.other_organization), "900")
        self.assertIsNone(self.average())

    def test_summary_other_metrics_and_query_count_are_preserved(self):
        animal = self.animal("A")
        self.weight(animal, "300", 2)
        self.weight(animal, "400", 1)
        self.animal("NO_WEIGHTS")
        self.animal("INACTIVE", is_active=False)
        self.animal("OTHER", organization=self.other_organization)
        breeding_type = BreedingType.objects.create(code="DASHBOARD", name="Dashboard breeding")
        breeding = BreedingEvent.objects.create(organization=self.organization, animal=animal,
                                                breeding_type=breeding_type, date=self.today)
        pregnancy = Pregnancy.objects.create(organization=self.organization, animal=animal,
                                              breeding=breeding, diagnosis_date=self.today,
                                              expected_birth=self.today + timedelta(days=10))
        Birth.objects.create(organization=self.organization, pregnancy=pregnancy, mother=animal,
                             birth_date=self.today, birth_weight=Decimal("35"))
        Vaccination.objects.create(organization=self.organization, animal=animal, vaccine_name="Test",
                                   application_date=self.today - timedelta(days=30),
                                   next_application_date=self.today, dose=Decimal("1"))
        with self.assertNumQueries(7):
            summary = DashboardSelector.summary(self.context)
        self.assertEqual(summary, dict(total_animals=2, active_animals=2, pregnancies=1,
                                      births_this_month=1, upcoming_births=1, vaccinations_due=1,
                                      average_weight=Decimal("400")))
        # More animals must not introduce per-animal queries.
        self.weight(self.animal("B"), "500")
        with self.assertNumQueries(7):
            self.assertEqual(self.average(), Decimal("450"))


class DashboardContractTests(TestCase):
    today = DashboardAverageWeightTests.today
    setUpTestData = classmethod(DashboardAverageWeightTests.setUpTestData.__func__)
    animal = DashboardAverageWeightTests.animal
    weight = DashboardAverageWeightTests.weight

    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        clock = patch("django.utils.timezone.now", return_value=datetime(
            2026, 5, 20, 18, tzinfo=datetime_timezone.utc,
        ))
        clock.start()
        self.addCleanup(clock.stop)
        self.breeding_type = BreedingType.objects.create(code="CONTRACT", name="Contract breeding")
        self.user = User.objects.create_user(email="dashboard-contract@example.com")
        self.membership = Membership.objects.create(
            user=self.user, organization=self.organization,
            role=Membership.Role.VIEWER, is_default=True,
        )
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {create_access_token(self.user)}"}

    def pregnancy(self, days=10, animal=None, organization=None, service=False, **changes):
        organization = organization or self.organization
        animal = animal or self.animal(str(uuid4()), organization=organization)
        breeding = BreedingEvent.objects.create(
            organization=organization, animal=animal, breeding_type=self.breeding_type,
            date=self.today - timedelta(days=100),
        )
        fields = dict(animal_id=animal.pk, breeding_id=breeding.pk,
                      diagnosis_date=self.today - timedelta(days=90),
                      expected_birth=self.today + timedelta(days=days))
        fields.update(changes)
        if service:
            return PregnancyService.create(self.context, PregnancyCreateSchema(**fields))
        return Pregnancy.objects.create(organization=organization, **fields)

    def birth(self, pregnancy=None, **changes):
        pregnancy = pregnancy or self.pregnancy(status=PregnancyStatus.FINISHED)
        fields = dict(organization=pregnancy.organization, pregnancy=pregnancy,
                      mother=pregnancy.animal, birth_date=self.today, birth_weight=Decimal("35"))
        fields.update(changes)
        return Birth.objects.create(**fields)

    def vaccination(self, animal=None, **changes):
        animal = animal or self.animal(str(uuid4()))
        fields = dict(organization=animal.organization, animal=animal, vaccine_name="Test",
                      application_date=self.today - timedelta(days=30),
                      next_application_date=self.today, dose=Decimal("1"))
        fields.update(changes)
        return Vaccination.objects.create(**fields)

    def summary(self):
        return DashboardSelector.summary(self.context)

    def upcoming(self):
        return DashboardSelector.upcoming_births(self.context)

    def test_window_is_inclusive_and_excludes_overdue_and_outside(self):
        rows = [self.pregnancy(days=days) for days in (-1, 0, 30, 31)]
        self.assertEqual(self.summary()["pregnancies"], 4)
        self.assertEqual(self.summary()["upcoming_births"], 2)
        self.assertEqual([row["animal_id"] for row in self.upcoming()],
                         [rows[1].animal_id, rows[2].animal_id])

    def test_finished_aborted_unconfirmed_and_inactive_pregnancies_are_excluded(self):
        eligible = self.pregnancy()
        for changes in (dict(status=PregnancyStatus.FINISHED),
                        dict(status=PregnancyStatus.ABORTED), dict(confirmed=False), dict(is_active=False)):
            self.pregnancy(**changes)
        self.assertEqual(self.summary()["pregnancies"], 1)
        self.assertEqual(self.summary()["upcoming_births"], 1)
        self.assertEqual([row["animal_id"] for row in self.upcoming()], [eligible.animal_id])

    def test_soft_deleted_records_are_excluded(self):
        pregnancy = self.pregnancy()
        birth = self.birth()
        vaccination = self.vaccination()
        for record in (pregnancy, birth, vaccination):
            record.delete()
        summary = self.summary()
        for metric in ("pregnancies", "upcoming_births", "births_this_month", "vaccinations_due"):
            self.assertEqual(summary[metric], 0)
        self.assertEqual(self.upcoming(), [])

    def test_other_tenant_records_are_excluded(self):
        foreign = self.animal("FOREIGN", organization=self.other_organization)
        self.pregnancy(animal=foreign, organization=self.other_organization)
        self.birth(pregnancy=self.pregnancy(organization=self.other_organization,
                                          status=PregnancyStatus.FINISHED))
        self.vaccination(animal=foreign)
        self.weight(foreign, "900")
        self.assertEqual(self.summary(), dict(total_animals=0, active_animals=0, pregnancies=0,
                         births_this_month=0, upcoming_births=0, vaccinations_due=0, average_weight=None))
        self.assertEqual(self.upcoming(), [])

    def test_inconsistent_pregnancy_direct_relations_are_excluded(self):
        foreign = self.animal("FOREIGN", organization=self.other_organization)
        wrong_animal = self.pregnancy()
        wrong_breeding = self.pregnancy()
        # Simulate legacy/imported corruption without changing domain services.
        Pregnancy._base_manager.filter(pk=wrong_animal.pk).update(animal=foreign)
        BreedingEvent._base_manager.filter(pk=wrong_breeding.breeding_id).update(
            organization=self.other_organization,
        )
        self.assertEqual(self.summary()["pregnancies"], 0)
        self.assertEqual(self.summary()["upcoming_births"], 0)
        self.assertEqual(self.upcoming(), [])
        response = self.client.get("/api/dashboard/upcoming-births", **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.assertNotIn(str(foreign.pk), response.content.decode())
        self.assertNotIn("FOREIGN", response.content.decode())

    def test_inconsistent_birth_direct_relations_are_excluded(self):
        foreign = self.animal("FOREIGN", organization=self.other_organization)
        foreign_pregnancy = self.pregnancy(organization=self.other_organization)
        for changes in (dict(mother=foreign), dict(pregnancy=foreign_pregnancy), dict(calf=foreign)):
            with self.subTest(relation=next(iter(changes))):
                birth = self.birth()
                Birth._base_manager.filter(pk=birth.pk).update(**changes)
                self.assertEqual(self.summary()["births_this_month"], 0)
                birth.delete()

    def test_inconsistent_vaccination_animal_is_excluded(self):
        foreign = self.animal("FOREIGN", organization=self.other_organization)
        self.vaccination(animal=foreign, organization=self.organization)
        self.assertEqual(self.summary()["vaccinations_due"], 0)

    def test_historical_inactive_relations_remain_eligible(self):
        pregnancy = self.pregnancy()
        finished = self.pregnancy(status=PregnancyStatus.FINISHED)
        calf = self.animal("CALF")
        self.birth(pregnancy=finished, calf=calf)
        self.vaccination(animal=pregnancy.animal)
        Animal._base_manager.filter(pk__in=[pregnancy.animal_id, finished.animal_id, calf.pk]).update(
            is_active=False,
        )
        BreedingEvent._base_manager.filter(pk__in=[pregnancy.breeding_id, finished.breeding_id]).update(
            is_active=False,
        )
        Pregnancy._base_manager.filter(pk=finished.pk).update(is_active=False)
        self.assertEqual(self.summary(), dict(total_animals=0, active_animals=0, pregnancies=1,
                         births_this_month=1, upcoming_births=1, vaccinations_due=1, average_weight=None))
        self.assertEqual(self.upcoming()[0]["animal_id"], pregnancy.animal_id)

    def test_nullable_or_empty_internal_id_uses_stable_uuid_without_str(self):
        for internal_id in (None, "", "IDENTIFIED"):
            with self.subTest(internal_id=internal_id):
                animal = self.animal(internal_id)
                self.pregnancy(animal=animal)
                with patch.object(Animal, "__str__", side_effect=AssertionError("Unsafe label")):
                    labels = {row["animal_id"]: row["animal"] for row in self.upcoming()}
                self.assertEqual(labels[animal.pk], internal_id or str(animal.pk))
                self.assertEqual(labels, {row["animal_id"]: row["animal"] for row in self.upcoming()})
        response = self.client.get("/api/dashboard/upcoming-births", **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(row["animal"] for row in response.json()))

    def test_queries_remain_seven_for_summary_and_one_for_upcoming(self):
        self.pregnancy()
        self.birth()
        self.vaccination()
        with self.assertNumQueries(7):
            self.summary()
        with self.assertNumQueries(1):
            self.assertEqual(len(self.upcoming()), 1)
        for _ in range(10):
            self.pregnancy()
        with self.assertNumQueries(7):
            self.assertEqual(self.summary()["upcoming_births"], 11)
        with self.assertNumQueries(1):
            self.assertEqual(len(self.upcoming()), 11)

    def test_vaccinations_due_keeps_record_count_null_and_date_semantics(self):
        animal = self.animal("A")
        for days in (-1, 0, 1):
            self.vaccination(animal=animal, next_application_date=self.today + timedelta(days=days))
        self.vaccination(animal=animal, next_application_date=None)
        self.vaccination(animal=animal, is_active=False)
        self.assertEqual(self.summary()["vaccinations_due"], 2)

    def test_inventory_and_average_do_not_confuse_business_status_with_is_active(self):
        other_status = AnimalStatus.objects.create(code="DASH_OTHER", name="Other status")
        active = self.animal("ACTIVE")
        other = self.animal("OTHER", status=other_status)
        self.weight(active, "400")
        self.weight(other, "600")
        self.assertEqual(self.summary()["total_animals"], 2)
        self.assertEqual(self.summary()["active_animals"], 1)
        self.assertEqual(self.summary()["average_weight"], Decimal("500"))

    def test_tenant_day_controls_month_year_and_due_boundaries_in_multiple_zones(self):
        # Same UTC instant, different civil days. Include both sides of each boundary.
        dates = (date(2025, 12, 31), date(2026, 1, 1), date(2026, 5, 31), date(2026, 6, 1))
        pregnancies = []
        for civil in dates:
            pregnancies.append(self.pregnancy(expected_birth=civil))
            self.birth(birth_date=civil)
            self.vaccination(next_application_date=civil)
        scenarios = (
            (datetime(2026, 1, 1, 2, tzinfo=datetime_timezone.utc), "America/Mexico_City", dates[0]),
            (datetime(2026, 1, 1, 2, tzinfo=datetime_timezone.utc), "UTC", dates[1]),
            (datetime(2026, 5, 31, 12, tzinfo=datetime_timezone.utc), "Pacific/Kiritimati", dates[3]),
            (datetime(2026, 6, 1, 2, tzinfo=datetime_timezone.utc), "America/Mexico_City", dates[2]),
            (datetime(2026, 6, 1, 2, tzinfo=datetime_timezone.utc), "UTC", dates[3]),
        )
        for instant, zone, civil in scenarios:
            with self.subTest(instant=instant, zone=zone):
                self.organization.timezone = zone
                self.organization.save(update_fields=["timezone"])
                # A globally active timezone must neither determine nor be changed by Dashboard.
                with timezone.override("Asia/Tokyo"), patch("django.utils.timezone.now", return_value=instant):
                    before = timezone.get_current_timezone_name()
                    summary = self.summary()
                    upcoming = self.upcoming()
                    self.assertEqual(timezone.get_current_timezone_name(), before)
                    self.assertEqual(summary["births_this_month"], sum(
                        (d.year, d.month) == (civil.year, civil.month) for d in dates))
                    self.assertEqual(summary["vaccinations_due"], sum(d <= civil for d in dates))
                    eligible = [p for p in pregnancies if civil <= p.expected_birth <= civil + timedelta(days=30)]
                    self.assertEqual(summary["upcoming_births"], len(eligible))
                    self.assertEqual([row["animal_id"] for row in upcoming], [p.animal_id for p in eligible])
                    for endpoint in ("summary", "upcoming-births"):
                        response = self.client.get(f"/api/dashboard/{endpoint}", **self.headers)
                        self.assertEqual(response.status_code, 200)
                        if endpoint == "summary":
                            self.assertEqual(response.json()["births_this_month"], summary["births_this_month"])
                        else:
                            self.assertEqual([row["expected_birth"] for row in response.json()],
                                             [p.expected_birth.isoformat() for p in eligible])

    def test_civil_midnight_updates_day_sensitive_metrics(self):
        self.pregnancy(days=0)
        self.vaccination(next_application_date=self.today + timedelta(days=1))
        for hour, count, due in ((5, 1, 0), (6, 0, 1)):
            with self.subTest(hour=hour), patch("django.utils.timezone.now", return_value=datetime(
                2026, 5, 21, hour, tzinfo=datetime_timezone.utc,
            )):
                self.assertEqual(self.summary()["upcoming_births"], count)
                self.assertEqual(len(self.upcoming()), count)
                self.assertEqual(self.summary()["vaccinations_due"], due)

    def test_two_tenants_at_same_instant_use_their_own_timezone_not_user_timezone(self):
        instant = datetime(2026, 6, 1, 2, tzinfo=datetime_timezone.utc)
        self.other_organization.timezone = "UTC"
        self.other_organization.save(update_fields=["timezone"])
        User._base_manager.filter(pk=self.user.pk).update(timezone="Pacific/Kiritimati")
        self.birth(birth_date=date(2026, 5, 31))
        self.birth(pregnancy=self.pregnancy(organization=self.other_organization,
                                          status=PregnancyStatus.FINISHED), birth_date=date(2026, 6, 1))
        self.pregnancy(expected_birth=date(2026, 5, 31))
        self.pregnancy(organization=self.other_organization, expected_birth=date(2026, 5, 31))
        with patch("django.utils.timezone.now", return_value=instant):
            mexico = self.summary()
            utc_context = RequestContext(organization=self.other_organization)
            utc = DashboardSelector.summary(utc_context)
            self.assertEqual(mexico["births_this_month"], 1)
            self.assertEqual(utc["births_this_month"], 1)
            self.assertEqual(mexico["upcoming_births"], 1)
            self.assertEqual(utc["upcoming_births"], 0)
            self.assertEqual(len(self.upcoming()), 1)
            self.assertEqual(DashboardSelector.upcoming_births(utc_context), [])
            response = self.client.get("/api/dashboard/summary", **self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["births_this_month"], 1)
            self.assertEqual(response.json()["upcoming_births"], 1)

    def test_invalid_timezone_fails_closed_before_dashboard_queries_and_http_503(self):
        self.organization.timezone = "Invalid/Zone"
        self.organization.save(update_fields=["timezone"])
        for selector in (self.summary, self.upcoming):
            with self.subTest(selector=selector.__name__), self.assertNumQueries(0):
                with self.assertRaises(TenantTimezoneUnavailable):
                    selector()
        for endpoint in ("summary", "upcoming-births"):
            response = self.client.get(f"/api/dashboard/{endpoint}", **self.headers)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["code"], "tenant_timezone_unavailable")
            self.assertEqual(response["Cache-Control"], "no-store")

    def test_missing_organization_has_no_temporal_fallback(self):
        for selector in (DashboardSelector.summary, DashboardSelector.upcoming_births):
            with self.assertNumQueries(0), self.assertRaises(TenantTimezoneUnavailable):
                selector(RequestContext())

    def test_http_populated_contract_for_all_five_roles(self):
        pregnancy = self.pregnancy()
        self.birth(alive=False)
        self.vaccination(animal=pregnancy.animal)
        self.weight(pregnancy.animal, "400")
        for role in Membership.Role.values:
            with self.subTest(role=role):
                Membership._base_manager.filter(pk=self.membership.pk).update(role=role)
                summary = self.client.get("/api/dashboard/summary", **self.headers)
                upcoming = self.client.get("/api/dashboard/upcoming-births", **self.headers)
                self.assertEqual(summary.status_code, 200)
                self.assertEqual(summary.json(), dict(total_animals=2, active_animals=2, pregnancies=1,
                                 births_this_month=1, upcoming_births=1, vaccinations_due=1, average_weight="400"))
                self.assertEqual(upcoming.status_code, 200)
                self.assertEqual(upcoming.json(), [dict(animal_id=str(pregnancy.animal_id),
                                 animal=pregnancy.animal.internal_id, expected_birth=pregnancy.expected_birth.isoformat())])

    def test_http_missing_invalid_and_refresh_tokens_are_401(self):
        for headers in ({}, {"HTTP_AUTHORIZATION": "Bearer invalid"},
                        {"HTTP_AUTHORIZATION": f"Bearer {create_refresh_token(self.user)}"}):
            for endpoint, selector in (("summary", "summary"), ("upcoming-births", "upcoming_births")):
                with self.subTest(endpoint=endpoint, headers_present=bool(headers)), patch.object(
                    DashboardSelector, selector,
                ) as domain:
                    self.assertEqual(self.client.get(f"/api/dashboard/{endpoint}", **headers).status_code, 401)
                    domain.assert_not_called()

    def test_http_inactive_nondefault_membership_and_unknown_role_are_403(self):
        for changes in (dict(is_active=False), dict(is_default=False), dict(role="UNKNOWN")):
            Membership._base_manager.filter(pk=self.membership.pk).update(
                is_active=True, is_default=True, role=Membership.Role.VIEWER,
            )
            Membership._base_manager.filter(pk=self.membership.pk).update(**changes)
            for endpoint, selector in (("summary", "summary"), ("upcoming-births", "upcoming_births")):
                with self.subTest(changes=changes, endpoint=endpoint), patch.object(
                    DashboardSelector, selector,
                ) as domain:
                    self.assertEqual(self.client.get(f"/api/dashboard/{endpoint}", **self.headers).status_code, 403)
                    domain.assert_not_called()

    def test_http_inactive_organization_is_403(self):
        Organization._base_manager.filter(pk=self.organization.pk).update(is_active=False)
        for endpoint in ("summary", "upcoming-births"):
            self.assertEqual(self.client.get(f"/api/dashboard/{endpoint}", **self.headers).status_code, 403)

    def test_http_cannot_select_another_tenant_through_query_parameters(self):
        own = self.pregnancy()
        self.pregnancy(organization=self.other_organization)
        for endpoint in ("summary", "upcoming-births"):
            response = self.client.get(f"/api/dashboard/{endpoint}",
                                       {"organization": str(self.other_organization.pk)}, **self.headers)
            self.assertEqual(response.status_code, 200)
            if endpoint == "summary":
                self.assertEqual(response.json()["total_animals"], 1)
                self.assertEqual(response.json()["pregnancies"], 1)
            else:
                self.assertEqual([row["animal_id"] for row in response.json()], [str(own.animal_id)])

    def test_openapi_preserves_two_get_routes_without_organization_parameters(self):
        from config.api import api
        paths = api.get_openapi_schema()["paths"]
        for endpoint in ("summary", "upcoming-births"):
            operations = paths[f"/api/dashboard/{endpoint}"]
            self.assertEqual(set(operations), {"get"})
            self.assertEqual(operations["get"].get("parameters", []), [])

    def assert_birth_flow(self, alive=True, existing_calf=False):
        pregnancy = self.pregnancy(days=0, service=True)
        calf = self.animal("EXISTING_CALF") if existing_calf else None
        before = self.summary()
        birth = BirthService.create(self.context, BirthCreateSchema(
            pregnancy_id=pregnancy.pk, mother_id=pregnancy.animal_id,
            calf_id=calf.pk if calf else None, calf_gender_id=self.gender.pk,
            birth_date=self.today, birth_weight=Decimal("35"), alive=alive,
        ))
        pregnancy.refresh_from_db()
        after = self.summary()
        self.assertEqual(pregnancy.status, PregnancyStatus.FINISHED)
        self.assertEqual(before["pregnancies"], 1)
        self.assertEqual(before["upcoming_births"], 1)
        self.assertEqual(after["pregnancies"], 0)
        self.assertEqual(after["upcoming_births"], 0)
        self.assertEqual(self.upcoming(), [])
        self.assertEqual(after["births_this_month"], 1)
        increment = int(alive and not existing_calf)
        self.assertEqual(after["total_animals"], before["total_animals"] + increment)
        self.assertEqual(after["active_animals"], before["active_animals"] + increment)
        self.assertIsNone(after["average_weight"])
        self.assertFalse(Weight.objects.exists())
        if calf:
            self.assertEqual(birth.calf_id, calf.pk)
        elif not alive:
            self.assertIsNone(birth.calf_id)
        else:
            self.assertIsNotNone(birth.calf_id)
            self.assertEqual(birth.calf.organization_id, self.organization.pk)
            self.assertEqual(birth.calf.birth_weight, Decimal("35"))
        for endpoint in ("summary", "upcoming-births"):
            response = self.client.get(f"/api/dashboard/{endpoint}", **self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), after if endpoint == "summary" else [])

    def test_real_pregnancy_birth_automatic_calf_updates_dashboard(self):
        self.assert_birth_flow()

    def test_real_dead_birth_counts_without_increasing_inventory(self):
        self.assert_birth_flow(alive=False)

    def test_real_existing_calf_birth_preserves_inventory(self):
        self.assert_birth_flow(existing_calf=True)
