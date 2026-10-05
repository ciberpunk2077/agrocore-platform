from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.db import IntegrityError, transaction
from uuid import uuid4
from apps.accounts.models import User, Membership
from apps.accounts.services.jwt import create_access_token

from apps.animal_movements.api.schemas import (
    AnimalMovementCreateSchema, AnimalMovementUpdateSchema,
)
from apps.animal_movements.models import AnimalMovement
from apps.animal_movements.services import AnimalMovementService
from apps.animals.models import Animal
from apps.catalogs.models import (
    AnimalStatus, Breed, FarmType, Gender, MovementType, Species,
)
from apps.common.exceptions import BusinessException
from apps.common.context.context import RequestContext
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization


class AnimalMovementChronologyTests(TestCase):
    chronology_message = (
        "La fecha del movimiento debe ser posterior al último movimiento registrado."
    )

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(code="MOV", name="Movements")
        species = Species.objects.create(code="MOV", name="Bovino")
        breed = Breed.objects.create(code="MOV", name="Raza", species=species)
        gender = Gender.objects.create(code="MOV_G", name="Movement fixture gender")
        cls.status = AnimalStatus.objects.get(code="ACTIVE")
        cls.sold_status = AnimalStatus.objects.get(code="SOLD")
        cls.transfer, _ = MovementType.objects.get_or_create(
            code="TRANSFER", defaults={"name": "Traslado"},
        )
        cls.sale, _ = MovementType.objects.get_or_create(
            code="SALE", defaults={"name": "Venta"},
        )
        farm_type = FarmType.objects.create(code="MOV", name="Rancho")
        cls.farm_a = Farm.objects.create(
            organization=cls.organization, farm_type=farm_type, code="A", name="A",
        )
        cls.farm_b = Farm.objects.create(
            organization=cls.organization, farm_type=farm_type, code="B", name="B",
        )
        cls.lot_a = Lot.objects.create(
            organization=cls.organization, farm=cls.farm_a, code="A", name="A",
        )
        cls.lot_b = Lot.objects.create(
            organization=cls.organization, farm=cls.farm_b, code="B", name="B",
        )
        cls.animal = Animal.objects.create(
            organization=cls.organization, species=species, breed=breed,
            gender=gender, status=cls.status, internal_id="MOV-1",
            farm=cls.farm_a, lot=cls.lot_a,
        )

    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.first_date = timezone.localdate() - timedelta(days=10)

    def payload(self, movement_date, **overrides):
        self.animal.refresh_from_db()
        destination_farm, destination_lot = (
            (self.farm_b, self.lot_b)
            if self.animal.farm_id == self.farm_a.id
            else (self.farm_a, self.lot_a)
        )
        data = {
            "animal_id": self.animal.id,
            "movement_type_id": self.transfer.id,
            "origin_farm_id": self.animal.farm_id,
            "origin_lot_id": self.animal.lot_id,
            "destination_farm_id": destination_farm.id,
            "destination_lot_id": destination_lot.id,
            "date": movement_date,
            "reason": "Traslado de prueba",
            "notes": "",
        }
        data.update(overrides)
        return AnimalMovementCreateSchema(**data)

    def create_first(self):
        return AnimalMovementService.create(self.context, self.payload(self.first_date))

    def assert_rejected_without_changes(self, payload, exception, message):
        self.animal.refresh_from_db()
        before = (self.animal.farm_id, self.animal.lot_id, self.animal.status_id)
        movement_ids = set(AnimalMovement._base_manager.values_list("id", flat=True))

        with self.assertRaisesMessage(exception, message):
            AnimalMovementService.create(self.context, payload)

        self.assertEqual(
            set(AnimalMovement._base_manager.values_list("id", flat=True)),
            movement_ids,
        )
        self.animal.refresh_from_db()
        self.assertEqual(
            (self.animal.farm_id, self.animal.lot_id, self.animal.status_id), before,
        )

    def test_first_transfer_is_allowed(self):
        movement = self.create_first()
        self.animal.refresh_from_db()
        self.assertEqual(AnimalMovement.objects.count(), 1)
        self.assertEqual(movement.date, self.first_date)
        self.assertEqual(movement.origin_status_id, self.status.id)
        self.assertEqual(self.animal.farm_id, self.farm_b.id)
        self.assertEqual(self.animal.lot_id, self.lot_b.id)
        self.assertEqual(self.animal.status_id, self.status.id)

    def test_later_transfer_is_allowed(self):
        self.create_first()
        movement = AnimalMovementService.create(
            self.context, self.payload(self.first_date + timedelta(days=1)),
        )
        self.animal.refresh_from_db()
        self.assertEqual(AnimalMovement.objects.count(), 2)
        self.assertEqual(movement.date, self.first_date + timedelta(days=1))
        self.assertEqual(self.animal.farm_id, self.farm_a.id)
        self.assertEqual(self.animal.lot_id, self.lot_a.id)
        self.assertEqual(self.animal.status_id, self.status.id)

    def test_earlier_transfer_is_rejected_without_changes(self):
        self.create_first()
        self.assert_rejected_without_changes(
            self.payload(self.first_date - timedelta(days=1)),
            BusinessException, self.chronology_message,
        )

    def test_same_date_transfer_is_rejected_without_changes(self):
        self.create_first()
        self.assert_rejected_without_changes(
            self.payload(self.first_date), BusinessException, self.chronology_message,
        )

    def test_rejected_sales_preserve_location_and_status(self):
        self.create_first()
        for delta in (-1, 0):
            with self.subTest(days=delta):
                self.assert_rejected_without_changes(
                    self.payload(
                        self.first_date + timedelta(days=delta),
                        movement_type_id=self.sale.id,
                        destination_farm_id=None, destination_lot_id=None,
                    ),
                    BusinessException, self.chronology_message,
                )

    def test_later_sale_clears_location_and_sets_sold_status(self):
        self.create_first()
        AnimalMovementService.create(
            self.context,
            self.payload(
                self.first_date + timedelta(days=1), movement_type_id=self.sale.id,
                destination_farm_id=None, destination_lot_id=None,
            ),
        )
        self.animal.refresh_from_db()
        self.assertEqual(AnimalMovement.objects.count(), 2)
        self.assertIsNone(self.animal.farm_id)
        self.assertIsNone(self.animal.lot_id)
        self.assertEqual(self.animal.status_id, self.sold_status.id)

    def test_future_date_is_still_rejected(self):
        self.create_first()
        self.assert_rejected_without_changes(
            self.payload(timezone.localdate() + timedelta(days=1)),
            BusinessException, "La fecha del movimiento no puede ser futura.",
        )

    def test_deleted_latest_movement_does_not_block_creation(self):
        self.create_first()
        deleted = AnimalMovementService.create(
            self.context, self.payload(self.first_date + timedelta(days=3)),
        )
        AnimalMovementService.delete(deleted)
        deleted.refresh_from_db()
        self.assertFalse(deleted.is_active)
        movement = AnimalMovementService.create(
            self.context, self.payload(self.first_date + timedelta(days=1)),
        )
        self.assertEqual(movement.date, self.first_date + timedelta(days=1))
        self.assertEqual(AnimalMovement.objects.count(), 2)

    def test_only_deleted_history_does_not_block_first_active_movement(self):
        deleted = self.create_first()
        AnimalMovementService.delete(deleted)
        movement = AnimalMovementService.create(
            self.context, self.payload(self.first_date - timedelta(days=1)),
        )
        self.assertEqual(movement.date, self.first_date - timedelta(days=1))
        self.assertEqual(AnimalMovement.objects.count(), 1)

    def test_other_animal_history_does_not_block_creation(self):
        other_animal = Animal.objects.create(
            organization=self.organization, species=self.animal.species,
            breed=self.animal.breed, gender=self.animal.gender,
            status=self.status, internal_id="MOV-2", farm=self.farm_a, lot=self.lot_a,
        )
        AnimalMovementService.create(
            self.context,
            self.payload(self.first_date + timedelta(days=1), animal_id=other_animal.id),
        )
        self.create_first()
        self.assertEqual(AnimalMovement.objects.filter(animal=self.animal).count(), 1)

    def test_transfer_still_requires_destination_lot(self):
        self.assert_rejected_without_changes(
            self.payload(self.first_date, destination_lot_id=None),
            BusinessException, "Un traslado requiere granja y lote de origen y de destino.",
        )

    def test_transfer_still_rejects_identical_origin_and_destination(self):
        self.assert_rejected_without_changes(
            self.payload(
                self.first_date, destination_farm_id=self.farm_a.id,
                destination_lot_id=self.lot_a.id,
            ),
            BusinessException, "El origen y el destino de un traslado no pueden ser iguales.",
        )


class AnimalMovementUpdateContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        AnimalMovementChronologyTests.setUpTestData.__func__(cls)
        for code in ("C", "D"):
            farm = Farm.objects.create(
                organization=cls.organization, farm_type=cls.farm_a.farm_type,
                code=code, name=code,
            )
            lot = Lot.objects.create(
                organization=cls.organization, farm=farm, code=code, name=code,
            )
            setattr(cls, f"farm_{code.lower()}", farm)
            setattr(cls, f"lot_{code.lower()}", lot)
        cls.other_animal = Animal.objects.create(
            organization=cls.organization, species=cls.animal.species,
            breed=cls.animal.breed, gender=cls.animal.gender,
            status=cls.status, internal_id="MOV-OTHER",
            farm=cls.farm_a, lot=cls.lot_a,
        )

    def setUp(self):
        self.context = RequestContext(organization=self.organization)
        self.first_date = timezone.localdate() - timedelta(days=10)

    def create_transfer(self, origin, destination, movement_date):
        return AnimalMovementService.create(
            self.context,
            AnimalMovementCreateSchema(
                animal_id=self.animal.pk, movement_type_id=self.transfer.pk,
                origin_farm_id=getattr(self, f"farm_{origin}").pk,
                origin_lot_id=getattr(self, f"lot_{origin}").pk,
                destination_farm_id=getattr(self, f"farm_{destination}").pk,
                destination_lot_id=getattr(self, f"lot_{destination}").pk,
                date=movement_date, reason="H4 contract", notes="Original notes",
            ),
        )

    def create_chain(self):
        first = self.create_transfer("a", "b", self.first_date)
        last = self.create_transfer("b", "c", self.first_date + timedelta(days=2))
        return first, last

    def update_payload(self, movement, **overrides):
        fields = {
            "animal_id": movement.animal_id,
            "movement_type_id": movement.movement_type_id,
            "origin_farm_id": movement.origin_farm_id,
            "origin_lot_id": movement.origin_lot_id,
            "destination_farm_id": movement.destination_farm_id,
            "destination_lot_id": movement.destination_lot_id,
            "date": movement.date, "reason": movement.reason, "notes": movement.notes,
        }
        fields.update(overrides)
        return AnimalMovementUpdateSchema(**fields)

    def snapshot(self):
        return (
            list(AnimalMovement._base_manager.order_by("id").values()),
            list(Animal._base_manager.order_by("id").values()),
        )

    def assert_update_rejected(self, movement, payload, exception=BusinessException):
        before = self.snapshot()
        with self.assertRaises(exception):
            AnimalMovementService.update(movement, self.context, payload)
        self.assertEqual(self.snapshot(), before)

    def assert_animal_state(self, location, status):
        self.animal.refresh_from_db()
        expected = (
            (getattr(self, f"farm_{location}").pk, getattr(self, f"lot_{location}").pk)
            if location else (None, None)
        )
        self.assertEqual((self.animal.farm_id, self.animal.lot_id), expected)
        self.assertEqual(self.animal.status_id, status.pk)

    def test_put_historical_movement_is_rejected_without_changes(self):
        first, last = self.create_chain()
        self.assert_update_rejected(
            first, self.update_payload(first, date=last.date + timedelta(days=1)),
        )
        self.assert_animal_state("c", self.status)

    def test_delete_historical_movement_is_rejected_without_changes(self):
        first, last = self.create_chain()
        before = self.snapshot()
        with self.assertRaises(BusinessException):
            AnimalMovementService.delete(first)
        self.assertEqual(self.snapshot(), before)
        first.refresh_from_db()
        last.refresh_from_db()
        self.assertTrue(first.is_active)
        self.assertTrue(last.is_active)
        self.assert_animal_state("c", self.status)

    def test_put_latest_date_before_previous_is_rejected_without_changes(self):
        first, last = self.create_chain()
        self.assert_update_rejected(
            last, self.update_payload(last, date=first.date - timedelta(days=1)),
        )

    def test_put_latest_date_equal_to_previous_is_rejected_without_changes(self):
        first, last = self.create_chain()
        self.assert_update_rejected(last, self.update_payload(last, date=first.date))

    def test_put_latest_date_after_previous_is_allowed(self):
        first, last = self.create_chain()
        new_date = first.date + timedelta(days=1)
        AnimalMovementService.update(last, self.context, self.update_payload(last, date=new_date))
        last.refresh_from_db()
        self.assertEqual(last.date, new_date)
        self.assert_animal_state("c", self.status)

    def test_put_latest_destination_synchronizes_animal(self):
        _, last = self.create_chain()
        AnimalMovementService.update(
            last, self.context, self.update_payload(
                last, destination_farm_id=self.farm_d.pk, destination_lot_id=self.lot_d.pk,
            ),
        )
        last.refresh_from_db()
        self.assertEqual((last.origin_farm_id, last.origin_lot_id), (self.farm_b.pk, self.lot_b.pk))
        self.assertEqual((last.destination_farm_id, last.destination_lot_id), (self.farm_d.pk, self.lot_d.pk))
        self.assert_animal_state("d", self.status)

    def test_put_latest_animal_is_immutable(self):
        _, last = self.create_chain()
        self.assert_update_rejected(
            last, self.update_payload(last, animal_id=self.other_animal.pk), BusinessException,
        )

    def test_put_latest_origin_is_immutable(self):
        _, last = self.create_chain()
        for changed in (
            {"origin_farm_id": self.farm_a.pk, "origin_lot_id": self.lot_a.pk},
            {"origin_lot_id": None},
        ):
            with self.subTest(changed=changed):
                self.assert_update_rejected(last, self.update_payload(last, **changed))

    def test_put_latest_transfer_to_sale_reapplies_effects(self):
        _, last = self.create_chain()
        AnimalMovementService.update(
            last, self.context, self.update_payload(
                last, movement_type_id=self.sale.pk,
                destination_farm_id=None, destination_lot_id=None,
            ),
        )
        last.refresh_from_db()
        self.assertEqual(last.movement_type_id, self.sale.pk)
        self.assertIsNone(last.destination_farm_id)
        self.assertIsNone(last.destination_lot_id)
        self.assert_animal_state(None, self.sold_status)

    def create_latest_sale(self):
        self.create_transfer("a", "b", self.first_date)
        return AnimalMovementService.create(
            self.context,
            AnimalMovementCreateSchema(
                animal_id=self.animal.pk, movement_type_id=self.sale.pk,
                origin_farm_id=self.farm_b.pk, origin_lot_id=self.lot_b.pk,
                date=self.first_date + timedelta(days=2), reason="H4 sale", notes="Original notes",
            ),
        )

    def test_put_latest_sale_to_transfer_restores_origin_status(self):
        last = self.create_latest_sale()
        self.assert_animal_state(None, self.sold_status)
        AnimalMovementService.update(
            last, self.context, self.update_payload(
                last, movement_type_id=self.transfer.pk,
                destination_farm_id=self.farm_c.pk, destination_lot_id=self.lot_c.pk,
            ),
        )
        last.refresh_from_db()
        self.assertEqual(last.movement_type_id, self.transfer.pk)
        self.assertEqual((last.destination_farm_id, last.destination_lot_id), (self.farm_c.pk, self.lot_c.pk))
        self.assertEqual(last.origin_status_id, self.status.pk)
        self.assert_animal_state("c", self.status)

    def test_delete_latest_soft_deletes_and_restores_original_state(self):
        last = self.create_latest_sale()
        self.assert_animal_state(None, self.sold_status)
        AnimalMovementService.delete(last)
        last.refresh_from_db()
        self.assertFalse(last.is_active)
        self.assertIsNotNone(last.deleted_at)
        self.assertTrue(AnimalMovement._base_manager.filter(pk=last.pk).exists())
        self.assert_animal_state("b", self.status)

    def test_put_rolls_back_movement_when_animal_save_fails(self):
        _, last = self.create_chain()
        before = self.snapshot()

        def fail_after_movement_save(animal, **kwargs):
            persisted = AnimalMovement._base_manager.get(pk=last.pk)
            self.assertEqual(persisted.destination_lot_id, self.lot_d.pk)
            raise RuntimeError("H4 forced Animal save failure")

        with patch.object(Animal, "save", autospec=True, side_effect=fail_after_movement_save):
            with self.assertRaisesMessage(RuntimeError, "H4 forced Animal save failure"):
                AnimalMovementService.update(
                    last, self.context, self.update_payload(
                        last, destination_farm_id=self.farm_d.pk, destination_lot_id=self.lot_d.pk,
                    ),
                )
        # A real read after rollback verifies the connection is still usable.
        self.assertEqual(self.snapshot(), before)

    def test_put_notes_only_preserves_current_location_and_status(self):
        _, last = self.create_chain()
        for status in (self.status, self.sold_status):
            with self.subTest(current_status=status.code):
                # Animal has an independent editable status. TRANSFER changes
                # location, not status; its destination remains correctly applied.
                self.animal.refresh_from_db()
                self.animal.status = status
                self.animal.save(update_fields=["status"])
                before_state = (self.animal.farm_id, self.animal.lot_id, self.animal.status_id)
                before_movement = AnimalMovement._base_manager.get(pk=last.pk)
                notes = f"Updated notes with current status {status.code}"
                AnimalMovementService.update(
                    last, self.context, self.update_payload(last, notes=notes),
                )
                last.refresh_from_db()
                self.animal.refresh_from_db()
                self.assertEqual(last.notes, notes)
                for field in (
                    "animal_id", "movement_type_id", "origin_status_id", "origin_farm_id",
                    "origin_lot_id", "destination_farm_id", "destination_lot_id", "date", "reason",
                ):
                    self.assertEqual(getattr(last, field), getattr(before_movement, field))
                self.assertEqual(
                    (self.animal.farm_id, self.animal.lot_id, self.animal.status_id), before_state,
                )

    def test_put_destination_only_preserves_divergent_status(self):
        _, last = self.create_chain()
        self.animal.refresh_from_db()
        self.animal.status = self.sold_status
        self.animal.save(update_fields=["status"])
        AnimalMovementService.update(
            last, self.context, self.update_payload(
                last, destination_farm_id=self.farm_d.pk, destination_lot_id=self.lot_d.pk,
            ),
        )
        last.refresh_from_db()
        self.assertEqual(last.destination_lot_id, self.lot_d.pk)
        self.assert_animal_state("d", self.sold_status)

    def test_put_sale_notes_only_preserves_independent_status(self):
        last = self.create_latest_sale()
        self.animal.refresh_from_db()
        self.animal.status = self.status
        self.animal.save(update_fields=["status"])
        AnimalMovementService.update(
            last, self.context, self.update_payload(last, notes="Sale notes corrected"),
        )
        last.refresh_from_db()
        self.assertEqual(last.notes, "Sale notes corrected")
        self.assertEqual(last.movement_type_id, self.sale.pk)
        self.assert_animal_state(None, self.status)

    def test_put_metadata_only_does_not_save_animal(self):
        _, last = self.create_chain()
        for changed in (
            {"notes": "Metadata notes"},
            {"reason": "Metadata reason"},
            {"date": last.date + timedelta(days=1)},
        ):
            with self.subTest(changed=changed):
                before_animal = Animal._base_manager.get(pk=self.animal.pk)
                with patch.object(Animal, "save", autospec=True) as save:
                    AnimalMovementService.update(last, self.context, self.update_payload(last, **changed))
                    save.assert_not_called()
                last.refresh_from_db()
                for field, value in changed.items():
                    self.assertEqual(getattr(last, field), value)
                self.animal.refresh_from_db()
                self.assertEqual(
                    (self.animal.farm_id, self.animal.lot_id, self.animal.status_id),
                    (before_animal.farm_id, before_animal.lot_id, before_animal.status_id),
                )

    def test_put_entry_purchase_exit_preserve_same_type_contract(self):
        for code in ("ENTRY", "PURCHASE", "EXIT"):
            with self.subTest(movement_type=code):
                uses_destination = code != "EXIT"
                animal = Animal.objects.create(
                    organization=self.organization, species=self.animal.species,
                    breed=self.animal.breed, gender=self.animal.gender,
                    status=self.status, internal_id=f"MOV-{code}",
                    farm=None if uses_destination else self.farm_a,
                    lot=None if uses_destination else self.lot_a,
                )
                movement = AnimalMovementService.create(
                    self.context, AnimalMovementCreateSchema(
                        animal_id=animal.pk,
                        movement_type_id=MovementType.objects.get(code=code).pk,
                        origin_farm_id=None if uses_destination else self.farm_a.pk,
                        origin_lot_id=None if uses_destination else self.lot_a.pk,
                        destination_farm_id=self.farm_c.pk if uses_destination else None,
                        destination_lot_id=self.lot_c.pk if uses_destination else None,
                        date=self.first_date, reason="H4 other types", notes="",
                    ),
                )
                animal.refresh_from_db()
                expected_location = (self.farm_c.pk, self.lot_c.pk) if uses_destination else (None, None)
                self.assertEqual((animal.farm_id, animal.lot_id), expected_location)
                animal.status = self.sold_status
                animal.save(update_fields=["status"])
                with patch.object(Animal, "save", autospec=True) as save:
                    AnimalMovementService.update(
                        movement, self.context, self.update_payload(movement, reason="Corrected reason"),
                    )
                    save.assert_not_called()
                movement.refresh_from_db()
                self.assertEqual(movement.reason, "Corrected reason")
                animal.refresh_from_db()
                self.assertEqual((animal.farm_id, animal.lot_id), expected_location)
                self.assertEqual(animal.status_id, self.sold_status.pk)
                if uses_destination:
                    AnimalMovementService.update(
                        movement, self.context, self.update_payload(
                            movement, destination_farm_id=self.farm_d.pk,
                            destination_lot_id=self.lot_d.pk,
                        ),
                    )
                    animal.refresh_from_db()
                    self.assertEqual((animal.farm_id, animal.lot_id), (self.farm_d.pk, self.lot_d.pk))
                    self.assertEqual(animal.status_id, self.sold_status.pk)


