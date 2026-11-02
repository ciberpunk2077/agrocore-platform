"""Independent D5 certification against real ORM, selectors and mounted HTTP API."""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as utc
from decimal import Decimal
import importlib
import secrets
import shutil
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.db import connection, transaction
from django.test import Client, TransactionTestCase, override_settings

from apps.accounts.models import User, Membership
from apps.accounts.services.jwt import create_access_token
from apps.animals.models import Animal
from apps.catalogs.models import Species, Breed, Gender, AnimalStatus, FarmType, WeighingMethod, BreedingType, MovementType, ProductionType
from apps.common.context.context import RequestContext
from apps.common.temporal import get_business_today
from apps.dashboard.selectors.dashboard_selector import DashboardSelector
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization
from apps.organizations.demo import d2, d3, d4
from apps.organizations.demo.delivery import EncryptedTestDelivery
from apps.organizations.demo.windows_acl import verify_private


# Explicit mapping to actual selectors and mounted API resource names.
RESOURCES = (
    ('farms', 'farms.Farm', 'farm', 'FarmSelector'),
    ('lots', 'lots.Lot', 'lot', 'LotSelector'),
    ('animals', 'animals.Animal', 'animal', 'AnimalSelector'),
    ('weights', 'weights.Weight', 'weight', 'WeightSelector'),
    ('vaccinations', 'vaccinations.Vaccination', 'vaccination', 'VaccinationSelector'),
    ('animal-movements', 'animal_movements.AnimalMovement', 'animal_movement', 'AnimalMovementSelector'),
    ('breeding', 'breeding.BreedingEvent', 'breeding', 'BreedingSelector'),
    ('pregnancies', 'pregnancy.Pregnancy', 'pregnancy', 'PregnancySelector'),
    ('births', 'births.Birth', 'birth', 'BirthSelector'),
    ('production', 'production.ProductionRecord', 'production', 'ProductionSelector'),
)


