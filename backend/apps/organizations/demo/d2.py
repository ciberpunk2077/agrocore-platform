"""Internal D2 writer, restricted to the dedicated disposable test database."""
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import tempfile
from types import SimpleNamespace
from uuid import UUID, uuid4

from django.conf import settings
from django.apps import apps
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password
from django.db import connections, transaction
from django.db.models import Q
from django.utils.text import slugify

from apps.accounts.models import Membership, User
from apps.organizations.models import Organization
from apps.organizations.services import create_organization
from .preflight import DATASET, PLAN, PLAN_DIGEST, authorize_database, canonical_json, demo_emails, run_lock
from .errors import D2Error

ROLES = (
    ('OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR', 'VIEWER'),
    ('OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR', 'OPERATOR', 'OPERATOR', 'VIEWER'),
    ('OWNER', 'ADMIN', 'OPERATOR', 'VIEWER'),
    ('OWNER', 'ADMIN', 'VETERINARIAN', 'OPERATOR', 'OPERATOR', 'VIEWER'),
    ('OWNER', 'ADMIN', 'VETERINARIAN', 'VETERINARIAN', 'OPERATOR', 'OPERATOR', 'OPERATOR', 'VIEWER'),
)
MODELS = {'organizations': Organization, 'users': User, 'memberships': Membership}


class DeliveryPending(D2Error):
    """Database committed; retain the staged encrypted bundle for recovery."""


def test_database(*, _allow_atomic=False):
    from .rehearsal_scope import scoped_database
    scoped = scoped_database(_allow_atomic=_allow_atomic)
    if scoped is not None:
        return scoped
    if settings.SETTINGS_MODULE != 'config.settings.demo_d2_testing':
        raise D2Error('D2 writes are restricted to dedicated disposable tests.')
    root = Path(settings.DEMO_D2_TEST_ROOT)
    path = Path(connections['default'].settings_dict['NAME'])
    if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith('agrocore-d2-') or path != root / 'disposable.sqlite3':
        raise D2Error('Disposable test database identity mismatch.')
    if connections['default'].in_atomic_block and not _allow_atomic:
        raise D2Error('D2 requires its own top-level transaction, not an outer transaction.')
    # Reuse all D1 SQLite/path guards after the stronger test-only environment gate.
    config = SimpleNamespace(SETTINGS_MODULE='config.settings.demo_testing',
        DATABASES={'default': connections['default'].settings_dict}, DEMO_AUTHORIZED_DATABASE=str(path))
    return authorize_database(config, 'default')


