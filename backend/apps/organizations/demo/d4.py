"""D4 service-only writer. No command exposure; disposable SQLite tests only."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import hashlib
import hmac
import json

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from apps.animals.models import Animal
from apps.animal_movements.api.schemas import AnimalMovementCreateSchema
from apps.animal_movements.services.animal_movement_service import AnimalMovementService
from apps.births.api.schemas import BirthCreateSchema
from apps.births.services.birth_service import BirthService
from apps.breeding.api.schemas import BreedingCreateSchema
from apps.breeding.services.breeding_service import BreedingService
from apps.catalogs.models import AnimalStatus, BreedingType, Gender, MovementType, ProductionType, WeighingMethod
from apps.common.temporal import get_business_today, get_business_timezone
from apps.lots.models import Lot
from apps.organizations.models import Organization
from apps.pregnancy.api.schemas import PregnancyCreateSchema
from apps.pregnancy.services.pregnancy_service import PregnancyService
from apps.production.api.schemas import ProductionCreateSchema
from apps.production.services.production_service import ProductionService
from apps.vaccinations.api.schemas import VaccinationCreateSchema
from apps.vaccinations.services.vaccination_service import VaccinationService, VACCINATION_TIME_ZONE
from apps.weights.api.schemas import WeightCreateSchema
from apps.weights.services.weight_service import WeightService
from .d2 import D2Error, DeliveryPending, _digest, _protected, _signature, _verify, test_database
from .d3 import D4_LABELS, RESERVES, _all_snapshot, _inventory as d3_inventory, _verify_d3, owner_context, resolve_catalogs
from .preflight import DATASET, PLAN, canonical_json, run_lock

# weights, vaccinations, sales, existing live births, within-window pregnancies, production
QUOTAS = ((12, 6, 1, 2, 2, 6), (16, 9, 2, 3, 3, 8), (0, 4, 1, 1, 0, 3),
          (14, 8, 2, 2, 2, 7), (20, 12, 3, 4, 4, 10))
QUOTA_DIGEST = hashlib.sha256(canonical_json(QUOTAS).encode()).hexdigest()
CATALOG_LABELS = ('catalogs.WeighingMethod', 'catalogs.BreedingType', 'catalogs.MovementType', 'catalogs.ProductionType')


class D4Error(D2Error):
    pass


def _receipt_digest(bundle):
    return hashlib.sha256(canonical_json(bundle['receipt']).encode()).hexdigest()


def _signed_parent(bundle, parent, key):
    try:
        receipt = bundle['receipt']; payload = receipt['payload']
        if not hmac.compare_digest(receipt['signature'], _signature(payload, key)) or payload['stage'] != 'D3-complete' or payload['dataset'] != DATASET or payload['parent_digest'] != _receipt_digest(parent):
            raise D4Error('D3 receipt chain is invalid.')
    except (KeyError, TypeError, ValueError):
        raise D4Error('D3 receipt chain is invalid.') from None


def _catalogs(species_code, breed_code, weighing_code, breeding_code):
    base = resolve_catalogs(species_code, breed_code)
    # Explicit demo-plan compatibility, not a new domain validation rule.
    if (species_code, breed_code) != ('BOV', 'HOL'):
        raise D4Error('D4 V1 only supports the explicitly planned BOV/HOL/MILK combination.')
    if not weighing_code or not breeding_code:
        raise D4Error('Explicit weighing and breeding catalog codes are required.')
    try:
        base.update(weighing=WeighingMethod.objects.get(code=weighing_code, is_active=True),
                    breeding=BreedingType.objects.get(code=breeding_code, is_active=True),
                    transfer=MovementType.objects.get(code='TRANSFER', is_active=True),
                    sale=MovementType.objects.get(code='SALE', is_active=True),
                    sold=AnimalStatus.objects.get(code='SOLD', is_active=True),
                    production=ProductionType.objects.get(code='MILK', is_active=True))
    except (WeighingMethod.DoesNotExist, BreedingType.DoesNotExist, MovementType.DoesNotExist, AnimalStatus.DoesNotExist, ProductionType.DoesNotExist):
        raise D4Error('A required active D4 catalog code is missing.') from None
    if base['production'].default_unit != 'L':
        raise D4Error('MILK must use the approved demo unit L.')
    return base


def _snapshot():
    result = _all_snapshot()
    for label in CATALOG_LABELS:
        result[label] = {str(row['id']): row for row in apps.get_model(label)._base_manager.values()}
    return result


def _protect(before, movement_ids, demo_org_ids):
    after = _snapshot()
    permitted = {'farm_id', 'lot_id', 'status_id'}
    for label, rows in before.items():
        for identifier, row in rows.items():
            current = after[label].get(identifier)
            if current == row:
                continue
            if label != 'animals.Animal' or identifier not in movement_ids or current is None or {field for field in row if row[field] != current[field]} - permitted:
                raise D4Error('A preexisting record outside the allowed movement transitions changed.')
        extras = set(after[label]) - set(rows)
        if extras:
            if label not in D4_LABELS and label != 'animals.Animal':
                raise D4Error('Unexpected record creation outside D4 scope.')
            if any(str(after[label][identifier]['organization_id']) not in demo_org_ids for identifier in extras):
                raise D4Error('New D4 record crosses tenant boundaries.')


def _inventory(org_ids):
    result = {}
    for label in ('animals.Animal', *D4_LABELS):
        rows = list(apps.get_model(label)._base_manager.filter(organization_id__in=org_ids).order_by('id').values())
        result[label] = {'count': len(rows), 'digest': _digest(rows), 'rows': json.loads(json.dumps(rows, default=str, sort_keys=True))}
    return result


def _validate(org_ids, parent3, payload):
    models = {label: list(apps.get_model(label)._base_manager.filter(organization_id__in=org_ids)) for label in ('animals.Animal', *D4_LABELS)}
    animals = {str(row.pk): row for row in models['animals.Animal']}
    original = {row['id']: row for row in parent3['receipt']['payload']['inventory']['animals']['rows']}
    automatic = set(payload['automatic_calf_uuids'])
    if len(automatic) != 32 or set(animals) - set(original) != automatic or len(animals) != 325:
        raise D4Error('Automatic calf or final animal quotas mismatch.')
    current_rows = {row['id']: row for row in payload['inventory']['animals.Animal']['rows']}
    transitions = payload['transitions']
    for identifier, old in original.items():
        current = current_rows.get(identifier)
        if current != old:
            transition = transitions.get(identifier)
            if not transition or transition != {'before': old, 'after': current} or {field for field in old if old[field] != current[field]} - {'farm_id', 'lot_id', 'status_id'}:
                raise D4Error('Unapproved D3 animal mutation.')
    for lot in Lot.objects.filter(organization_id__in=org_ids):
        if sum(row.lot_id == lot.pk for row in animals.values()) > lot.capacity:
            raise D4Error('Final lot occupancy exceeds reserved capacity.')
    for label in D4_LABELS:
        for row in models[label]:
            for field in ('animal_id', 'mother_id', 'calf_id'):
                identifier = getattr(row, field, None)
                if identifier is not None and (str(identifier) not in animals or animals[str(identifier)].organization_id != row.organization_id):
                    raise D4Error('D4 animal foreign key crosses tenants.')
    for row in models['breeding.BreedingEvent']:
        mother = animals[str(row.animal_id)]; father = animals.get(str(row.male_id))
        today = date.fromisoformat(payload['operating_dates'][str(row.organization_id)])
        if mother.gender.code != 'F' or not father or father.gender.code != 'M' or father.organization_id != row.organization_id or row.date < max(mother.birth_date, father.birth_date) or row.date > today:
            raise D4Error('Breeding tenant, sex or chronology is invalid.')
    for row in models['pregnancy.Pregnancy']:
        today = date.fromisoformat(payload['operating_dates'][str(row.organization_id)])
        if row.breeding.organization_id != row.organization_id or row.breeding.animal_id != row.animal_id or not row.confirmed or not (row.breeding.date <= row.diagnosis_date <= today) or row.expected_birth <= row.diagnosis_date:
            raise D4Error('Pregnancy relation or chronology is invalid.')
    for row in models['weights.Weight']:
        if row.weight <= 0 or row.date < animals[str(row.animal_id)].birth_date:
            raise D4Error('Weight chronology or amount is invalid.')
    for row in models['vaccinations.Vaccination']:
        if row.dose <= 0 or row.application_date < animals[str(row.animal_id)].birth_date or row.next_application_date is not None and row.next_application_date <= row.application_date or not row.vaccine_name.startswith('DEMO'):
            raise D4Error('Synthetic vaccination chronology or amount is invalid.')
    for row in models['production.ProductionRecord']:
        mother = animals[str(row.animal_id)]
        if mother.species.code != 'BOV' or mother.breed.code != 'HOL' or mother.breed.species_id != mother.species_id or mother.gender.code != 'F' or row.production_type.code != 'MILK' or row.unit != row.production_type.default_unit or row.unit != 'L' or row.quantity <= 0 or timezone.is_naive(row.recorded_at):
            raise D4Error('Production species, sex, type, unit or timestamp is invalid.')
    # Replay real movement records from signed D3 origin state; never update the DB.
    states = {identifier: {field: row[field] for field in ('farm_id', 'lot_id', 'status_id')} for identifier, row in original.items()}
    previous_dates = {}
    for row in sorted(models['animal_movements.AnimalMovement'], key=lambda row: (row.date, str(row.pk))):
        identifier = str(row.animal_id); state = states.get(identifier)
        if state is None or (str(row.origin_farm_id), str(row.origin_lot_id), str(row.origin_status_id)) != (state['farm_id'], state['lot_id'], state['status_id']) or row.date < animals[identifier].birth_date or identifier in previous_dates and row.date <= previous_dates[identifier]:
            raise D4Error('Movement origin, tenant or chronology is invalid.')
        if row.movement_type.code == 'TRANSFER':
            if not row.destination_lot or row.destination_lot.organization_id != row.organization_id or row.destination_lot.farm_id != row.destination_farm_id:
                raise D4Error('Movement destination crosses tenants.')
            state.update(farm_id=str(row.destination_farm_id), lot_id=str(row.destination_lot_id))
        elif row.movement_type.code == 'SALE':
            if row.destination_farm_id or row.destination_lot_id:
                raise D4Error('SALE must remove location.')
            state.update(farm_id=None, lot_id=None, status_id=str(AnimalStatus.objects.get(code='SOLD').pk))
        else:
            raise D4Error('Unexpected movement type in D4 plan.')
        previous_dates[identifier] = row.date
    for identifier in previous_dates:
        if states[identifier] != {field: current_rows[identifier][field] for field in ('farm_id', 'lot_id', 'status_id')}:
            raise D4Error('Movement final state differs from its service-generated transition.')
    births = models['births.Birth']
    if len({row.pregnancy_id for row in births}) != len(births):
        raise D4Error('A pregnancy is used by multiple births.')
    for row in births:
        pregnancy = row.pregnancy
        if pregnancy.organization_id != row.organization_id or pregnancy.animal_id != row.mother_id or pregnancy.status != 'FINISHED' or not (pregnancy.breeding.date <= pregnancy.diagnosis_date <= row.birth_date):
            raise D4Error('Birth/pregnancy chronology or transition is invalid.')
        if not row.alive and row.calf_id is not None:
            raise D4Error('Non-live birth must not create or associate an animal.')
        if str(row.calf_id) in automatic:
            calf = animals[str(row.calf_id)]; mother = animals[str(row.mother_id)]
            if calf.mother_id != mother.pk or calf.father_id != pregnancy.breeding.male_id or calf.farm_id != mother.farm_id or calf.lot_id != mother.lot_id or calf.birth_date != row.birth_date:
                raise D4Error('Automatic calf does not match its reserved mother.')
    for index, (_, code, _, _, _, final) in enumerate(PLAN):
        org = Organization.objects.get(code=code)
        weights, vaccines, sales, existing, upcoming, production = QUOTAS[index]
        birth_count = RESERVES[index] + existing + 1
        expectations = dict(zip(D4_LABELS, [weights, vaccines, sales + 1, birth_count + 1 + upcoming + 1, birth_count + 1 + upcoming + 1, birth_count, production]))
        if sum(row.organization_id == org.pk for row in animals.values()) != final:
            raise D4Error('Per-tenant animal quota mismatch.')
        for label, expected in expectations.items():
            if sum(row.organization_id == org.pk for row in models[label]) != expected:
                raise D4Error('Per-tenant record quota mismatch.')
        pregnancies = [row for row in models['pregnancy.Pregnancy'] if row.organization_id == org.pk]
        if [sum(row.status == state for row in pregnancies) for state in ('FINISHED', 'ABORTED', 'ACTIVE')] != [birth_count, 1, upcoming + 1]:
            raise D4Error('Pregnancy outcome quotas mismatch.')
        if sum(str(row.pk) in automatic and row.organization_id == org.pk for row in animals.values()) != RESERVES[index]:
            raise D4Error('Per-tenant automatic calf quota mismatch.')
        if sum(row.organization_id == org.pk and row.status.code == 'SOLD' for row in animals.values()) != sales:
            raise D4Error('SALE transitions do not match quotas.')


def _verify_d4(bundle, parent2, parent3, key, org_ids, catalogs):
    try:
        receipt = bundle['receipt']; payload = receipt['payload']
        if not hmac.compare_digest(receipt['signature'], _signature(payload, key)) or payload['stage'] != 'D4-complete' or payload['dataset'] != DATASET or payload['quota_digest'] != QUOTA_DIGEST or payload['parent_digest'] != _receipt_digest(parent3):
            raise D4Error('D4 signed receipt chain is invalid.')
        if payload['catalogs'] != {name: str(row.pk) for name, row in catalogs.items()}:
            raise D4Error('D4 catalog identity changed.')
        if payload['inventory'] != _inventory(org_ids):
            raise D4Error('D4 dataset is partial or altered; no repair allowed.')
        # D3 farms/lots remain immutable; animal changes are verified by the transition chain.
        current3 = d3_inventory(org_ids)
        for label in ('farms', 'lots'):
            if current3[label] != parent3['receipt']['payload']['inventory'][label]:
                raise D4Error('D3 farms or lots changed.')
        _validate(org_ids, parent3, payload)
        return {'state': 'recognized-D4', 'animals': 325, 'automatic_calves': 32}
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, D4Error):
            raise
        raise D4Error('Malformed D4 receipt; no adoption allowed.') from None


def create_d4(protected_uuid, d2_delivery, d3_delivery, delivery, *, signing_key,
              species_code, breed_code, weighing_method_code, breeding_type_code, dry_run=False):
    path = test_database()
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise D4Error('A private signing key of at least 32 bytes is required.')
    if len({str(item.final) for item in (d2_delivery, d3_delivery, delivery)}) != 3:
        raise D4Error('D4 requires a separate encrypted delivery directory.')
    with run_lock(path):
        protected = _protected(protected_uuid)
        try:
            parent2, parent3, bundle = d2_delivery.load(), d3_delivery.load(), delivery.load()
        except Exception:
            raise D4Error('Encrypted delivery could not be read; no writes performed.') from None
        if parent2 is None or parent3 is None or d2_delivery.pending.exists() or d3_delivery.pending.exists():
            raise D4Error('D2 and D3 must be complete and published before D4.')
        _verify(parent2, signing_key, protected)
        _signed_parent(parent3, parent2, signing_key)
        org_ids = parent2['receipt']['payload']['inventory']['organizations']['ids']
        catalogs = _catalogs(species_code, breed_code, weighing_method_code, breeding_type_code)
        if parent3['receipt']['payload']['catalogs'] != {name: str(row.pk) for name, row in catalogs.items() if name in parent3['receipt']['payload']['catalogs']}:
            raise D4Error('D3 catalog bindings differ from D4.')
        if bundle is not None:
            result = _verify_d4(bundle, parent2, parent3, signing_key, org_ids, catalogs)
            if not dry_run:
                try:
                    delivery.publish()
                except Exception:
                    raise DeliveryPending('D4 verified; encrypted receipt publication remains pending.') from None
            return result
        _verify_d3(parent3, parent2, signing_key, org_ids)
        if any(apps.get_model(label)._base_manager.filter(organization_id__in=org_ids).exists() for label in D4_LABELS):
            raise D4Error('Unknown or partial D4 records already exist; no adoption allowed.')
        if dry_run:
            return {'state': 'fresh-D4-dry-run', 'animals': 325, 'automatic_calves': 32}
        before = _snapshot(); automatic_ids = []; movement_ids = set(); operating_dates = {}
        original = {row['id']: row for row in parent3['receipt']['payload']['inventory']['animals']['rows']}
        try:
            with transaction.atomic(using='default'):
                _verify_d3(parent3, parent2, signing_key, org_ids)
                for reservation in parent3['receipt']['payload']['reservations']:
                    org = Organization.objects.get(pk=reservation['organization_uuid']); context = owner_context(org)
                    index = next(index for index, plan in enumerate(PLAN) if plan[1] == org.code)
                    weights, vaccines, sales, existing_count, inside, production = QUOTAS[index]
                    today = get_business_today(context)
                    history_day = min(today, timezone.localdate(), timezone.localdate(timezone=VACCINATION_TIME_ZONE))
                    operating_dates[str(org.pk)] = today.isoformat()
                    adults = [Animal.objects.get(pk=identifier) for identifier in reservation['adult_female_uuids']]
                    males = [Animal.objects.get(pk=identifier) for identifier in reservation['adult_male_uuids']]
                    automatic_mothers = [Animal.objects.get(pk=identifier) for identifier in reservation['mother_uuids']]
                    existing_calves = [Animal.objects.get(pk=identifier) for identifier in reservation['existing_calf_uuids'][:existing_count]]
                    used = {row.pk for row in automatic_mothers} | {row.mother_id for row in existing_calves}
                    spare = [row for row in adults if row.pk not in used]
                    birth_specs = [(mother, today, None) for mother in automatic_mothers]
                    birth_specs += [(calf.mother, calf.birth_date, calf) for calf in existing_calves]
                    birth_specs += [(spare.pop(0), today, False)]
                    for number, (mother, birth_date, calf) in enumerate(birth_specs):
                        father = calf.father if calf not in (None, False) else males[number % len(males)]
                        event = BreedingService.create(context, BreedingCreateSchema(animal_id=mother.pk, male_id=father.pk, breeding_type_id=catalogs['breeding'].pk,
                            date=birth_date - timedelta(days=280), expected_birth=birth_date, notes='DEMO D4 synthetic breeding'))
                        pregnancy = PregnancyService.create(context, PregnancyCreateSchema(animal_id=mother.pk, breeding_id=event.pk, diagnosis_date=birth_date - timedelta(days=200), expected_birth=birth_date, confirmed=True, notes='DEMO D4 confirmed'))
                        birth = BirthService.create(context, BirthCreateSchema(pregnancy_id=pregnancy.pk, mother_id=mother.pk, calf_id=calf.pk if calf not in (None, False) else None,
                            calf_gender_id=calf.gender_id if calf not in (None, False) else catalogs['female' if number % 2 == 0 else 'male'].pk,
                            birth_date=birth_date, birth_weight=Decimal('32.00'), alive=calf is not False, dystocia=number == 0, notes='DEMO D4 synthetic birth'))
                        if calf is None:
                            automatic_ids.append(str(birth.calf_id))
                    # Distinct mothers for aborted and active outcomes; no direct status assignment.
                    for number, offset in enumerate([60] + ([0, 30, 14, 21][:inside]) + [31]):
                        mother = spare.pop(0)
                        expected = today + timedelta(days=offset)
                        event = BreedingService.create(context, BreedingCreateSchema(animal_id=mother.pk, male_id=males[number % len(males)].pk, breeding_type_id=catalogs['breeding'].pk,
                            date=expected - timedelta(days=280), expected_birth=expected, notes='DEMO D4 forecast'))
                        pregnancy = PregnancyService.create(context, PregnancyCreateSchema(animal_id=mother.pk, breeding_id=event.pk,
                            diagnosis_date=expected - timedelta(days=200), expected_birth=expected, confirmed=True, notes='DEMO D4 forecast'))
                        if number == 0:
                            PregnancyService.abort(context, pregnancy.pk)
                    for number, animal in enumerate(adults[:weights // 2]):
                        for age, gain in [(60, 0), (5, 20)]:
                            WeightService.create(context, WeightCreateSchema(animal_id=animal.pk, weighing_method_id=catalogs['weighing'].pk,
                                date=history_day - timedelta(days=age), weight=Decimal(400 + index * 25 + number * 3 + gain), notes='DEMO D4 synthetic weight'))
                    for number, animal in enumerate(adults[:vaccines]):
                        next_day = [today - timedelta(days=2), today, today + timedelta(days=14), None][number % 4]
                        VaccinationService.create(context, VaccinationCreateSchema(animal_id=animal.pk, vaccine_name='DEMO — vacuna ficticia, sin protocolo clínico',
                            application_date=history_day - timedelta(days=45), next_application_date=next_day, dose=Decimal('1.00'), notes='Synthetic UI test data only'))
                    recorded_at = datetime.combine(today, time.min, tzinfo=get_business_timezone(context))
                    for number in range(production):
                        mother = automatic_mothers[number % len(automatic_mothers)]
                        ProductionService.create(context, ProductionCreateSchema(animal_id=mother.pk, production_type_id=catalogs['production'].pk,
                            recorded_at=recorded_at, quantity=Decimal('12.500') + number, notes=f'DEMO D4 synthetic milk #{number + 1}'))
                    # Move/sell only unrelated juveniles, after every other operation.
                    juveniles = [row for row in Animal.objects.filter(organization=org).order_by('internal_id') if row.notes and row.notes.startswith('{') and json.loads(row.notes).get('cohort') == 'juvenile']
                    moving = juveniles[:sales]
                    lots = list(Lot.objects.filter(organization=org).order_by('code'))
                    animal = moving[0]
                    destination = next(lot for lot in lots if lot.pk != animal.lot_id)
                    AnimalMovementService.create(context, AnimalMovementCreateSchema(animal_id=animal.pk, movement_type_id=catalogs['transfer'].pk,
                        origin_farm_id=animal.farm_id, origin_lot_id=animal.lot_id, destination_farm_id=destination.farm_id, destination_lot_id=destination.pk,
                        date=history_day - timedelta(days=7), reason='DEMO D4 transfer'))
                    for animal in moving:
                        animal.refresh_from_db()
                        AnimalMovementService.create(context, AnimalMovementCreateSchema(animal_id=animal.pk, movement_type_id=catalogs['sale'].pk,
                            origin_farm_id=animal.farm_id, origin_lot_id=animal.lot_id, date=history_day - timedelta(days=1), reason='DEMO D4 sale'))
                        movement_ids.add(str(animal.pk))
                _protect(before, movement_ids, set(org_ids))
                inventory = _inventory(org_ids)
                after_animals = {row['id']: row for row in inventory['animals.Animal']['rows']}
                payload = {'dataset': DATASET, 'stage': 'D4-complete', 'quota_digest': QUOTA_DIGEST,
                           'parent_digest': _receipt_digest(parent3), 'catalogs': {name: str(row.pk) for name, row in catalogs.items()},
                           'operating_dates': operating_dates, 'automatic_calf_uuids': automatic_ids, 'inventory': inventory,
                           'transitions': {identifier: {'before': original[identifier], 'after': after_animals[identifier]} for identifier in movement_ids}}
                bundle = {'receipt': {'payload': payload, 'signature': _signature(payload, signing_key)}}
                _verify_d4(bundle, parent2, parent3, signing_key, org_ids, catalogs)
                delivery.stage(bundle)
                _protect(before, movement_ids, set(org_ids))
        except Exception as error:
            raise D4Error(f'D4 transaction failed ({type(error).__name__}); rollback requested. Any staged receipt is unconfirmed; never reseed automatically.') from None
        try:
            delivery.publish()
        except Exception:
            raise DeliveryPending('D4 committed; encrypted receipt pending. Recover the same verified receipt without reseeding.') from None
        return {'state': 'created-D4', 'animals': 325, 'automatic_calves': 32}