class AnimalMovementErrorTranslationHTTPTests(TestCase):
    setUpTestData = classmethod(AnimalMovementUpdateContractTests.setUpTestData.__func__)
    setUp = AnimalMovementUpdateContractTests.setUp
    create_transfer = AnimalMovementUpdateContractTests.create_transfer
    create_chain = AnimalMovementUpdateContractTests.create_chain
    update_payload = AnimalMovementUpdateContractTests.update_payload
    snapshot = AnimalMovementUpdateContractTests.snapshot

    def request(self, method, data, movement=None):
        user, _ = User.objects.get_or_create(email="movement-h5@example.com")
        Membership.objects.get_or_create(user=user, organization=self.organization,
            defaults={"role": Membership.Role.OWNER, "is_default": True})
        path = "/api/animal-movements/" if method == "post" else f"/api/animal-movements/{movement.pk}"
        with transaction.atomic():
            return getattr(self.client, method)(path, data, content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")

    def payload(self, movement=None, **changes):
        data = dict(animal_id=str(self.animal.pk), movement_type_id=str(self.transfer.pk),
            origin_farm_id=str(self.farm_a.pk), origin_lot_id=str(self.lot_a.pk),
            destination_farm_id=str(self.farm_b.pk), destination_lot_id=str(self.lot_b.pk),
            date=self.first_date.isoformat(), reason="HTTP", notes="HTTP")
        if movement:
            data = self.update_payload(movement).model_dump(mode="json")
        data.update(changes)
        return data

    def assert_bad_input(self, method, movement=None, **changes):
        before = self.snapshot()
        response = self.request(method, self.payload(movement, **changes), movement)
        self.assertEqual(response.status_code, 400)
        self.assertIsInstance(response.json()["detail"], str)
        self.assertEqual(self.snapshot(), before)

    def test_future_date_post_and_put_returns_400(self):
        with self.subTest(method="post"):
            self.assert_bad_input("post", date=(timezone.localdate() + timedelta(days=1)).isoformat())
        _, last = self.create_chain()
        with self.subTest(method="put"):
            self.assert_bad_input("put", last, date=(timezone.localdate() + timedelta(days=1)).isoformat())

    def test_missing_animal_post_and_put_returns_400(self):
        with self.subTest(method="post"):
            self.assert_bad_input("post", animal_id=str(uuid4()))
        _, last = self.create_chain()
        with self.subTest(method="put"):
            self.assert_bad_input("put", last, animal_id=str(uuid4()))

    def test_missing_farm_lot_and_type_post_and_put_returns_400(self):
        for field in ("origin_farm_id", "origin_lot_id", "destination_farm_id", "destination_lot_id", "movement_type_id"):
            with self.subTest(method="post", field=field):
                self.assert_bad_input("post", **{field: str(uuid4())})
        _, last = self.create_chain()
        for field in ("destination_farm_id", "destination_lot_id", "movement_type_id"):
            with self.subTest(method="put", field=field):
                self.assert_bad_input("put", last, **{field: str(uuid4())})

    def test_inactive_payload_relations_return_400(self):
        self.other_animal.delete()
        with self.subTest(method="post"):
            self.assert_bad_input("post", animal_id=str(self.other_animal.pk))
        self.farm_d.delete()
        self.assert_bad_input("post", destination_farm_id=str(self.farm_d.pk))
        self.lot_d.delete()
        self.assert_bad_input("post", destination_lot_id=str(self.lot_d.pk))

    def test_cross_tenant_animal_returns_400(self):
        other = Organization.objects.create(code="H5-FOREIGN", name="H5 foreign")
        self.other_animal.organization = other
        self.other_animal.save(update_fields=["organization"])
        self.assert_bad_input("post", animal_id=str(self.other_animal.pk))
        _, last = self.create_chain()
        with self.subTest(method="put"):
            self.assert_bad_input("put", last, animal_id=str(self.other_animal.pk))

    def test_incompatible_farm_lot_returns_400(self):
        with self.subTest(method="post"):
            self.assert_bad_input("post", destination_lot_id=str(self.lot_c.pk))
        _, last = self.create_chain()
        with self.subTest(method="put"):
            self.assert_bad_input("put", last, destination_lot_id=str(self.lot_d.pk))

    def test_cross_tenant_destination_farm_lot_returns_400(self):
        other = Organization.objects.create(code="H5-LOCATIONS", name="H5 foreign locations")
        farm = Farm.objects.create(organization=other, farm_type=self.farm_a.farm_type,
                                   code="FOREIGN", name="Foreign farm")
        lot = Lot.objects.create(organization=other, farm=farm, code="FOREIGN", name="Foreign lot")
        self.assert_bad_input("post", destination_farm_id=str(farm.pk), destination_lot_id=str(lot.pk))
        _, last = self.create_chain()
        self.assert_bad_input("put", last, destination_farm_id=str(farm.pk), destination_lot_id=str(lot.pk))

    def test_foreign_destination_farm_is_rejected_explicitly(self):
        other = Organization.objects.create(code="DEST-FOREIGN", name="Foreign destination")
        farm = Farm.objects.create(
            organization=other, farm_type=self.farm_a.farm_type,
            code="DEST", name="Foreign destination farm",
        )
        before = self.snapshot()
        response = self.request("post", self.payload(
            destination_farm_id=str(farm.pk), destination_lot_id=None,
        ))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {
            "detail": "La unidad productiva destino no pertenece a la organización.",
        })
        self.assertEqual(self.snapshot(), before)

    def test_inconsistent_local_lot_cannot_bypass_destination_farm_tenant(self):
        other = Organization.objects.create(code="DEST-INCONSISTENT", name="Foreign farm tenant")
        farm = Farm.objects.create(
            organization=other, farm_type=self.farm_a.farm_type,
            code="DEST", name="Foreign farm",
        )
        # Deliberately inconsistent fixture: local lot linked to a foreign farm.
        lot = Lot.objects.create(
            organization=self.organization, farm=farm, code="INCONSISTENT", name="Local lot",
        )
        changes = dict(destination_farm_id=str(farm.pk), destination_lot_id=str(lot.pk))
        data = AnimalMovementCreateSchema(**self.payload(**changes))
        before = self.snapshot()
        with self.assertRaisesMessage(
            BusinessException, "La unidad productiva destino no pertenece a la organización.",
        ):
            AnimalMovementService.create(self.context, data)
        self.assertEqual(self.snapshot(), before)
        for method in ("post", "put"):
            movement = self.create_chain()[1] if method == "put" else None
            with self.subTest(method=method):
                before = self.snapshot()
                response = self.request(method, self.payload(movement, **changes), movement)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {
                    "detail": "La unidad productiva destino no pertenece a la organización.",
                })
                self.assertEqual(self.snapshot(), before)

    def test_same_tenant_create_types_and_same_farm_transfer_remain_valid(self):
        second_lot = Lot.objects.create(
            organization=self.organization, farm=self.farm_a, code="SAME-FARM", name="Second lot",
        )
        for code, same_farm in (
            ("TRANSFER", False), ("TRANSFER", True), ("ENTRY", False),
            ("PURCHASE", False), ("EXIT", False), ("SALE", False),
        ):
            with self.subTest(code=code, same_farm=same_farm):
                has_origin = code not in ("ENTRY", "PURCHASE")
                has_destination = code not in ("EXIT", "SALE")
                animal = Animal.objects.create(
                    organization=self.organization, species=self.animal.species,
                    breed=self.animal.breed, gender=self.animal.gender, status=self.status,
                    internal_id=f"DEST-{code}-{same_farm}",
                    farm=self.farm_a if has_origin else None,
                    lot=self.lot_a if has_origin else None,
                )
                destination_farm = self.farm_a if same_farm else self.farm_b
                destination_lot = second_lot if same_farm else self.lot_b
                response = self.request("post", self.payload(
                    animal_id=str(animal.pk),
                    movement_type_id=str(MovementType.objects.get(code=code).pk),
                    origin_farm_id=str(self.farm_a.pk) if has_origin else None,
                    origin_lot_id=str(self.lot_a.pk) if has_origin else None,
                    destination_farm_id=str(destination_farm.pk) if has_destination else None,
                    destination_lot_id=str(destination_lot.pk) if has_destination else None,
                ))
                self.assertEqual(response.status_code, 200)
                movement = AnimalMovement.objects.get(pk=response.json()["id"])
                self.assertEqual(movement.organization_id, self.organization.pk)
                self.assertEqual(movement.origin_status_id, self.status.pk)
                animal.refresh_from_db()
                self.assertEqual(
                    (animal.farm_id, animal.lot_id),
                    (destination_farm.pk, destination_lot.pk) if has_destination else (None, None),
                )
                self.assertEqual(animal.status_id, self.sold_status.pk if code == "SALE" else self.status.pk)

    def test_post_omitted_texts_are_empty(self):
        data = self.payload()
        data.pop("reason")
        data.pop("notes")
        response = self.request("post", data)
        self.assertEqual(response.status_code, 200)
        movement = AnimalMovement._base_manager.get(pk=response.json()["id"])
        self.assertEqual((movement.reason, movement.notes), ("", ""))

    def test_put_null_texts_are_empty(self):
        _, last = self.create_chain()
        state = self.snapshot()[1]
        response = self.request("put", self.payload(last, reason=None, notes=None), last)
        self.assertEqual(response.status_code, 200)
        last.refresh_from_db()
        self.assertEqual((last.reason, last.notes), ("", ""))
        self.assertEqual(self.snapshot()[1], state)

    def test_reason_length_post_and_put_returns_400(self):
        with self.subTest(method="post"):
            self.assert_bad_input("post", reason="x" * 256)
        _, last = self.create_chain()
        with self.subTest(method="put"):
            self.assert_bad_input("put", last, reason="x" * 256)

    def test_unrelated_full_clean_validation_propagates(self):
        _, last = self.create_chain()
        for errors in (
            {"notes": ValidationError("Unknown", code="unexpected")},
            {"organization": ValidationError("Wrong field", code="invalid")},
            {"reason": ValidationError("Unknown", code="unexpected")},
            {
                "reason": ValidationError("Known length", code="max_length"),
                "notes": ValidationError("Unknown", code="unexpected"),
            },
        ):
            for method in ("post", "put"):
                with self.subTest(errors=errors, method=method):
                    error = ValidationError(errors)
                    before = self.snapshot()
                    with patch.object(AnimalMovement, "full_clean", side_effect=error):
                        with self.assertRaises(ValidationError) as caught:
                            self.request(method, self.payload(last) if method == "put" else self.payload(
                                origin_farm_id=str(self.farm_c.pk), origin_lot_id=str(self.lot_c.pk),
                                date=timezone.localdate().isoformat()), last)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(self.snapshot(), before)

    def test_internal_sold_dependency_does_not_exist_propagates(self):
        _, last = self.create_chain()
        error = AnimalStatus.DoesNotExist("Internal SOLD missing")
        for method in ("post", "put"):
            with self.subTest(method=method):
                before = self.snapshot()
                data = self.payload(last, movement_type_id=str(self.sale.pk),
                    destination_farm_id=None, destination_lot_id=None)
                if method == "post":
                    data.update(origin_farm_id=str(self.farm_c.pk), origin_lot_id=str(self.lot_c.pk), date=timezone.localdate().isoformat())
                with patch.object(AnimalStatus.objects, "get", side_effect=error):
                    with self.assertRaises(AnimalStatus.DoesNotExist) as caught:
                        self.request(method, data, last)
                self.assertIs(caught.exception, error)
                self.assertEqual(self.snapshot(), before)

    def test_unrelated_integrity_error_propagates(self):
        _, last = self.create_chain()
        for method in ("post", "put"):
            with self.subTest(method=method):
                before = self.snapshot()
                error = IntegrityError("Unrelated database failure")
                with patch.object(AnimalMovement, "save", side_effect=error):
                    with self.assertRaises(IntegrityError) as caught:
                        self.request(method, self.payload(last) if method == "put" else self.payload(
                            origin_farm_id=str(self.farm_c.pk), origin_lot_id=str(self.lot_c.pk),
                            date=timezone.localdate().isoformat()), last)
                self.assertIs(caught.exception, error)
                self.assertEqual(self.snapshot(), before)

    def test_schema_errors_remain_422_and_missing_endpoint_remains_404(self):
        response = self.request("post", self.payload(animal_id="invalid"))
        self.assertEqual(response.status_code, 422)
        missing = AnimalMovement(pk=uuid4())
        response = self.request("put", self.payload(), missing)
        self.assertEqual(response.status_code, 404)