@contextmanager
def no_sql_writes():
    """Fail at execution, without ever including SQL parameters or secrets."""
    def inspect(execute, sql, params, many, context):
        verb = sql.lstrip().split(None, 1)[0].upper()
        if verb not in {'SELECT', 'BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE'}:
            raise AssertionError('Unexpected mutating SQL during read-only certification.')
        return execute(sql, params, many, context)
    with connection.execute_wrapper(inspect):
        yield


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class DemoD5Tests(TransactionTestCase):
    def setUp(self):
        clock = patch('django.utils.timezone.now', return_value=datetime(2026, 10, 12, 18, tzinfo=utc.utc))
        clock.start(); self.addCleanup(clock.stop)
        self.protected = Organization.objects.create(name='Rancho los Hermanos', code='PROTECTED')
        self.old_user = User.objects.create_user(email='protected@example.invalid', password=secrets.token_urlsafe(32))
        membership = Membership.objects.create(user=self.old_user, organization=self.protected, role='OWNER', is_default=True)
        context = RequestContext(self.old_user, self.protected, membership)
        self.today = get_business_today(context)
        self.species = Species.objects.create(code='BOV', name='Explicit bovine fixture')
        self.breed = Breed.objects.create(species=self.species, code='HOL', name='Explicit breed fixture')
        for model, code, extra in (
            (Gender, 'F', {}), (Gender, 'M', {}), (AnimalStatus, 'ACTIVE', {}), (AnimalStatus, 'SOLD', {}),
            (FarmType, 'RANCH', {}), (MovementType, 'TRANSFER', {}), (MovementType, 'SALE', {}),
            (ProductionType, 'MILK', {'default_unit': 'L'}), (WeighingMethod, 'SCALE', {}), (BreedingType, 'NAT', {}),
        ):
            model.objects.get_or_create(code=code, defaults={'name': code, **extra})
        farm = Farm.objects.create(organization=self.protected, farm_type=FarmType.objects.get(code='RANCH'), code='OLD-F', name='Protected farm')
        lot = Lot.objects.create(organization=self.protected, farm=farm, code='OLD-L', name='Protected lot', capacity=20)
        other_lot = Lot.objects.create(organization=self.protected, farm=farm, code='OLD-L2', name='Protected destination', capacity=20)
        def animal(identifier, sex):
            return Animal.objects.create(organization=self.protected, farm=farm, lot=lot, species=self.species, breed=self.breed,
                gender=Gender.objects.get(code=sex), status=AnimalStatus.objects.get(code='ACTIVE'), internal_id=identifier,
                birth_date=self.today - timedelta(days=1800))
        mother, male, moving = animal('OLD-MOTHER', 'F'), animal('OLD-MALE', 'M'), animal('OLD-MOVING', 'M')
        # Independent protected graph created via real domain services before D2.
        self._service('weights', 'WeightService').create(context, self._schema('weights', 'WeightCreateSchema')(
            animal_id=mother.pk, weighing_method_id=WeighingMethod.objects.get(code='SCALE').pk,
            date=self.today - timedelta(days=10), weight=Decimal('123.45')))
        self._service('vaccinations', 'VaccinationService').create(context, self._schema('vaccinations', 'VaccinationCreateSchema')(
            animal_id=mother.pk, vaccine_name='Protected fixture', application_date=self.today - timedelta(days=20), dose=Decimal('1.00')))
        event = self._service('breeding', 'BreedingService').create(context, self._schema('breeding', 'BreedingCreateSchema')(
            animal_id=mother.pk, male_id=male.pk, breeding_type_id=BreedingType.objects.get(code='NAT').pk,
            date=self.today - timedelta(days=280), expected_birth=self.today))
        pregnancy = self._service('pregnancy', 'PregnancyService').create(context, self._schema('pregnancy', 'PregnancyCreateSchema')(
            animal_id=mother.pk, breeding_id=event.pk, diagnosis_date=self.today - timedelta(days=200), expected_birth=self.today, confirmed=True))
        self._service('births', 'BirthService').create(context, self._schema('births', 'BirthCreateSchema')(
            pregnancy_id=pregnancy.pk, mother_id=mother.pk, calf_gender_id=Gender.objects.get(code='F').pk,
            birth_date=self.today, birth_weight=Decimal('30.00'), alive=True))
        self._service('production', 'ProductionService').create(context, self._schema('production', 'ProductionCreateSchema')(
            animal_id=mother.pk, production_type_id=ProductionType.objects.get(code='MILK').pk,
            recorded_at=datetime(2026, 10, 12, 15, tzinfo=utc.utc), quantity=Decimal('9.125')))
        self._service('animal_movements', 'AnimalMovementService').create(context, self._schema('animal_movements', 'AnimalMovementCreateSchema')(
            animal_id=moving.pk, movement_type_id=MovementType.objects.get(code='TRANSFER').pk,
            origin_farm_id=farm.pk, origin_lot_id=lot.pk, destination_farm_id=farm.pk, destination_lot_id=other_lot.pk,
            date=self.today - timedelta(days=1)))
        # Preexisting El Roble is independent of the new RED01 dataset and must never be adopted.
        self.existing_roble = Organization.objects.create(name='Rancho El Roble', code='RER')
        self.existing_roble_user = User.objects.create_user(email='existing.roble@example.invalid', password=secrets.token_urlsafe(32))
        Membership.objects.create(user=self.existing_roble_user, organization=self.existing_roble, role='OWNER', is_default=True)
        roble_farm = Farm.objects.create(organization=self.existing_roble, farm_type=FarmType.objects.get(code='RANCH'), code='RER-F', name='Existing Roble farm')
        roble_lot = Lot.objects.create(organization=self.existing_roble, farm=roble_farm, code='RER-L', name='Existing Roble lot', capacity=20)
        Animal.objects.create(organization=self.existing_roble, farm=roble_farm, lot=roble_lot, species=self.species,
            breed=self.breed, gender=Gender.objects.get(code='F'), status=AnimalStatus.objects.get(code='ACTIVE'),
            internal_id='RER-A', birth_date=self.today - timedelta(days=1800))
        self.protected_before = d4._snapshot()
        self.key = secrets.token_bytes(32)
        deliveries = []
        for _ in range(3):
            directory = settings.DEMO_D2_TEST_ROOT / f'delivery-{uuid4().hex}'
            directory.mkdir(); self.addCleanup(shutil.rmtree, directory)
            deliveries.append(EncryptedTestDelivery(directory, encryption_key=secrets.token_bytes(32)))
        self.d2, self.d3, self.delivery = deliveries
        self.recoveries = []
        self._run_phase(lambda: d2.create_d2(self.protected.pk, self.d2, signing_key=self.key), self.d2)
        self._run_phase(lambda: d3.create_d3(self.protected.pk, self.d2, self.d3, signing_key=self.key,
            species_code='BOV', breed_code='HOL'), self.d3)
        self.org_ids = self.d2.load()['receipt']['payload']['inventory']['organizations']['ids']
        self.before_d4 = d4._snapshot()
        self._run_phase(self.create, self.delivery)
        self.organizations = [Organization.objects.get(code=row[1]) for row in d4.PLAN]

    def _run_phase(self, create, delivery):
        if self._testMethodName == 'test_full_chain_publication_recovery_without_any_reseed':
            with patch.object(delivery, 'publish', side_effect=OSError('simulated publication failure')):
                with self.assertRaises(d2.DeliveryPending): create()
            pending = delivery.pending.read_bytes()
            before = d4._snapshot()
            with no_sql_writes(), patch('apps.organizations.demo.d2.secrets.token_urlsafe') as generate:
                create()
                generate.assert_not_called()
            self.assertEqual(delivery.final.read_bytes(), pending)
            self.assertEqual(d4._snapshot(), before)
            self.recoveries.append(delivery)
        else:
            create()
        # Each stage must also recognize repetition before the following stage advances its inventory.
        with no_sql_writes(), patch.object(delivery, 'stage') as stage:
            create(); stage.assert_not_called()

    @staticmethod
    def _service(app, name):
        stem = {'WeightService': 'weight', 'VaccinationService': 'vaccination', 'BreedingService': 'breeding',
            'PregnancyService': 'pregnancy', 'BirthService': 'birth', 'ProductionService': 'production',
            'AnimalMovementService': 'animal_movement'}[name]
        return getattr(importlib.import_module(f'apps.{app}.services.{stem}_service'), name)

    @staticmethod
    def _schema(app, name):
        return getattr(importlib.import_module(f'apps.{app}.api.schemas'), name)

    def create(self, **options):
        return d4.create_d4(self.protected.pk, self.d2, self.d3, self.delivery, signing_key=self.key,
            species_code='BOV', breed_code='HOL', weighing_method_code='SCALE', breeding_type_code='NAT', **options)

    def session(self, organization, role='OWNER', *, login=False):
        membership = Membership.objects.filter(organization=organization, role=role).select_related('user').first()
        context = RequestContext(membership.user, organization, membership)
        client = Client()
        if login:
            entry = next(row for row in self.d2.load()['credentials'] if row['user_uuid'] == str(membership.user.pk))
            response = client.post('/api/auth/login', data={'email': entry['email'], 'password': entry['password']}, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            token = response.json()['access']
        else:
            token = create_access_token(membership.user)
        client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        return context, client

    def model_rows(self, label, org):
        return apps.get_model(label).objects.filter(organization=org)

    def test_exact_counts_quotas_reservations_and_memberships(self):
        encino = self.organizations[0]
        self.assertEqual((encino.name, encino.code, encino.slug), ('Rancho El Encino Demo', 'RED01', 'rancho-el-encino-demo'))
        self.assertEqual(set(Membership.objects.filter(organization=encino).values_list('user__email', flat=True)),
            {f'red01.{index:02d}@demo.example.com' for index in range(1, 6)})
        self.assertEqual(Organization.objects.filter(pk__in=self.org_ids).count(), 5)
        memberships = Membership.objects.filter(organization_id__in=self.org_ids)
        self.assertEqual(memberships.count(), 30)
        self.assertEqual(User.objects.filter(memberships__organization_id__in=self.org_ids).distinct().count(), 30)
        for index, org in enumerate(self.organizations):
            plan = d4.PLAN[index]; weights, vaccines, sales, existing, upcoming, production = d4.QUOTAS[index]
            births = d3.RESERVES[index] + existing + 1
            expected = [plan[3], plan[4], plan[5], weights, vaccines, sales + 1, births + upcoming + 2, births + upcoming + 2, births, production]
            self.assertEqual([self.model_rows(label, org).count() for _, label, _, _ in RESOURCES], expected)
            roles = memberships.filter(organization=org)
            self.assertEqual(Counter(roles.values_list('role', flat=True)), Counter(d2.ROLES[index]))
            for membership in roles.select_related('user'):
                self.assertEqual(Membership._base_manager.filter(user=membership.user).count(), 1)
                self.assertTrue(membership.is_default)
                self.assertFalse(membership.user.is_staff or membership.user.is_superuser)
            reservation = next(row for row in self.d3.load()['receipt']['payload']['reservations']
                if row['organization_uuid'] == str(org.pk))
            self.assertEqual(len(reservation['mother_uuids']), d3.RESERVES[index])
        self.assertEqual(len(self.delivery.load()['receipt']['payload']['automatic_calf_uuids']), 32)

    def test_existing_roble_not_adopted_and_all_protected_rows_unchanged(self):
        self.assertNotIn(str(self.existing_roble.pk), self.org_ids)
        after = d4._snapshot()
        for label, rows in self.protected_before.items():
            for identifier, row in rows.items():
                self.assertEqual(after[label][identifier], row, label)
        self.assertEqual(Organization.objects.filter(name='Rancho El Roble', code='RER', slug='rancho-el-roble').count(), 1)
        self.assertEqual(Membership.objects.filter(user=self.existing_roble_user).count(), 1)
        self.assertFalse(Membership.objects.filter(user=self.existing_roble_user, organization_id__in=self.org_ids).exists())

    def test_real_selectors_isolate_lists_details_histories_and_timeline(self):
        from apps.timeline.selectors import TimelineSelector
        for index, org in enumerate(self.organizations):
            context, _ = self.session(org)
            foreign = self.organizations[(index + 1) % 5]
            foreign_animal = Animal.objects.filter(organization=foreign).first()
            for _, label, stem, name in RESOURCES:
                app = label.split('.')[0]
                selector = getattr(importlib.import_module(f'apps.{app}.selectors.{stem}_selector'), name)
                own_ids = set(self.model_rows(label, org).values_list('pk', flat=True))
                self.assertEqual({row.pk for row in selector.list(context)}, own_ids)
                own = self.model_rows(label, org).first()
                if own:
                    self.assertEqual(selector.get_by_id(context, own.pk).pk, own.pk)
                other = self.model_rows(label, foreign).first()
                if other:
                    self.assertIsNone(selector.get_by_id(context, other.pk))
                if hasattr(selector, 'history'):
                    self.assertEqual(list(selector.history(context, foreign_animal.pk)), [])
            self.assertEqual(TimelineSelector.history(context, foreign_animal.pk), [])
            animal = Animal.objects.filter(organization=org, weights__isnull=False).first()
            if animal:
                self.assertTrue(TimelineSelector.history(context, animal.pk))

    def test_real_http_login_accepts_required_demo_credentials(self):
        entries = self.d2.load()['credentials']
        self.assertEqual(len(entries), 30)
        with no_sql_writes():
            for entry in entries:
                client = Client()
                response = client.post('/api/auth/login', data={'email': entry['email'], 'password': entry['password']}, content_type='application/json')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['user']['id'], entry['user_uuid'])
                client.defaults['HTTP_AUTHORIZATION'] = f"Bearer {response.json()['access']}"
                current = client.get('/api/common/context')
                self.assertEqual(current.status_code, 200)
                data = current.json()
                self.assertEqual(data['current_user']['id'], entry['user_uuid'])
                self.assertEqual(data['current_user']['email'], entry['email'])
                self.assertEqual(data['organization']['id'], entry['organization_uuid'])
                self.assertEqual(data['membership']['id'], entry['membership_uuid'])
                self.assertEqual(data['role'], entry['role'])
                self.assertTrue(data['can_read'])
                self.assertEqual(data['can_write'], entry['role'] != 'VIEWER')
                self.assertEqual(data['business_time']['business_today'], self.today.isoformat())

    def test_http_independent_sessions_lists_and_foreign_details(self):
        sessions = [self.session(org, login=True) for org in self.organizations]
        with no_sql_writes():
            for index, (context, client) in enumerate(sessions):
                org = context.organization; foreign = self.organizations[(index + 1) % 5]
                summary = client.get('/api/dashboard/summary')
                self.assertEqual(summary.status_code, 200)
                for field, value in DashboardSelector.summary(context).items():
                    if field == 'average_weight' and value is not None:
                        self.assertAlmostEqual(Decimal(str(summary.json()[field])), value, places=6)
                    else:
                        self.assertEqual(summary.json()[field], value)
                agenda = client.get('/api/dashboard/upcoming-births')
                self.assertEqual(agenda.status_code, 200)
                self.assertEqual(agenda.json(), [{key: str(value) for key, value in row.items()}
                    for row in DashboardSelector.upcoming_births(context)])
                for route, label, _, _ in RESOURCES:
                    response = client.get(f'/api/{route}/')
                    self.assertEqual(response.status_code, 200, route)
                    self.assertEqual({row['id'] for row in response.json()}, {str(value) for value in self.model_rows(label, org).values_list('pk', flat=True)}, route)
                    own = self.model_rows(label, org).first()
                    if own:
                        self.assertEqual(client.get(f'/api/{route}/{own.pk}').status_code, 200, route)
                    other = self.model_rows(label, foreign).first()
                    if other:
                        self.assertEqual(client.get(f'/api/{route}/{other.pk}').status_code, 404, route)
                foreign_animal = Animal.objects.filter(organization=foreign).first()
                response = client.get(f'/api/timeline/animal/{foreign_animal.pk}')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])
                weighted = Animal.objects.filter(organization=org, weights__isnull=False).first()
                if weighted:
                    self.assertTrue(client.get(f'/api/timeline/animal/{weighted.pk}').json())

    def test_http_history_endpoints_do_not_leak_foreign_animals(self):
        paths = ('weights/animal/{}/history', 'vaccinations/animal/{}/history', 'animal-movements/animal/{}/history',
            'breeding/animal/{}/history', 'pregnancies/animal/{}/history', 'births/animal/{}/history', 'production/history/{}')
        for index, org in enumerate(self.organizations):
            _, client = self.session(org)
            foreign = Animal.objects.filter(organization=self.organizations[(index + 1) % 5]).first()
            for path in paths:
                response = client.get('/api/' + path.format(foreign.pk))
                self.assertEqual(response.status_code, 200, path)
                self.assertEqual(response.json(), [], path)

    def test_all_real_roles_read_and_http_write_policy(self):
        org = self.organizations[0]
        farm_type = str(FarmType.objects.get(code='RANCH').pk)
        for role in d2.ROLES[0]:
            _, client = self.session(org, role, login=True)
            for route, _, _, _ in RESOURCES:
                self.assertEqual(client.get(f'/api/{route}/').status_code, 200, (role, route))
            payload = {'name': f'HTTP permission {role}', 'code': f'HTTP-{role}', 'farm_type_id': farm_type}
            if role == 'VIEWER':
                with no_sql_writes():
                    self.assertEqual(client.post('/api/farms/', data=payload, content_type='application/json').status_code, 403)
                    own = Farm.objects.filter(organization=org).first()
                    self.assertEqual(client.put(f'/api/farms/{own.pk}', data=payload, content_type='application/json').status_code, 403)
                    self.assertEqual(client.delete(f'/api/farms/{own.pk}').status_code, 403)
                    for route, _, _, _ in RESOURCES:
                        self.assertEqual(client.post(f'/api/{route}/', data={}, content_type='application/json').status_code, 403, route)
            else:
                response = client.post('/api/farms/', data=payload, content_type='application/json')
                self.assertEqual(response.status_code, 200, role)
                self.assertEqual(Farm.objects.get(pk=response.json()['id']).organization_id, org.pk)

    def test_dashboard_real_selectors_and_http_match_per_tenant(self):
        summaries = []
        for index, org in enumerate(self.organizations):
            context, client = self.session(org, 'VIEWER')
            summary = DashboardSelector.summary(context); summaries.append(summary['total_animals'])
            weights, _, sales, existing, inside, _ = d4.QUOTAS[index]
            self.assertEqual(summary['total_animals'], d4.PLAN[index][5])
            self.assertEqual(summary['active_animals'], summary['total_animals'] - sales)
            self.assertEqual(summary['upcoming_births'], inside)
            self.assertEqual(summary['births_this_month'], d3.RESERVES[index] + existing + 1)
            due = self.model_rows('vaccinations.Vaccination', org).filter(next_application_date__lte=self.today).count()
            self.assertEqual(summary['vaccinations_due'], due)
            http = client.get('/api/dashboard/summary')
            self.assertEqual(http.status_code, 200)
            for field, value in summary.items():
                if field != 'average_weight': self.assertEqual(http.json()[field], value)
            agenda = client.get('/api/dashboard/upcoming-births')
            self.assertEqual(agenda.status_code, 200)
            self.assertEqual(len(agenda.json()), inside)
            dates = {row['expected_birth'] for row in agenda.json()}
            if inside:
                self.assertIn(self.today.isoformat(), dates)
                self.assertIn((self.today + timedelta(days=30)).isoformat(), dates)
            self.assertNotIn((self.today + timedelta(days=31)).isoformat(), dates)
            if weights:
                expected = Decimal(420 + index * 25) + Decimal(3 * (weights // 2 - 1)) / 2
                self.assertAlmostEqual(summary['average_weight'], expected, places=6)
                self.assertAlmostEqual(Decimal(str(http.json()['average_weight'])), expected, places=6)
            else:
                self.assertIsNone(summary['average_weight']); self.assertIsNone(http.json()['average_weight'])
                self.assertEqual(agenda.json(), [])
            business = client.get('/api/common/context')
            self.assertEqual(business.status_code, 200)
            self.assertEqual(business.json()['business_time']['business_today'], self.today.isoformat())
        self.assertEqual(len(set(summaries)), 5)

    def test_business_day_rollover_moves_inclusive_forecast_window(self):
        context, client = self.session(self.organizations[0])
        with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 13, 1, tzinfo=utc.utc)):
            self.assertEqual(get_business_today(context), self.today)
            self.assertEqual(DashboardSelector.summary(context)['upcoming_births'], 2)
        with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 13, 18, tzinfo=utc.utc)):
            dates = {row['expected_birth'] for row in DashboardSelector.upcoming_births(context)}
            self.assertNotIn(self.today, dates)
            self.assertIn(self.today + timedelta(days=31), dates)
            self.assertEqual(client.get('/api/common/context').json()['business_time']['business_today'], '2026-10-13')

    def test_empty_fixture_returns_real_zero_and_null_values(self):
        empty = Organization.objects.create(code='EMPTY-PROTECTED', name='Independent empty fixture')
        context = RequestContext(organization=empty)
        with no_sql_writes():
            summary = DashboardSelector.summary(context)
            self.assertIsNone(summary.pop('average_weight'))
            self.assertEqual(set(summary.values()), {0})
            self.assertEqual(DashboardSelector.upcoming_births(context), [])

    def test_full_chain_publication_recovery_without_any_reseed(self):
        self.assertEqual(len(self.recoveries), 3)
        self.assertEqual(len(self.d2.load()['credentials']), 30)
        self.assertEqual(self.create()['state'], 'recognized-D4')

    def test_domain_graph_integrity_and_protected_snapshot_all_phases(self):
        after = d4._snapshot()
        for label, rows in self.protected_before.items():
            for identifier, row in rows.items():
                self.assertEqual(after[label][identifier], row, label)
        from apps.weights.selectors.weight_selector import WeightSelector
        for org in self.organizations:
            context, _ = self.session(org)
            animals = list(self.model_rows('animals.Animal', org))
            for animal in animals:
                self.assertEqual(animal.breed.species_id, animal.species_id)
                self.assertLessEqual(animal.birth_date, self.today)
                for parent, sex in ((animal.mother, 'F'), (animal.father, 'M')):
                    if parent:
                        self.assertEqual(parent.organization_id, org.pk)
                        self.assertEqual(parent.gender.code, sex)
                        self.assertLess(parent.birth_date, animal.birth_date)
                if animal.status.code == 'SOLD':
                    self.assertIsNone(animal.farm_id); self.assertIsNone(animal.lot_id)
                else:
                    self.assertEqual(animal.lot.organization_id, org.pk)
                    self.assertEqual(animal.lot.farm_id, animal.farm_id)
                latest = self.model_rows('weights.Weight', org).filter(animal=animal).order_by('-date').first()
                selected = WeightSelector.last_weight(context, animal.pk)
                self.assertEqual(selected.pk if selected else None, latest.pk if latest else None)
            for lot in self.model_rows('lots.Lot', org):
                self.assertLessEqual(Animal.objects.filter(lot=lot).count(), lot.capacity)
            for birth in self.model_rows('births.Birth', org).select_related('pregnancy__breeding', 'calf'):
                pregnancy = birth.pregnancy
                self.assertEqual(pregnancy.status, 'FINISHED')
                self.assertEqual(pregnancy.animal_id, birth.mother_id)
                self.assertLessEqual(pregnancy.breeding.date, pregnancy.diagnosis_date)
                self.assertLessEqual(pregnancy.diagnosis_date, birth.birth_date)
                if birth.calf:
                    self.assertEqual(birth.calf.organization_id, org.pk)
                    self.assertEqual(birth.calf.mother_id, birth.mother_id)
                    self.assertEqual(birth.calf.father_id, pregnancy.breeding.male_id)
                    self.assertEqual(birth.calf.birth_date, birth.birth_date)
            self.assertEqual(self.model_rows('pregnancy.Pregnancy', org).filter(status='ABORTED').count(), 1)
            for row in self.model_rows('production.ProductionRecord', org):
                self.assertEqual(row.unit, row.production_type.default_unit)
                self.assertEqual(row.unit, 'L')
                self.assertGreater(row.quantity, 0)
        # Validate every local tenant FK, including movement origin/destination and calf genealogy.
        for _, label, _, _ in RESOURCES:
            for row in apps.get_model(label).objects.filter(organization_id__in=self.org_ids):
                for field in row._meta.fields:
                    if field.is_relation and field.name != 'organization':
                        related = getattr(row, field.name)
                        if related is not None and hasattr(related, 'organization_id'):
                            self.assertEqual(related.organization_id, row.organization_id, (label, field.name))

    def test_recognized_repeat_and_dry_run_execute_zero_mutating_sql(self):
        before = d4._snapshot()
        files = [item.final.read_bytes() for item in (self.d2, self.d3, self.delivery)]
        with no_sql_writes(), patch('apps.organizations.demo.d2.secrets.token_urlsafe') as generate, patch.object(self.delivery, 'stage') as stage:
            self.assertEqual(self.create()['state'], 'recognized-D4')
            self.assertEqual(self.create(dry_run=True)['state'], 'recognized-D4')
            generate.assert_not_called(); stage.assert_not_called()
        self.assertEqual(d4._snapshot(), before)
        self.assertEqual([item.final.read_bytes() for item in (self.d2, self.d3, self.delivery)], files)

    def test_dataset_tampering_is_rejected_without_repair(self):
        org = self.organizations[0]
        foreign = Animal.objects.filter(organization=self.organizations[1]).first()
        candidates = (
            ('weights.Weight', {'animal_id': foreign.pk}),
            ('weights.Weight', {'id': uuid4()}),
            ('weights.Weight', None),
            ('animals.Animal', {'status_id': AnimalStatus.objects.get(code='SOLD').pk}),
            ('animals.Animal', {'lot_id': Lot.objects.filter(organization=self.organizations[1]).first().pk}),
            ('organizations.Organization', {'description': ''}),
            ('pregnancy.Pregnancy', {'is_active': False}),
        )
        parent2, parent3, bundle = self.d2.load(), self.d3.load(), self.delivery.load()
        for label, changes in candidates:
            with transaction.atomic():
                model = apps.get_model(label)
                row = org if label.startswith('organizations.') else model.objects.filter(organization=org).first()
                if changes is None:
                    model._base_manager.filter(pk=row.pk).delete()
                else:
                    model._base_manager.filter(pk=row.pk).update(**changes)
                before = d4._snapshot()
                # Internal writers reject outer transactions first; test the actual verifier independently.
                with no_sql_writes(), self.assertRaises(d2.D2Error):
                    d2._verify(parent2, self.key, self.protected)
                    d4._verify_d4(bundle, parent2, parent3, self.key, self.org_ids,
                        d4._catalogs('BOV', 'HOL', 'SCALE', 'NAT'))
                self.assertEqual(d4._snapshot(), before)
                transaction.set_rollback(True)

    def test_encryption_acl_keys_and_fail_closed_access_checks(self):
        for delivery in (self.d2, self.d3, self.delivery):
            verify_private(delivery.directory); verify_private(delivery.final)
            self.assertEqual(len(list(delivery.directory.iterdir())), 1)
        from cryptography.fernet import InvalidToken
        import base64
        from cryptography.fernet import Fernet
        with self.assertRaises(InvalidToken):
            Fernet(base64.urlsafe_b64encode(secrets.token_bytes(32))).decrypt(self.d2.final.read_bytes())
        credentials = self.d2.load()['credentials']
        ciphertext = self.d2.final.read_bytes()
        for row in credentials:
            self.assertNotIn(row['password'].encode(), ciphertext)
        before = d4._snapshot()
        with patch('apps.organizations.demo.delivery.verify_private', side_effect=d2.D2Error('ACL rejected')):
            with self.assertRaises(d4.D4Error): self.create()
        self.assertEqual(d4._snapshot(), before)

    def test_manifest_uuid_stage_and_signature_tampering_rejected(self):
        from copy import deepcopy
        parent2, parent3, original = self.d2.load(), self.d3.load(), self.delivery.load()
        catalogs = d4._catalogs('BOV', 'HOL', 'SCALE', 'NAT')
        for alteration in ('uuid', 'stage', 'signature', 'partial'):
            bundle = deepcopy(original)
            if alteration == 'signature':
                bundle['receipt']['signature'] = '0' * 64
            else:
                payload = bundle['receipt']['payload']
                if alteration == 'uuid': payload['inventory']['animals.Animal']['rows'][0]['id'] = str(uuid4())
                if alteration == 'stage': payload['stage'] = 'unknown'
                if alteration == 'partial': payload['inventory'].pop('weights.Weight')
                bundle['receipt']['signature'] = d2._signature(payload, self.key)
            with no_sql_writes(), self.assertRaises(d4.D4Error):
                d4._verify_d4(bundle, parent2, parent3, self.key, self.org_ids, catalogs)

    def test_altered_real_windows_acl_is_rejected(self):
        import ctypes
        from apps.organizations.demo.windows_acl import _api, _kernel, restrict_directory
        api = _api(); descriptor = ctypes.c_void_p()
        self.assertTrue(api.ConvertStringSecurityDescriptorToSecurityDescriptorW('D:P(A;OICI;FA;;;WD)', 1, ctypes.byref(descriptor), None))
        try:
            self.assertTrue(api.SetFileSecurityW(str(self.delivery.directory), 0x80000004, descriptor))
            with self.assertRaises(d2.D2Error): verify_private(self.delivery.directory)
            with no_sql_writes(), self.assertRaises(d4.D4Error): self.create()
        finally:
            _kernel().LocalFree(descriptor)
            restrict_directory(self.delivery.directory)


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing',
    PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class DemoD5ProtectedRollbackTests(TransactionTestCase):
    def test_d2_domain_mutation_during_delivery_rolls_back_complete_identity_dataset(self):
        protected = Organization.objects.create(name='Rancho los Hermanos', code='PROTECTED')
        farm_type, _ = FarmType.objects.get_or_create(code='RANCH', defaults={'name': 'RANCH'})
        farm = Farm.objects.create(organization=protected, farm_type=farm_type, code='OLD-F', name='Protected farm')
        before = d2._existing_database_snapshot()
        directory = settings.DEMO_D2_TEST_ROOT / f'delivery-{uuid4().hex}'
        directory.mkdir(); self.addCleanup(shutil.rmtree, directory)
        delivery = EncryptedTestDelivery(directory, encryption_key=secrets.token_bytes(32))
        def mutate(_bundle):
            Farm.objects.filter(pk=farm.pk).update(name='Unauthorized change')
        with patch.object(delivery, 'stage', side_effect=mutate):
            with self.assertRaises(d2.D2Error):
                d2.create_d2(protected.pk, delivery, signing_key=secrets.token_bytes(32))
        self.assertEqual(d2._existing_database_snapshot(), before)
        self.assertFalse(delivery.pending.exists())
        self.assertFalse(delivery.final.exists())
