from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from django.test import TestCase

from apps.accounts.models import Membership, User
from apps.accounts.services.jwt import create_access_token
from apps.animals.models import Animal
from apps.animal_movements.models import AnimalMovement
from apps.births.models import Birth
from apps.breeding.models import BreedingEvent
from apps.catalogs.models import (
    AnimalStatus, Breed, BreedingType, FarmType, Gender, MovementType,
    Species, WeighingMethod,
)
from apps.common.context.context import RequestContext
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization
from apps.pregnancy.models import Pregnancy, PregnancyStatus
from apps.timeline.schemas import TimelineEventSchema
from apps.timeline.selectors import TimelineSelector
from apps.vaccinations.models import Vaccination
from apps.weights.models import Weight


class TimelineRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="TIMELINE", name="Timeline")
        cls.other_organization = Organization.objects.create(code="TIMELINE_OTHER", name="Other timeline")
        cls.species = Species.objects.create(code="TIMELINE", name="Timeline species")
        cls.breed = Breed.objects.create(species=cls.species, code="TIMELINE", name="Timeline breed")
        cls.female = Gender.objects.get(code="F")
        cls.male_gender = Gender.objects.get(code="M")
        cls.status = AnimalStatus.objects.create(code="TIMELINE", name="Timeline status")
        cls.method = WeighingMethod.objects.create(code="TIMELINE", name="Timeline scale")
        cls.movement_type, _ = MovementType.objects.get_or_create(code="TRANSFER", defaults={"name": "Transfer"})
        cls.breeding_type = BreedingType.objects.create(code="TIMELINE", name="Timeline breeding")
        farm_type = FarmType.objects.create(code="TIMELINE", name="Timeline farm type")
        cls.locations = {}
        for organization in (cls.organization, cls.other_organization):
            farm = Farm.objects.create(organization=organization, farm_type=farm_type,
                                       code="TIMELINE", name="Timeline farm")
            lots = [Lot.objects.create(organization=organization, farm=farm, code=code, name=code)
                    for code in ("Origin", "Destination")]
            cls.locations[organization.pk] = (farm, *lots)
        cls.animal = cls.make_animal("MOTHER", cls.organization)
        cls.other_animal = cls.make_animal("OTHER", cls.organization)
        cls.foreign_animal = cls.make_animal("FOREIGN", cls.other_organization)
        cls.user = User.objects.create_user(email="timeline@example.com")
        cls.foreign_user = User.objects.create_user(email="foreign-timeline@example.com")
        for user, organization in ((cls.user, cls.organization), (cls.foreign_user, cls.other_organization)):
            Membership.objects.create(user=user, organization=organization,
                                      role=Membership.Role.OWNER, is_default=True)

    @classmethod
    def make_animal(cls, internal_id, organization, **changes):
        farm, origin, _ = cls.locations[organization.pk]
        fields = dict(organization=organization, species=cls.species, breed=cls.breed,
                      gender=cls.female, status=cls.status, internal_id=internal_id,
                      farm=farm, lot=origin, birth_date=date(2020, 1, 1))
        fields.update(changes)
        return Animal.objects.create(**fields)

    def save_event(self, model, **fields):
        event = model(**fields)
        event.full_clean()
        event.save()
        return event

    def simple_event(self, kind, animal=None):
        animal = animal or self.animal
        fields = dict(organization=animal.organization, animal=animal)
        if kind == "weight":
            return self.save_event(Weight, **fields, weighing_method=self.method,
                                   date=date(2024, 3, 1), weight=Decimal("350.00"))
        if kind == "vaccination":
            return self.save_event(Vaccination, **fields, vaccine_name="Timeline vaccine",
                                   application_date=date(2024, 4, 1), dose=Decimal("2.50"),
                                   veterinarian="Timeline vet")
        farm, origin, destination = self.locations[animal.organization_id]
        return self.save_event(AnimalMovement, **fields, movement_type=self.movement_type,
                               origin_farm=farm, destination_farm=farm, origin_lot=origin,
                               destination_lot=destination, date=date(2024, 5, 1))

    def reproduction(self, animal=None, details=True):
        animal = animal or self.animal
        fields = dict(organization=animal.organization, animal=animal)
        male = self.make_animal(f"MALE_{animal.pk}", animal.organization, gender=self.male_gender) if details else None
        breeding = self.save_event(BreedingEvent, **fields, breeding_type=self.breeding_type,
                                   male=male, date=date(2024, 1, 1),
                                   expected_birth=date(2024, 10, 1), technician="Timeline technician" if details else "")
        pregnancy = self.save_event(Pregnancy, **fields, breeding=breeding,
                                    diagnosis_date=date(2024, 2, 1), expected_birth=date(2024, 10, 1),
                                    confirmed=True, status=PregnancyStatus.FINISHED)
        calf = self.make_animal(f"CALF_{animal.pk}", animal.organization,
                                mother=animal, birth_date=date(2024, 10, 1), birth_weight=Decimal("32.50")) if details else None
        birth = self.save_event(Birth, organization=animal.organization, mother=animal,
                                pregnancy=pregnancy, birth_date=date(2024, 10, 1),
                                birth_weight=Decimal("32.50"), calf=calf,
                                calf_gender=self.female if details else None, dystocia=details)
        return dict(breeding=breeding, pregnancy=pregnancy, birth=birth)

    def all_events(self, animal=None):
        events = {kind: self.simple_event(kind, animal) for kind in ("weight", "movement", "vaccination")}
        events.update(self.reproduction(animal))
        return events

    def history(self, animal=None, organization=None):
        return TimelineSelector.history(RequestContext(organization=organization or self.organization),
                                        (animal or self.animal).pk)

    def get_timeline(self, animal_id, user=None):
        return self.client.get(f"/api/timeline/animal/{animal_id}",
                               HTTP_AUTHORIZATION=f"Bearer {create_access_token(user or self.user)}")

    def assert_simple_filter(self, kind, scenario):
        included = self.simple_event(kind)
        excluded = self.simple_event(kind, self.other_animal) if scenario == "other" else None
        if scenario == "deleted":
            included.delete()
            self.assertFalse(type(included)._base_manager.get(pk=included.pk).is_active)
            expected = []
        elif scenario == "inactive":
            included.is_active = False
            included.save()
            expected = []
        else:
            expected = [included.pk]
        history = self.history()
        self.assertEqual([event["id"] for event in history], expected)
        if excluded:
            self.assertNotIn(excluded.pk, expected)
        if history:
            self.assertEqual(history[0]["event_type"], kind)
            descriptions = {
                "weight": f"350.00 kg ({self.method.name})",
                "vaccination": "Timeline vaccine - Dosis: 2.50 - Veterinario: Timeline vet",
                "movement": "Origin → Destination",
            }
            self.assertEqual(history[0]["description"], descriptions[kind])

    def test_empty_timeline(self):
        self.assertEqual(self.history(), [])

    def test_weight_active_and_other_animal(self):
        self.assert_simple_filter("weight", "other")

    def test_weight_soft_deleted(self):
        self.assert_simple_filter("weight", "deleted")

    def test_weight_inactive(self):
        self.assert_simple_filter("weight", "inactive")

    def test_vaccination_active_and_other_animal(self):
        self.assert_simple_filter("vaccination", "other")

    def test_vaccination_soft_deleted(self):
        self.assert_simple_filter("vaccination", "deleted")

    def test_vaccination_inactive(self):
        self.assert_simple_filter("vaccination", "inactive")

    def test_movement_active_and_other_animal(self):
        self.assert_simple_filter("movement", "other")

    def test_movement_soft_deleted(self):
        self.assert_simple_filter("movement", "deleted")

    def test_movement_inactive(self):
        self.assert_simple_filter("movement", "inactive")

    def test_reproduction_descriptions_and_mother_history(self):
        events = self.reproduction()
        history = {event["event_type"]: event for event in self.history()}
        self.assertEqual(set(history), set(events))
        for kind, event in events.items():
            self.assertEqual(history[kind]["id"], event.pk)
        self.assertEqual(history["breeding"]["description"],
                         f"Tipo: {self.breeding_type.name} - Macho: {events['breeding'].male.internal_id}"
                         " - Parto estimado: 2024-10-01 - Técnico: Timeline technician")
        self.assertEqual(history["pregnancy"]["description"],
                         "Estado: Finalizada - Parto estimado: 2024-10-01 - Confirmada")
        self.assertEqual(history["birth"]["description"],
                         f"Cría: {events['birth'].calf.internal_id} - Peso: 32.50 kg"
                         f" - Sexo: {self.female.name} - Parto con distocia")
        self.assertEqual(self.history(events["birth"].calf), [])

    def test_reproduction_optional_details(self):
        self.reproduction(details=False)
        history = {event["event_type"]: event for event in self.history()}
        self.assertEqual(history["birth"]["description"], "Cría: Sin cría registrada - Peso: 32.50 kg")
        self.assertEqual(history["breeding"]["description"], f"Tipo: {self.breeding_type.name} - Parto estimado: 2024-10-01")
        self.assertIn("Confirmada", history["pregnancy"]["description"])

    def test_reproduction_other_animal_is_excluded(self):
        included = self.reproduction()
        self.reproduction(self.other_animal)
        self.assertEqual({event["id"] for event in self.history()}, {event.pk for event in included.values()})

    def test_reproduction_soft_deleted_events_are_excluded(self):
        events = self.reproduction()
        for event in events.values():
            event.delete()
            self.assertFalse(type(event)._base_manager.get(pk=event.pk).is_active)
        self.assertEqual(self.history(), [])

    def test_all_event_types_are_isolated_between_tenants(self):
        local = self.all_events()
        foreign = self.all_events(self.foreign_animal)
        self.assertEqual({event["id"] for event in self.history()}, {event.pk for event in local.values()})
        self.assertEqual(self.history(self.foreign_animal), [])
        self.assertEqual(self.history(organization=self.other_organization), [])
        self.assertEqual({event["id"] for event in self.history(self.foreign_animal, self.other_organization)},
                         {event.pk for event in foreign.values()})

    def test_combined_events_are_sorted_by_date_descending(self):
        events = self.all_events()
        history = self.history()
        self.assertEqual([event["event_type"] for event in history],
                         ["birth", "movement", "vaccination", "weight", "pregnancy", "breeding"])
        self.assertEqual([event["date"] for event in history],
                         [date(2024, month, 1) for month in (10, 5, 4, 3, 2, 1)])
        self.assertEqual({event["id"] for event in history}, {event.pk for event in events.values()})

    def test_api_valid_animal_without_events(self):
        response = self.get_timeline(self.animal.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_api_route_schema_descriptions_and_order(self):
        self.all_events()
        response = self.get_timeline(self.animal.pk)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 6)
        expected = self.history()
        for actual, event in zip(data, expected):
            self.assertEqual(set(actual), {"id", "date", "event_type", "title", "description"})
            self.assertEqual(UUID(actual["id"]), event["id"])
            self.assertEqual(actual["date"], event["date"].isoformat())
            for field in ("event_type", "title", "description"):
                self.assertEqual(actual[field], event[field])
            TimelineEventSchema.model_validate(actual)

    def test_api_invalid_uuid_returns_validation_error(self):
        response = self.get_timeline("not-a-uuid")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"][0]["loc"], ["path", "animal_id"])

    def test_api_foreign_animal_returns_empty_without_leaking_events(self):
        local = self.all_events()
        foreign = self.all_events(self.foreign_animal)
        for user, allowed, denied, events in (
            (self.user, self.animal, self.foreign_animal, local),
            (self.foreign_user, self.foreign_animal, self.animal, foreign),
        ):
            with self.subTest(user=user.email):
                response = self.get_timeline(allowed.pk, user)
                self.assertEqual(response.status_code, 200)
                self.assertEqual({UUID(event["id"]) for event in response.json()}, {event.pk for event in events.values()})
                response = self.get_timeline(denied.pk, user)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])

    def test_api_excludes_other_animal_and_deleted_events(self):
        events = self.all_events()
        self.all_events(self.other_animal)
        for event in events.values():
            event.delete()
        response = self.get_timeline(self.animal.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_api_unknown_valid_uuid_preserves_empty_response(self):
        response = self.get_timeline(uuid4())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