class AnimalMovementDetailUpdateCertificationTests(TestCase):
    setUpTestData = classmethod(AnimalMovementUpdateContractTests.setUpTestData.__func__)
    setUp = AnimalMovementUpdateContractTests.setUp
    create_transfer = AnimalMovementUpdateContractTests.create_transfer
    create_chain = AnimalMovementUpdateContractTests.create_chain
    update_payload = AnimalMovementUpdateContractTests.update_payload
    snapshot = AnimalMovementUpdateContractTests.snapshot
    assert_animal_state = AnimalMovementUpdateContractTests.assert_animal_state
    create_latest_sale = AnimalMovementUpdateContractTests.create_latest_sale
    request = AnimalMovementErrorTranslationHTTPTests.request

    def test_detail_and_history_share_complete_schema(self):
        _, last = self.create_chain()
        response = self.request("get", {}, last)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {
            "id", "animal_id", "movement_type_id", "origin_status_id", "origin_farm_id",
            "origin_lot_id", "destination_farm_id", "destination_lot_id", "date", "reason", "notes",
        })
        user = User.objects.get(email="movement-h5@example.com")
        history = self.client.get(
            f"/api/animal-movements/animal/{self.animal.pk}/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}",
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0], response.json())

    def test_detail_missing_foreign_deleted_and_invalid_uuid(self):
        _, last = self.create_chain()
        foreign_org = Organization.objects.create(code="DETAIL-FOREIGN", name="Foreign")
        foreign = AnimalMovement.objects.create(
            organization=foreign_org, animal=self.animal, movement_type=self.transfer, date=self.first_date,
        )
        for movement in (foreign, AnimalMovement(pk=uuid4())):
            with self.subTest(movement=movement.pk):
                self.assertEqual(self.request("get", {}, movement).status_code, 404)
        last.delete()
        self.assertEqual(self.request("get", {}, last).status_code, 404)
        user = User.objects.get(email="movement-h5@example.com")
        response = self.client.get("/api/animal-movements/invalid",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        self.assertEqual(response.status_code, 422)

    def test_detail_remains_readable_with_inactive_animal_and_relations(self):
        _, last = self.create_chain()
        self.animal.delete()
        self.farm_b.delete()
        self.lot_b.delete()
        self.transfer.delete()
        response = self.request("get", {}, last)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["animal_id"], str(self.animal.pk))
        self.assertEqual(response.json()["origin_farm_id"], str(self.farm_b.pk))
        self.assertEqual(response.json()["movement_type_id"], str(self.transfer.pk))

    def test_inactive_historical_origin_blocks_metadata_put_without_changes(self):
        _, last = self.create_chain()
        self.farm_b.delete()
        before = self.snapshot()
        response = self.request("put", self.update_payload(last, notes="Metadata").model_dump(mode="json"), last)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_transfer_exit_transfer_reapplies_destination_and_snapshot(self):
        _, last = self.create_chain()
        exit_type = MovementType.objects.get(code="EXIT")
        AnimalMovementService.update(last, self.context, self.update_payload(
            last, movement_type_id=exit_type.pk, destination_farm_id=None, destination_lot_id=None,
        ))
        self.assert_animal_state(None, self.status)
        AnimalMovementService.update(last, self.context, self.update_payload(
            last, movement_type_id=self.transfer.pk, destination_farm_id=self.farm_d.pk, destination_lot_id=self.lot_d.pk,
        ))
        self.assert_animal_state("d", self.status)
        last.refresh_from_db()
        self.assertEqual(last.origin_farm_id, self.farm_b.pk)
        self.assertEqual(last.origin_status_id, self.status.pk)

    def test_update_to_entry_purchase_preserves_nonnull_historical_origin(self):
        _, last = self.create_chain()
        for code in ("ENTRY", "PURCHASE"):
            with self.subTest(code=code):
                AnimalMovementService.update(last, self.context, self.update_payload(
                    last, movement_type_id=MovementType.objects.get(code=code).pk,
                    destination_farm_id=self.farm_d.pk, destination_lot_id=self.lot_d.pk,
                ))
                last.refresh_from_db()
                self.assertEqual((last.origin_farm_id, last.origin_lot_id), (self.farm_b.pk, self.lot_b.pk))
                self.assert_animal_state("d", self.status)

    def test_entry_purchase_null_origin_cannot_be_added_for_transfer_exit_sale(self):
        for code in ("ENTRY", "PURCHASE"):
            animal = Animal.objects.create(
                organization=self.organization, species=self.animal.species, breed=self.animal.breed,
                gender=self.animal.gender, status=self.status, internal_id=f"CERT-{code}",
            )
            movement = AnimalMovementService.create(self.context, AnimalMovementCreateSchema(
                animal_id=animal.pk, movement_type_id=MovementType.objects.get(code=code).pk,
                destination_farm_id=self.farm_a.pk, destination_lot_id=self.lot_a.pk, date=self.first_date,
            ))
            for target in ("TRANSFER", "EXIT", "SALE"):
                with self.subTest(code=code, target=target):
                    before = self.snapshot()
                    with self.assertRaises(BusinessException):
                        AnimalMovementService.update(movement, self.context, self.update_payload(
                            movement, movement_type_id=MovementType.objects.get(code=target).pk,
                            origin_farm_id=self.farm_a.pk, origin_lot_id=self.lot_a.pk,
                            destination_farm_id=self.farm_b.pk if target == "TRANSFER" else None,
                            destination_lot_id=self.lot_b.pk if target == "TRANSFER" else None,
                        ))
                    self.assertEqual(self.snapshot(), before)

    def test_null_status_snapshot_preserves_current_status_on_type_change(self):
        last = self.create_latest_sale()
        AnimalMovement._base_manager.filter(pk=last.pk).update(origin_status=None)
        last.refresh_from_db()
        AnimalMovementService.update(last, self.context, self.update_payload(
            last, movement_type_id=self.transfer.pk, destination_farm_id=self.farm_c.pk, destination_lot_id=self.lot_c.pk,
        ))
        self.assert_animal_state("c", self.sold_status)
        last.refresh_from_db()
        self.assertIsNone(last.origin_status_id)

    def test_inactive_status_snapshot_is_restored_without_frontend_repair(self):
        last = self.create_latest_sale()
        self.status.delete()
        AnimalMovementService.update(last, self.context, self.update_payload(
            last, movement_type_id=self.transfer.pk, destination_farm_id=self.farm_c.pk, destination_lot_id=self.lot_c.pk,
        ))
        self.assert_animal_state("c", self.status)
        last.refresh_from_db()
        self.assertEqual(last.origin_status_id, self.status.pk)

    def test_same_date_uses_created_at_to_choose_latest_and_date_must_move_forward(self):
        first = self.create_transfer("a", "b", self.first_date)
        last = AnimalMovement.objects.create(
            organization=self.organization, animal=self.animal, movement_type=self.transfer,
            origin_status=self.status, origin_farm=self.farm_b, origin_lot=self.lot_b,
            destination_farm=self.farm_c, destination_lot=self.lot_c, date=self.first_date,
        )
        AnimalMovement._base_manager.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
        before = self.snapshot()
        with self.assertRaises(BusinessException):
            AnimalMovementService.update(first, self.context, self.update_payload(first))
        with self.assertRaises(BusinessException):
            AnimalMovementService.update(last, self.context, self.update_payload(last))
        self.assertEqual(self.snapshot(), before)
        AnimalMovementService.update(last, self.context, self.update_payload(last, date=self.first_date + timedelta(days=1)))
        last.refresh_from_db()
        self.assertEqual(last.date, self.first_date + timedelta(days=1))


