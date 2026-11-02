from collections import Counter
import io
import json
import secrets
import shutil
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.hashers import identify_hasher, PBKDF2PasswordHasher
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, OperationalError
from django.test import TransactionTestCase, override_settings

from apps.accounts.models import Membership, User
from apps.organizations.models import Organization
from apps.organizations.demo.d2 import D2Error, DeliveryPending, PLAN, ROLES, create_d2, test_database
from apps.organizations.demo.delivery import EncryptedTestDelivery


class FastTestPBKDF2(PBKDF2PasswordHasher):
    iterations = 1000  # Test-only cost; algorithm and per-user random salt remain real.


@override_settings(SETTINGS_MODULE='config.settings.demo_d2_testing', PASSWORD_HASHERS=['apps.organizations.tests_demo_d2.FastTestPBKDF2'])
class DemoD2Tests(TransactionTestCase):
    def setUp(self):
        self.protected = Organization.objects.create(name='Rancho los Hermanos', code='PROTECTED')
        self.old_user = User.objects.create_user(email='existing@example.invalid', password=secrets.token_urlsafe(32))
        self.old_membership = Membership.objects.create(user=self.old_user, organization=self.protected, role='OWNER', is_default=True)
        self.before = self.snapshot()
        self.directory = settings.DEMO_D2_TEST_ROOT / f'delivery-{uuid4().hex}'
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)
        self.delivery = EncryptedTestDelivery(self.directory, encryption_key=secrets.token_bytes(32))
        self.key = secrets.token_bytes(32)

    def snapshot(self):
        return [list(model._base_manager.order_by('id').values()) for model in (Organization, User, Membership)]

    def create(self, **options):
        return create_d2(self.protected.pk, self.delivery, signing_key=self.key, **options)

    def demo_memberships(self):
        return Membership.objects.exclude(pk=self.old_membership.pk).select_related('user', 'organization')

    def test_exact_counts_and_provenance(self):
        result = self.create()
        self.assertEqual(result, {'state': 'created-D2', 'organizations': 5, 'users': 30, 'memberships': 30})
        self.assertEqual(Organization.objects.count(), 6)
        self.assertEqual(User.objects.count(), 31)
        self.assertEqual(Membership.objects.count(), 31)
        bundle = self.delivery.load()
        for name, count in [('organizations', 5), ('users', 30), ('memberships', 30)]:
            self.assertEqual(len(bundle['receipt']['payload']['inventory'][name]['ids']), count)
        for org in Organization.objects.exclude(pk=self.protected.pk):
            self.assertEqual(json.loads(org.description)['stage'], 'D2')

    def test_roles_one_owner_and_exclusive_memberships(self):
        self.create()
        for (_, code, count, *_), roles in zip(PLAN, ROLES):
            memberships = list(self.demo_memberships().filter(organization__code=code))
            self.assertEqual(len(memberships), count)
            self.assertEqual(Counter(item.role for item in memberships), Counter(roles))
            self.assertEqual(sum(item.role == 'OWNER' for item in memberships), 1)
            for item in memberships:
                self.assertTrue(item.is_default and item.is_active)
                self.assertEqual(Membership._base_manager.filter(user=item.user).count(), 1)
                self.assertTrue(item.user.email.startswith(code.lower() + '.'))
                self.assertFalse(item.user.is_staff or item.user.is_superuser)

    def test_passwords_individual_valid_hashed_and_encrypted_on_disk(self):
        self.create(); bundle = self.delivery.load()
        passwords = [entry['password'] for entry in bundle['credentials']]
        self.assertEqual(len(set(passwords)), 30)
        file_data = self.delivery.final.read_bytes()
        for entry in bundle['credentials']:
            user = User.objects.get(pk=entry['user_uuid'])
            self.assertTrue(user.check_password(entry['password']))
            self.assertNotEqual(user.password, entry['password'])
            identify_hasher(user.password)
            self.assertNotIn(entry['password'].encode(), file_data)
        self.assertFalse(self.delivery.pending.exists())

    def test_existing_rows_unchanged(self):
        self.create()
        for model, old in zip((Organization, User, Membership), self.before):
            self.assertEqual(list(model._base_manager.filter(pk__in=[row['id'] for row in old]).order_by('id').values()), old)

    def test_dry_run_does_not_generate_secrets_or_touch_delivery(self):
        with patch('apps.organizations.demo.d2.secrets.token_urlsafe') as random_password, patch.object(self.delivery, 'stage') as stage:
            self.assertEqual(self.create(dry_run=True)['state'], 'fresh-D2-dry-run')
            random_password.assert_not_called(); stage.assert_not_called()
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_intermediate_service_failure_rolls_back_everything(self):
        from apps.organizations.demo import d2
        original = d2.create_organization
        calls = 0
        def fail(**fields):
            nonlocal calls
            calls += 1
            if calls == 3: raise RuntimeError('secret payload must never escape')
            return original(**fields)
        with patch.object(d2, 'create_organization', fail):
            with self.assertRaises(D2Error) as caught: self.create()
        self.assertNotIn('secret payload', str(caught.exception))
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_stage_failure_rolls_back_everything(self):
        with patch.object(self.delivery, 'stage', side_effect=OSError('sensitive content')):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)

    def test_publication_failure_recovers_without_reseeding_or_new_passwords(self):
        with patch.object(self.delivery, 'publish', side_effect=OSError('sensitive content')):
            with self.assertRaises(DeliveryPending) as caught: self.create()
        self.assertNotIn('sensitive content', str(caught.exception))
        self.assertTrue(self.delivery.pending.exists()); self.assertFalse(self.delivery.final.exists())
        before = self.snapshot(); pending = self.delivery.pending.read_bytes()
        with patch('apps.organizations.demo.d2.secrets.token_urlsafe') as generate:
            self.assertEqual(self.create()['state'], 'recognized-D2'); generate.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.delivery.final.read_bytes(), pending)

    def test_repetition_is_noop(self):
        self.create(); before = self.snapshot(); bundle = self.delivery.final.read_bytes()
        self.assertEqual(self.create()['state'], 'recognized-D2')
        self.assertEqual(self.snapshot(), before); self.assertEqual(self.delivery.final.read_bytes(), bundle)

    def test_altered_dataset_rejected(self):
        self.create()
        User.objects.exclude(pk=self.old_user.pk).filter(pk=self.demo_memberships().first().user_id).update(first_name='Changed')
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_partial_dataset_rejected(self):
        Organization.objects.create(name=PLAN[0][0], code=PLAN[0][1])
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_email_collision_case_insensitive_without_password_change(self):
        user = User.objects.create_user(email='RED01.01@demo.example.com', password=secrets.token_urlsafe(32))
        before = self.snapshot(); password_hash = user.password
        with self.assertRaises(D2Error): self.create()
        user.refresh_from_db(); self.assertEqual(user.password, password_hash)
        self.assertEqual(self.snapshot(), before)

    def test_code_collision_including_inactive_rows(self):
        row = Organization.objects.create(name='Other code', code=PLAN[0][1])
        for _ in range(2):
            before = self.snapshot()
            with self.assertRaises(D2Error): self.create()
            self.assertEqual(self.snapshot(), before)
            row.delete()  # Fixture soft deletion; uniqueness still reserves the code.

    def test_slug_collision(self):
        Organization.objects.create(name='Other slug', code='OTHER', slug='rancho-el-encino-demo')
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_cross_membership_rejected(self):
        self.create(); user = self.demo_memberships().first().user
        Membership.objects.create(user=user, organization=self.protected, role='VIEWER')
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_wrong_signing_key_rejected(self):
        self.create()
        with self.assertRaises(D2Error): create_d2(self.protected.pk, self.delivery, signing_key=secrets.token_bytes(32))

    def test_broken_encrypted_bundle_rejected_without_database_changes(self):
        self.create(); self.delivery.final.write_bytes(b'corrupt encrypted receipt')
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_unknown_environment_or_database_rejected(self):
        with override_settings(SETTINGS_MODULE='config.settings.local'):
            with self.assertRaises(D2Error): test_database()
        with patch.dict(connections['default'].settings_dict, NAME='backend/db.sqlite3'):
            with self.assertRaises(D2Error): test_database()

    def test_command_stays_blocked_even_with_environment_flag(self):
        import os
        with patch.dict(os.environ, {'AGROCORE_ENABLE_DEMO_WRITES': '1'}):
            with self.assertRaises(CommandError): call_command('seed_demo_ranches', '--write', stdout=io.StringIO())
        self.assertEqual(self.snapshot(), self.before)

    def test_membership_validation_failure_rolls_back(self):
        with patch.object(Membership, 'full_clean', side_effect=ValueError('private data')):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)

    def test_password_validation_failure_rolls_back(self):
        with patch('apps.organizations.demo.d2.validate_password', side_effect=ValueError('private password')):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)

    def test_existing_domain_records_untouched_and_no_new_domain_records(self):
        from apps.farms.models import Farm
        from apps.lots.models import Lot
        from apps.catalogs.models import FarmType
        from django.apps import apps
        farm_type, _ = FarmType.objects.get_or_create(code='RANCH', defaults={'name': 'Rancho'})
        farm = Farm.objects.create(organization=self.protected, name='Protected farm', code='OLD-FARM', farm_type=farm_type)
        Lot.objects.create(organization=self.protected, farm=farm, name='Protected lot', code='OLD-LOT')
        labels = ['farms.Farm', 'lots.Lot', 'animals.Animal', 'weights.Weight', 'vaccinations.Vaccination', 'animal_movements.AnimalMovement', 'breeding.BreedingEvent', 'pregnancy.Pregnancy', 'births.Birth', 'production.ProductionRecord']
        models = [apps.get_model(label) for label in labels]
        before = [list(model._base_manager.order_by('id').values()) for model in models]
        self.create()
        self.assertEqual(before, [list(model._base_manager.order_by('id').values()) for model in models])

    def test_pending_receipt_after_rollback_is_rejected_not_reseeded(self):
        real_stage = self.delivery.stage
        def fail_after_stage(bundle):
            real_stage(bundle)
            raise OSError('test failure after durable encrypted stage')
        with patch.object(self.delivery, 'stage', side_effect=fail_after_stage):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)
        self.assertTrue(self.delivery.pending.exists())
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)

    def test_real_file_write_error_rolls_back(self):
        with patch('apps.organizations.demo.delivery.os.open', side_effect=OSError('denied')):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)

    def test_tampered_signed_manifest_rejected(self):
        self.create()
        bundle = self.delivery.load()
        bundle['receipt']['payload']['stage'] = 'D2-partial'
        self.delivery.final.write_bytes(self.delivery.cipher.encrypt(json.dumps(bundle).encode()))
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_missing_receipt_never_adopts_existing_dataset(self):
        self.create(); self.delivery.final.unlink()
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_protected_mutation_during_stage_rolls_back(self):
        def malicious_stage(_bundle):
            Organization.objects.filter(pk=self.protected.pk).update(name='Changed')
        with patch.object(self.delivery, 'stage', side_effect=malicious_stage):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)

    def test_dry_run_pending_bundle_never_publishes(self):
        with patch.object(self.delivery, 'publish', side_effect=OSError('test')):
            with self.assertRaises(DeliveryPending): self.create()
        before = self.snapshot()
        with patch.object(self.delivery, 'publish') as publish:
            self.assertEqual(self.create(dry_run=True)['state'], 'recognized-D2')
            publish.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(self.delivery.pending.exists())

    def test_no_secrets_printed_in_normal_execution(self):
        from contextlib import redirect_stdout, redirect_stderr
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err): self.create()
        self.assertEqual(out.getvalue(), ''); self.assertEqual(err.getvalue(), '')

    def test_commit_failure_preserves_only_unconfirmed_encrypted_bundle(self):
        with patch.object(connections['default'], 'commit', side_effect=OperationalError('commit fault')):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)
        self.assertTrue(self.delivery.pending.exists())
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)

    def test_encryption_failure_rolls_back_without_plaintext_file(self):
        with patch.object(self.delivery.cipher, 'encrypt', side_effect=RuntimeError('test')):
            with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_mismatched_credential_membership_ids_rejected(self):
        self.create(); bundle = self.delivery.load()
        bundle['credentials'][0]['membership_uuid'] = str(uuid4())
        self.delivery.final.write_bytes(self.delivery.cipher.encrypt(json.dumps(bundle).encode()))
        before = self.snapshot()
        with self.assertRaises(D2Error): self.create()
        self.assertEqual(self.snapshot(), before)

    def test_repeat_verification_never_upgrades_or_changes_password_hashes(self):
        self.create(); before = self.snapshot()
        with patch.object(FastTestPBKDF2, 'iterations', 2000):
            self.assertEqual(self.create()['state'], 'recognized-D2')
        self.assertEqual(self.snapshot(), before)

    def test_old_domain_even_with_valid_signed_inventory_is_rejected_without_changes(self):
        from apps.organizations.demo import d2
        self.create(); bundle = self.delivery.load()
        for entry in bundle['credentials']:
            entry['email'] = entry['email'].replace('@demo.example.com', '@demo.invalid')
            User._base_manager.filter(pk=entry['user_uuid']).update(email=entry['email'])
        payload = bundle['receipt']['payload']
        identifiers = {name: value['ids'] for name, value in payload['inventory'].items()}
        payload['inventory'] = d2._inventory(identifiers)
        bundle['receipt']['signature'] = d2._signature(payload, self.key)
        self.delivery.final.write_bytes(self.delivery.cipher.encrypt(json.dumps(bundle).encode()))
        before = self.snapshot(); ciphertext = self.delivery.final.read_bytes()
        with self.assertRaises(D2Error): self.create()
        with self.assertRaises(D2Error): self.create(dry_run=True)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.delivery.final.read_bytes(), ciphertext)

    def test_previous_roble_plan_signature_cannot_adopt_or_update_dataset(self):
        import hashlib
        from apps.organizations.demo import d2
        from apps.organizations.demo.preflight import canonical_json
        self.create(); bundle = self.delivery.load()
        old_plan = (('Rancho El Roble', 'DEMO-V1-ROBLE', 5, 2, 6, 50), *PLAN[1:])
        payload = bundle['receipt']['payload']
        payload['plan_digest'] = hashlib.sha256(canonical_json(old_plan).encode()).hexdigest()
        bundle['receipt']['signature'] = d2._signature(payload, self.key)
        self.delivery.final.write_bytes(self.delivery.cipher.encrypt(json.dumps(bundle).encode()))
        before = self.snapshot(); ciphertext = self.delivery.final.read_bytes()
        with self.assertRaises(D2Error): self.create()
        with self.assertRaises(D2Error): self.create(dry_run=True)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.delivery.final.read_bytes(), ciphertext)
