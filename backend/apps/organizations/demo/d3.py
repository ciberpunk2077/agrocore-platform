"""Internal D3 domain preparation; disposable D2 test database only."""
from datetime import timedelta
import hashlib
import hmac
import json
from uuid import UUID

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership
from apps.animals.api.schemas import AnimalCreateSchema
from apps.animals.models import Animal
from apps.animals.services.animal_service import AnimalService
from apps.catalogs.models import AnimalStatus, Breed, FarmType, Gender, Species
from apps.common.authorization import MembershipOperationPolicy
from apps.common.context.context import RequestContext
from apps.common.temporal import get_business_today
from apps.farms.api.schemas import FarmCreateSchema
from apps.farms.models import Farm
from apps.farms.services.farm_service import FarmService
from apps.lots.api.schemas import LotCreateSchema
from apps.lots.models import Lot
from apps.lots.services.lot_service import LotService
from apps.organizations.models import Organization
from .d2 import D2Error, DeliveryPending, _digest, _protected, _signature, _verify, test_database
from .preflight import DATASET, PLAN, PLAN_DIGEST, canonical_json, run_lock

RESERVES = (5, 8, 3, 6, 10)
DOMAIN_MODELS = {'farms': Farm, 'lots': Lot, 'animals': Animal}
D4_LABELS = ('weights.Weight', 'vaccinations.Vaccination', 'animal_movements.AnimalMovement',
             'breeding.BreedingEvent', 'pregnancy.Pregnancy', 'births.Birth', 'production.ProductionRecord')


class D3Error(D2Error):
    pass


def resolve_catalogs(species_code, breed_code):
    """Exact codes and exact species relationship; never create/restore catalogs."""
    if not isinstance(species_code, str) or not species_code or not isinstance(breed_code, str) or not breed_code:
        raise D3Error('Explicit species and breed codes are required.')
    try:
        species = Species.objects.get(code=species_code, is_active=True)
        return {'species': species, 'breed': Breed.objects.get(code=breed_code, species=species, is_active=True),
                'farm_type': FarmType.objects.get(code='RANCH', is_active=True),
                'female': Gender.objects.get(code='F', is_active=True), 'male': Gender.objects.get(code='M', is_active=True),
                'status': AnimalStatus.objects.get(code='ACTIVE', is_active=True)}
    except (Species.DoesNotExist, Breed.DoesNotExist, FarmType.DoesNotExist, Gender.DoesNotExist, AnimalStatus.DoesNotExist):
        raise D3Error('Required active catalog code or exact species/breed relationship is missing.') from None


def owner_context(org):
    memberships = list(Membership.objects.filter(organization=org, role=Membership.Role.OWNER).select_related('user'))
    if len(memberships) != 1 or not memberships[0].is_default:
        raise D3Error('Exactly one active default OWNER membership is required.')
    context = RequestContext(user=memberships[0].user, organization=org, membership=memberships[0])
    MembershipOperationPolicy.authorize(context, 'POST')
    return context