class AnimalMovementDeleteCertificationTests(TestCase):
    setUpTestData = classmethod(AnimalMovementUpdateContractTests.setUpTestData.__func__)
    setUp = AnimalMovementUpdateContractTests.setUp
    create_transfer = AnimalMovementUpdateContractTests.create_transfer
    create_chain = AnimalMovementUpdateContractTests.create_chain
    update_payload = AnimalMovementUpdateContractTests.update_payload
    snapshot = AnimalMovementUpdateContractTests.snapshot
    create_latest_sale = AnimalMovementUpdateContractTests.create_latest_sale
    request = AnimalMovementErrorTranslationHTTPTests.request
    assert_animal_state = AnimalMovementUpdateContractTests.assert_animal_state

    def test_all_types_restore_original_location_and_status(self):
        for code in ("TRANSFER", "ENTRY", "PURCHASE", "EXIT", "SALE"):
            with self.subTest(code=code):
                has_origin = code not in ("ENTRY", "PURCHASE")
                destination = code not in ("EXIT", "SALE")
                animal = Animal.objects.create(
                    organization=self.organization, species=self.animal.species, breed=self.animal.breed,
                    gender=self.animal.gender, status=self.status, internal_id=f"DEL-{code}",
                    farm=self.farm_a if has_origin else None, lot=self.lot_a if has_origin else None,
                )
                movement = AnimalMovementService.create(self.context, AnimalMovementCreateSchema(
                    animal_id=animal.pk, movement_type_id=MovementType.objects.get(code=code).pk,
                    origin_farm_id=self.farm_a.pk if has_origin else None,
                    origin_lot_id=self.lot_a.pk if has_origin else None,
                    destination_farm_id=self.farm_b.pk if destination else None,
                    destination_lot_id=self.lot_b.pk if destination else None, date=self.first_date,
                ))
                AnimalMovementService.delete(movement)
                animal.refresh_from_db()
                self.assertEqual((animal.farm_id, animal.lot_id), (self.farm_a.pk, self.lot_a.pk) if has_origin else (None, None))
                self.assertEqual(animal.status_id, self.status.pk)
                movement.refresh_from_db()
                self.assertFalse(movement.is_active)
                self.assertIsNotNone(movement.deleted_at)
                self.assertTrue(AnimalMovement._base_manager.filter(pk=movement.pk).exists())

    def test_delete_after_update_keeps_original_snapshot(self):
        for source, target in (("TRANSFER", "SALE"), ("SALE", "TRANSFER"), ("TRANSFER", "EXIT"), ("TRANSFER", "PURCHASE")):
            with self.subTest(source=source, target=target):
                # Each scenario runs in a savepoint rolled back to an identical fixture.
                with transaction.atomic():
                    movement = self.create_latest_sale() if source == "SALE" else self.create_chain()[1]
                    AnimalMovementService.update(movement, self.context, self.update_payload(
                        movement, movement_type_id=MovementType.objects.get(code=target).pk,
                        destination_farm_id=None if target in ("SALE", "EXIT") else self.farm_d.pk,
                        destination_lot_id=None if target in ("SALE", "EXIT") else self.lot_d.pk,
                    ))
                    AnimalMovementService.delete(movement)
                    self.assert_animal_state("b", self.status)
                    transaction.set_rollback(True)

    def test_null_status_snapshot_preserves_current_status(self):
        movement = self.create_latest_sale()
        AnimalMovement._base_manager.filter(pk=movement.pk).update(origin_status=None)
        movement.refresh_from_db()
        AnimalMovementService.delete(movement)
        self.assert_animal_state("b", self.sold_status)

    def test_inactive_status_snapshot_is_restored(self):
        movement = self.create_latest_sale()
        self.status.delete()
        AnimalMovementService.delete(movement)
        self.assert_animal_state("b", self.status)

    def test_independent_status_and_location_are_overwritten_by_snapshot(self):
        _, movement = self.create_chain()
        self.animal.refresh_from_db()
        self.animal.status = self.sold_status
        self.animal.farm = self.farm_d
        self.animal.lot = self.lot_d
        self.animal.save(update_fields=["farm", "lot", "status"])
        response = self.request("delete", {}, movement)
        self.assertEqual(response.status_code, 200)
        self.assert_animal_state("b", self.status)

    def test_inactive_historical_relations_do_not_block_restoration(self):
        _, movement = self.create_chain()
        for relation in (self.farm_b, self.lot_b, self.farm_c, self.lot_c, self.status):
            relation.delete()
        response = self.request("delete", {}, movement)
        self.assertEqual(response.status_code, 200)
        self.assert_animal_state("b", self.status)
        self.animal.refresh_from_db()
        self.assertFalse(self.animal.farm.is_active)
        self.assertFalse(self.animal.lot.is_active)
        self.assertFalse(self.animal.status.is_active)

    def test_inactive_animal_is_mutated_but_not_reactivated(self):
        _, movement = self.create_chain()
        self.animal.delete()
        response = self.request("delete", {}, movement)
        self.assertEqual(response.status_code, 200)
        self.assert_animal_state("b", self.status)
        self.assertFalse(self.animal.is_active)
        self.assertIsNotNone(self.animal.deleted_at)

    def test_animal_failure_rolls_back_soft_delete(self):
        _, movement = self.create_chain()
        before = self.snapshot()
        with patch.object(Animal, "save", autospec=True, side_effect=RuntimeError("Delete Animal failure")):
            with self.assertRaisesMessage(RuntimeError, "Delete Animal failure"):
                AnimalMovementService.delete(movement)
        self.assertEqual(self.snapshot(), before)
        movement.refresh_from_db()
        self.assertTrue(movement.is_active)
        self.assertIsNone(movement.deleted_at)

    def test_soft_delete_failure_rolls_back_and_does_not_save_animal(self):
        _, movement = self.create_chain()
        before = self.snapshot()
        with patch.object(AnimalMovement, "save", autospec=True, side_effect=IntegrityError("Delete movement failure")):
            with patch.object(Animal, "save", autospec=True) as save_animal:
                with self.assertRaisesMessage(IntegrityError, "Delete movement failure"):
                    AnimalMovementService.delete(movement)
                save_animal.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_http_contract_repeat_and_reads_after_delete(self):
        _, movement = self.create_chain()
        response = self.request("delete", {}, movement)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        movement.refresh_from_db()
        self.assertFalse(movement.is_active)
        self.assertIsNotNone(movement.deleted_at)
        before = self.snapshot()
        self.assertEqual(self.request("delete", {}, movement).status_code, 404)
        self.assertEqual(self.request("get", {}, movement).status_code, 404)
        self.assertEqual(self.snapshot(), before)
        user = User.objects.get(email="movement-h5@example.com")
        history = self.client.get(f"/api/animal-movements/animal/{self.animal.pk}/history",
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        self.assertEqual(history.status_code, 200)
        self.assertNotIn(str(movement.pk), [m["id"] for m in history.json()])

    def test_foreign_tenant_and_historical_delete_do_not_mutate(self):
        first, last = self.create_chain()
        other = Organization.objects.create(code="DELETE-FOREIGN", name="Foreign")
        foreign = AnimalMovement.objects.create(organization=other, animal=self.other_animal,
            movement_type=self.transfer, date=self.first_date)
        before = self.snapshot()
        self.assertEqual(self.request("delete", {}, foreign).status_code, 404)
        self.assertEqual(self.request("delete", {}, first).status_code, 400)
        self.assertEqual(self.snapshot(), before)
        last.refresh_from_db()
        self.assertTrue(last.is_active)

    def test_writer_roles_can_delete_and_viewer_cannot(self):
        for role in (Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.VETERINARIAN, Membership.Role.OPERATOR, Membership.Role.VIEWER):
            with self.subTest(role=role), transaction.atomic():
                _, movement = self.create_chain()
                user = User.objects.create(email=f"delete-{role}@example.com")
                Membership.objects.create(user=user, organization=self.organization, role=role, is_default=True)
                before = self.snapshot()
                response = self.client.delete(f"/api/animal-movements/{movement.pk}",
                    HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
                self.assertEqual(response.status_code, 403 if role == Membership.Role.VIEWER else 200)
                if role == Membership.Role.VIEWER:
                    self.assertEqual(self.snapshot(), before)
                transaction.set_rollback(True)
