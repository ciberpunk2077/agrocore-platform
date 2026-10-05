from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.animals.models import Animal
from apps.births.models import Birth
from apps.breeding.models import BreedingEvent
from apps.catalogs.models import AnimalStatus, Breed, BreedingType, Gender, Species, WeighingMethod
from apps.common.context.context import RequestContext
from apps.dashboard.selectors import DashboardSelector
from apps.organizations.models import Organization
from apps.pregnancy.models import Pregnancy
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
        clock = patch("django.utils.timezone.localdate", return_value=self.today)
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
