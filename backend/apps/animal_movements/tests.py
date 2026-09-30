from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.animal_movements.api.schemas import AnimalMovementCreateSchema
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
        gender = Gender.objects.create(code="F", name="Hembra")
        cls.status = AnimalStatus.objects.create(code="ACTIVE", name="Activo")
        cls.sold_status = AnimalStatus.objects.create(code="SOLD", name="Vendido")
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
            ValidationError, "La fecha del movimiento no puede ser futura.",
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