def animal_plan(today, direct, reserve, lot_count):
    mothers = reserve * 2 + 6
    calves = max(2, reserve // 2)
    result = []
    for index in range(direct):
        if index < mothers:
            item = {'cohort': 'adult-female', 'sex': 'F', 'days': 1460 + index * 30, 'mother': None, 'father': None}
        elif index < mothers + 2:
            item = {'cohort': 'adult-male', 'sex': 'M', 'days': 2555, 'mother': None, 'father': None}
        elif index >= direct - calves:
            calf_index = index - (direct - calves)
            item = {'cohort': 'existing-calf', 'sex': 'F' if calf_index % 2 == 0 else 'M',
                    'days': min(calf_index + 1, today.day - 1), 'mother': calf_index, 'father': mothers + calf_index % 2}
        else:
            item = {'cohort': 'juvenile', 'sex': 'F' if index % 2 == 0 else 'M',
                    'days': 180 + index % 10 * 45, 'mother': index % mothers, 'father': mothers + index % 2}
        item.update(index=index, internal_id=f'D3-A{index + 1:04d}', birth_date=today - timedelta(days=item.pop('days')))
        item['lot_index'] = item['mother'] % lot_count if item['cohort'] == 'existing-calf' else index % lot_count
        result.append(item)
    # D4 automatic mothers do not overlap the already existing calves' mothers.
    automatic_mothers = list(range(calves, calves + reserve))
    capacities = [sum(row['lot_index'] == lot for row in result) + sum(mother % lot_count == lot for mother in automatic_mothers) + 2 for lot in range(lot_count)]
    return result, automatic_mothers, capacities


def _all_snapshot():
    labels = ('organizations.Organization', 'accounts.User', 'accounts.Membership',
              'farms.Farm', 'lots.Lot', 'animals.Animal', *D4_LABELS,
              'catalogs.FarmType', 'catalogs.Species', 'catalogs.Breed', 'catalogs.Gender', 'catalogs.AnimalStatus')
    return {label: {str(row['id']): row for row in apps.get_model(label)._base_manager.values()} for label in labels}


def _assert_existing(before):
    after = _all_snapshot()
    for label, rows in before.items():
        if any(after[label].get(identifier) != row for identifier, row in rows.items()):
            raise D3Error('Preexisting records changed; rollback required.')
        if label in D4_LABELS and after[label] != rows:
            raise D3Error('D4 records must not be created in D3.')


def _inventory(org_ids):
    result = {}
    for name, model in DOMAIN_MODELS.items():
        rows = list(model._base_manager.filter(organization_id__in=org_ids).order_by('id').values())
        result[name] = {'count': len(rows), 'digest': _digest(rows),
                        'rows': json.loads(json.dumps(rows, default=str, sort_keys=True))}
    return result


def _validate_structure(org_ids, reservations):
    farms = {str(row.pk): row for row in Farm._base_manager.filter(organization_id__in=org_ids)}
    lots = {str(row.pk): row for row in Lot._base_manager.filter(organization_id__in=org_ids)}
    animals = {str(row.pk): row for row in Animal._base_manager.filter(organization_id__in=org_ids).select_related('breed', 'gender', 'status')}
    if len(reservations) != 5 or {row['organization_uuid'] for row in reservations} != set(org_ids):
        raise D3Error('Reservation tenant identities mismatch.')
    future = {}
    for reserve in reservations:
        org = Organization.objects.get(pk=reserve['organization_uuid'])
        index = next(index for index, plan in enumerate(PLAN) if plan[1] == org.code)
        _, _, _, farm_count, lot_count, final_count = PLAN[index]
        if (sum(row.organization_id == org.pk for row in farms.values()), sum(row.organization_id == org.pk for row in lots.values()), sum(row.organization_id == org.pk for row in animals.values())) != (farm_count, lot_count, final_count - RESERVES[index]):
            raise D3Error('Per-organization D3 quotas mismatch.')
        if reserve['automatic_calves'] != RESERVES[index] or len(set(reserve['mother_uuids'])) != RESERVES[index]:
            raise D3Error('Reserved automatic mothers mismatch.')
        today = get_business_today(owner_context(org))
        for identifier in reserve['mother_uuids']:
            mother = animals.get(identifier)
            if not mother or mother.organization_id != org.pk or mother.gender.code != 'F' or not mother.is_active or mother.status.code != 'ACTIVE' or (today - mother.birth_date).days < 1460:
                raise D3Error('Reserved D4 mother is not eligible.')
            future[str(mother.lot_id)] = future.get(str(mother.lot_id), 0) + 1
    for lot in lots.values():
        farm = farms.get(str(lot.farm_id))
        if not farm or farm.organization_id != lot.organization_id or not lot.is_active or not farm.is_active:
            raise D3Error('Lot/farm tenant relationship is invalid.')
        occupied = sum(row.lot_id == lot.pk for row in animals.values())
        if occupied + future.get(str(lot.pk), 0) > lot.capacity:
            raise D3Error('Lot capacity cannot accommodate initial animals and reserved calves.')
    for animal in animals.values():
        lot = lots.get(str(animal.lot_id))
        if not lot or animal.organization_id != lot.organization_id or animal.farm_id != lot.farm_id or animal.breed.species_id != animal.species_id or animal.gender.code not in ('F', 'M') or animal.status.code != 'ACTIVE' or not animal.is_active:
            raise D3Error('Animal tenant, location or catalog relationship is invalid.')
        for identifier, gender in [(animal.mother_id, 'F'), (animal.father_id, 'M')]:
            if identifier is None:
                continue
            parent = animals.get(str(identifier))
            if not parent or parent.organization_id != animal.organization_id or parent.gender.code != gender or parent.birth_date >= animal.birth_date:
                raise D3Error('Genealogy is invalid or cyclic.')


def _verify_d3(bundle, parent, signing_key, org_ids):
    try:
        receipt = bundle['receipt']; payload = receipt['payload']
        if not hmac.compare_digest(receipt['signature'], _signature(payload, signing_key)):
            raise D3Error('D3 receipt signature mismatch.')
        parent_digest = hashlib.sha256(canonical_json(parent['receipt']).encode()).hexdigest()
        if (payload['dataset'], payload['stage'], payload['plan_digest'], payload['parent_digest']) != (DATASET, 'D3-complete', PLAN_DIGEST, parent_digest):
            raise D3Error('Unknown, partial or incompatible D3 receipt.')
        if payload['inventory'] != _inventory(org_ids):
            raise D3Error('D3 dataset is partial or altered; no repair allowed.')
        for name, count in [('farms', 12), ('lots', 39), ('animals', 293)]:
            if payload['inventory'][name]['count'] != count:
                raise D3Error('D3 quotas mismatch.')
        reservations = payload['reservations']
        if len(reservations) != 5 or sum(item['automatic_calves'] for item in reservations) != 32:
            raise D3Error('Automatic calf reservations are incomplete.')
        _validate_structure(org_ids, reservations)
        return {'state': 'recognized-D3', 'farms': 12, 'lots': 39, 'animals': 293, 'reserved_calves': 32}
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, D3Error):
            raise
        raise D3Error('Malformed D3 receipt; no adoption allowed.') from None