def _digest(rows):
    serialized = json.dumps(sorted(rows, key=lambda row: str(row['id'])), default=str, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _snapshot(ids):
    return {name: _digest(list(model._base_manager.filter(pk__in=ids[name]).values())) for name, model in MODELS.items()}


def _inventory(ids):
    digests = _snapshot(ids)
    return {name: {'ids': sorted(str(value) for value in ids[name]), 'digest': digests[name]} for name in MODELS}


def _existing_database_snapshot():
    """Include the entire protected domain graph, not just identity tables."""
    return {model._meta.label: {str(row[model._meta.pk.attname]): row for row in model._base_manager.values()}
            for model in apps.get_models() if model._meta.managed and not model._meta.proxy}


def _assert_existing_database(before):
    after = _existing_database_snapshot()
    allowed = {model._meta.label for model in MODELS.values()}
    for label, rows in before.items():
        if any(after[label].get(identifier) != row for identifier, row in rows.items()):
            raise D2Error('Preexisting database records changed; rollback required.')
        if label not in allowed and set(after[label]) != set(rows):
            raise D2Error('Unexpected domain records during D2; rollback required.')


def _signature(payload, key):
    return hmac.new(key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()


def _protected(identifier):
    try:
        row = Organization._base_manager.get(pk=UUID(str(identifier)))
    except (ValueError, TypeError, Organization.DoesNotExist):
        raise D2Error('Protected organization UUID is unavailable.') from None
    if row.name.strip().casefold() != 'rancho los hermanos':
        raise D2Error('Protected UUID does not identify Rancho los Hermanos.')
    return row


def _collisions():
    predicate = Q()
    for name, code, *_ in PLAN:
        predicate |= Q(name=name) | Q(code=code) | Q(slug=slugify(name))
    if Organization._base_manager.filter(predicate).exists():
        raise D2Error('Organization collision or partial/unknown dataset; no adoption allowed.')
    predicate = Q()
    for email in demo_emails():
        predicate |= Q(email__iexact=email)
    if User._base_manager.filter(predicate).exists():
        raise D2Error('Existing account collision; no account or password may be reused.')


def _verify(bundle, key, protected):
    try:
        receipt = bundle['receipt']; payload = receipt['payload']
        if not hmac.compare_digest(receipt['signature'], _signature(payload, key)):
            raise D2Error('Receipt signature mismatch.')
        if (payload['dataset'], payload['stage'], payload['plan_digest'], payload['protected_uuid']) != (DATASET, 'D2-complete', PLAN_DIGEST, str(protected.pk)):
            raise D2Error('Unknown, partial or incompatible D2 receipt.')
        if set(payload['inventory']) != set(MODELS):
            raise D2Error('Incomplete D2 inventory.')
        ids = {name: [UUID(value) for value in entry['ids']] for name, entry in payload['inventory'].items()}
        if len(ids['organizations']) != 5 or len(ids['users']) != 30 or len(ids['memberships']) != 30:
            raise D2Error('Partial D2 inventory.')
        if protected.pk in ids['organizations'] or _inventory(ids) != payload['inventory']:
            raise D2Error('Dataset missing or altered; automatic repair is forbidden.')
        organization_ids = set(ids['organizations'])
        if set(User._base_manager.filter(pk__in=ids['users']).values_list('email', flat=True)) != set(demo_emails()):
            raise D2Error('Demo email plan differs; existing accounts and receipts cannot be migrated automatically.')
        # Reject additional memberships even when the signed original rows still match.
        actual_memberships = set(Membership._base_manager.filter(Q(user_id__in=ids['users']) | Q(organization_id__in=ids['organizations'])).values_list('pk', flat=True))
        if actual_memberships != set(ids['memberships']):
            raise D2Error('Additional or cross-tenant membership detected.')
        credentials = bundle['credentials']
        if len(credentials) != 30 or len({entry['user_uuid'] for entry in credentials}) != 30:
            raise D2Error('Incomplete credential delivery bundle.')
        for entry in credentials:
            user = User._base_manager.get(pk=UUID(entry['user_uuid']))
            if user.pk not in ids['users'] or entry['email'] != user.email or not check_password(entry['password'], user.password):
                raise D2Error('Credential bundle does not match committed users.')
            membership = Membership._base_manager.get(pk=UUID(entry['membership_uuid']))
            if membership.pk not in ids['memberships'] or membership.user_id != user.pk or str(membership.organization_id) != entry['organization_uuid'] or membership.role != entry['role']:
                raise D2Error('Credential identity or membership provenance mismatch.')
        for org in Organization._base_manager.filter(pk__in=organization_ids):
            index = next(index for index, plan in enumerate(PLAN) if plan[1] == org.code)
            if org.name != PLAN[index][0] or org.slug != slugify(org.name):
                raise D2Error('Organization identity mismatch.')
            memberships = list(Membership._base_manager.filter(organization=org).select_related('user'))
            if sorted(item.role for item in memberships) != sorted(ROLES[index]):
                raise D2Error('Role quotas mismatch.')
            for membership in memberships:
                user = membership.user
                if not membership.is_default or not membership.is_active or not user.is_active or user.is_staff or user.is_superuser or not user.email.startswith(org.code.lower() + '.'):
                    raise D2Error('User or membership invariants failed.')
        return {'state': 'recognized-D2', 'organizations': 5, 'users': 30, 'memberships': 30}
    except (KeyError, TypeError, ValueError, StopIteration, User.DoesNotExist, Membership.DoesNotExist) as error:
        if isinstance(error, D2Error):
            raise
        raise D2Error('Malformed D2 bundle; no adoption allowed.') from None


def create_d2(protected_uuid, delivery, *, signing_key, dry_run=False):
    """No CLI exposure. All errors exclude credentials and underlying payloads."""
    path = test_database()
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise D2Error('A private signing key of at least 32 bytes is required.')
    with run_lock(path):
        protected = _protected(protected_uuid)
        try:
            bundle = delivery.load()
        except Exception:
            raise D2Error('Credential bundle could not be read; no writes performed.') from None
        if bundle is not None:
            result = _verify(bundle, signing_key, protected)
            if not dry_run:
                try:
                    delivery.publish()
                except Exception:
                    raise DeliveryPending('Verified dataset; encrypted delivery remains pending.') from None
            return result
        _collisions()
        if dry_run:
            return {'state': 'fresh-D2-dry-run', 'organizations': 5, 'users': 30, 'memberships': 30}
        existing = {name: list(model._base_manager.values_list('pk', flat=True)) for name, model in MODELS.items()}
        before = _snapshot(existing)
        database_before = _existing_database_snapshot()
        run_id = str(uuid4()); credentials = []
        ids = {name: [] for name in MODELS}
        try:
            with transaction.atomic(using='default'):
                # Recheck conflicts within the transaction before any insertion.
                _collisions()
                for (name, code, count, *_), roles in zip(PLAN, ROLES):
                    description = canonical_json({'dataset': DATASET, 'stage': 'D2', 'run_uuid': run_id})
                    fields = dict(id=uuid4(), name=name, code=code, slug=slugify(name), description=description, timezone='America/Mexico_City')
                    candidate = Organization(**fields); candidate.full_clean()
                    org = create_organization(**fields); ids['organizations'].append(org.pk)
                    if count != len(roles):
                        raise D2Error('Invalid role plan.')
                    for index, role in enumerate(roles, 1):
                        fields = dict(id=uuid4(), email=f'{code.lower()}.{index:02d}@demo.example.com',
                            first_name='Demo', last_name=f'{code} {index:02d}', is_active=True, is_staff=False, is_superuser=False)
                        candidate = User(**fields); candidate.set_unusable_password(); candidate.full_clean()
                        password = secrets.token_urlsafe(32); validate_password(password, user=candidate)
                        user = User.objects.create_user(password=password, **fields); user.full_clean()
                        membership = Membership(id=uuid4(), user=user, organization=org, role=role, is_default=True)
                        membership.full_clean(); membership.save()
                        ids['users'].append(user.pk); ids['memberships'].append(membership.pk)
                        credentials.append({'user_uuid': str(user.pk), 'organization_uuid': str(org.pk), 'membership_uuid': str(membership.pk), 'email': user.email, 'role': role, 'password': password})
                if _snapshot(existing) != before:
                    raise D2Error('Preexisting records changed; rollback required.')
                _assert_existing_database(database_before)
                payload = {'dataset': DATASET, 'stage': 'D2-complete', 'run_uuid': run_id,
                    'plan_digest': PLAN_DIGEST, 'protected_uuid': str(protected.pk), 'inventory': _inventory(ids)}
                bundle = {'receipt': {'payload': payload, 'signature': _signature(payload, signing_key)}, 'credentials': credentials}
                _verify(bundle, signing_key, protected)
                delivery.stage(bundle)  # Failure here rolls back the entire DB transaction.
                if _snapshot(existing) != before:
                    raise D2Error('Preexisting records changed while staging; rollback required.')
                _assert_existing_database(database_before)
        except Exception as error:
            raise D2Error(f'D2 transaction failed ({type(error).__name__}); rollback was requested. Any staged bundle is unconfirmed; verify it before recovery and never reseed automatically.') from None
        try:
            delivery.publish()
        except Exception:
            raise DeliveryPending('D2 committed; encrypted delivery pending. Recover using the same bundle and signing key; do not reseed.') from None
        return {'state': 'created-D2', 'organizations': 5, 'users': 30, 'memberships': 30}