def create_d3(protected_uuid, d2_delivery, delivery, *, signing_key, species_code, breed_code, dry_run=False):
    path = test_database()
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise D3Error('A private signing key of at least 32 bytes is required.')
    if delivery is d2_delivery or getattr(delivery, 'final', None) == getattr(d2_delivery, 'final', object()):
        raise D3Error('D3 must use a separate encrypted delivery directory.')
    with run_lock(path):
        protected = _protected(protected_uuid)
        try:
            parent = d2_delivery.load(); bundle = delivery.load()
        except Exception:
            raise D3Error('Encrypted delivery unavailable; no writes performed.') from None
        if parent is None or getattr(d2_delivery, 'pending', None) and d2_delivery.pending.exists():
            raise D3Error('D2 delivery must be complete before D3.')
        _verify(parent, signing_key, protected)
        org_ids = parent['receipt']['payload']['inventory']['organizations']['ids']
        if any(apps.get_model(label)._base_manager.filter(organization_id__in=org_ids).exists() for label in D4_LABELS):
            raise D3Error('Unexpected D4 records already exist; D3 cannot adopt this dataset.')
        catalogs = resolve_catalogs(species_code, breed_code)
        if bundle is not None:
            result = _verify_d3(bundle, parent, signing_key, org_ids)
            if bundle['receipt']['payload']['catalogs'] != {name: str(row.pk) for name, row in catalogs.items()}:
                raise D3Error('Catalog identity differs from the signed D3 plan.')
            if not dry_run:
                try:
                    delivery.publish()
                except Exception:
                    raise DeliveryPending('D3 verified; encrypted receipt publication remains pending.') from None
            return result
        if any(model._base_manager.filter(organization_id__in=org_ids).exists() for model in DOMAIN_MODELS.values()):
            raise D3Error('Domain collision or unknown partial D3 dataset; no adoption allowed.')
        orgs = [Organization.objects.get(pk=identifier) for identifier in org_ids]
        plans = []
        for org in orgs:
            index = next(index for index, item in enumerate(PLAN) if item[1] == org.code)
            context = owner_context(org)
            # Ordinary Animal writes also enforce UTC date. Satisfy both existing contracts.
            today = min(get_business_today(context), timezone.now().date())
            _, _, _, farms_count, lots_count, final_count = PLAN[index]
            animals, automatic, capacities = animal_plan(today, final_count - RESERVES[index], RESERVES[index], lots_count)
            plans.append((context, farms_count, lots_count, animals, automatic, capacities))
        if dry_run:
            return {'state': 'fresh-D3-dry-run', 'farms': 12, 'lots': 39, 'animals': 293, 'reserved_calves': 32}
        before = _all_snapshot()
        try:
            with transaction.atomic(using='default'):
                if any(model._base_manager.filter(organization_id__in=org_ids).exists() for model in DOMAIN_MODELS.values()):
                    raise D3Error('D3 collision detected inside the transaction.')
                reservations = []
                for context, farm_count, lot_count, animal_specs, automatic, capacities in plans:
                    org = context.organization
                    provenance = canonical_json({'dataset': DATASET, 'stage': 'D3', 'parent_run_uuid': parent['receipt']['payload']['run_uuid']})
                    farms = [FarmService.create(context, FarmCreateSchema(name=f'{org.name} · Finca {number + 1}', code=f'D3-F{number + 1:02d}', farm_type_id=catalogs['farm_type'].pk, description=provenance)) for number in range(farm_count)]
                    lots = [LotService.create(context, LotCreateSchema(farm_id=farms[number % farm_count].pk, code=f'D3-L{number + 1:02d}', name=f'Lote {number + 1}', capacity=capacities[number], description=provenance)) for number in range(lot_count)]
                    created = []
                    for spec in animal_specs:
                        lot = lots[spec['lot_index']]
                        animal = AnimalService.create(context, AnimalCreateSchema(farm_id=lot.farm_id, lot_id=lot.pk,
                            species_id=catalogs['species'].pk, breed_id=catalogs['breed'].pk,
                            gender_id=catalogs['female' if spec['sex'] == 'F' else 'male'].pk, status_id=catalogs['status'].pk,
                            internal_id=spec['internal_id'], name=f'Animal demo {spec["index"] + 1}', birth_date=spec['birth_date'],
                            mother_id=created[spec['mother']].pk if spec['mother'] is not None else None,
                            father_id=created[spec['father']].pk if spec['father'] is not None else None,
                            notes=canonical_json({'dataset': DATASET, 'stage': 'D3', 'cohort': spec['cohort']})))
                        created.append(animal)
                    reservations.append({'organization_uuid': str(org.pk), 'automatic_calves': len(automatic),
                        'mother_uuids': [str(created[index].pk) for index in automatic],
                        'adult_female_uuids': [str(animal.pk) for animal, spec in zip(created, animal_specs) if spec['cohort'] == 'adult-female'],
                        'adult_male_uuids': [str(animal.pk) for animal, spec in zip(created, animal_specs) if spec['cohort'] == 'adult-male'],
                        'existing_calf_uuids': [str(animal.pk) for animal, spec in zip(created, animal_specs) if spec['cohort'] == 'existing-calf']})
                _assert_existing(before)
                payload = {'dataset': DATASET, 'stage': 'D3-complete', 'plan_digest': PLAN_DIGEST,
                           'parent_digest': hashlib.sha256(canonical_json(parent['receipt']).encode()).hexdigest(),
                           'catalogs': {name: str(row.pk) for name, row in catalogs.items()}, 'reservations': reservations,
                           'inventory': _inventory(org_ids)}
                bundle = {'receipt': {'payload': payload, 'signature': _signature(payload, signing_key)}}
                _verify_d3(bundle, parent, signing_key, org_ids)
                delivery.stage(bundle)
                _assert_existing(before)
        except Exception as error:
            raise D3Error(f'D3 transaction failed ({type(error).__name__}); rollback requested. Any staged receipt remains unconfirmed; never reseed automatically.') from None
        try:
            delivery.publish()
        except Exception:
            raise DeliveryPending('D3 committed; encrypted receipt pending. Verify and recover the same receipt; do not reseed.') from None
        return {'state': 'created-D3', 'farms': 12, 'lots': 39, 'animals': 293, 'reserved_calves': 32}
