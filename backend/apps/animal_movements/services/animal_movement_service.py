from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction

from django.utils import timezone
from apps.animals.models import Animal
from apps.catalogs.models import MovementType, AnimalStatus
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.common.exceptions import BusinessException

from apps.animal_movements.models import AnimalMovement
from apps.common.services import BaseCRUDService




class AnimalMovementService:

    @staticmethod
    @transaction.atomic
    def create(context, data):

        try:

            relations = AnimalMovementService._load_relations(data)

            AnimalMovementService._validate_relations(
                context,
                relations,
            )

            AnimalMovementService._validate_business_rules(
                data,
                relations,
            )

        

            # movement = AnimalMovement.objects.create(
            movement = AnimalMovement(
                organization=context.organization,
                animal=relations["animal"],
                movement_type=relations["movement_type"],
                origin_status=relations["animal"].status,
                origin_farm=relations["origin_farm"],
                origin_lot=relations["origin_lot"],
                destination_farm=relations["destination_farm"],
                destination_lot=relations["destination_lot"],
                date=data.date,
                reason=data.reason,
                notes=data.notes,
            )

            movement.full_clean()
            movement.save()

            AnimalMovementService._update_animal_location(
                relations["animal"],
                relations,
            )

            return movement

        except ObjectDoesNotExist:
            raise ValidationError(
                "Uno de los registros relacionados no existe."
            )

        except ValidationError:
            raise


    @staticmethod
    def _load_relations(data):

        return {
            "animal": Animal.objects.get(id=data.animal_id),
            "movement_type": MovementType.objects.get(id=data.movement_type_id, is_active=True,),
            "origin_farm": (
                Farm.objects.get(id=data.origin_farm_id)
                if data.origin_farm_id else None
            ),
            "origin_lot": (
                Lot.objects.get(id=data.origin_lot_id)
                if data.origin_lot_id else None
            ),
            "destination_farm": (
                Farm.objects.get(id=data.destination_farm_id)
                if data.destination_farm_id else None
            ),
            "destination_lot": (
                Lot.objects.get(id=data.destination_lot_id)
                if data.destination_lot_id else None
            ),
        }

    @staticmethod
    def _validate_relations(
        context, 
        relations,
        validate_current_location=True,
        ):

        animal = relations["animal"]
        origin_farm = relations["origin_farm"]
        origin_lot = relations["origin_lot"]
        destination_farm = relations["destination_farm"]
        destination_lot = relations["destination_lot"]

        if animal.organization_id != context.organization.id:
            raise ValidationError(
                "El animal no pertenece a la organización actual."
            )

        if not animal.is_active:
            raise ValidationError(
                "No es posible registrar movimientos para un animal inactivo."
            )

        # if animal.farm_id != origin_farm.id:
        if (
            validate_current_location
            and origin_farm
            and animal.farm_id != origin_farm.id
        ):
            raise ValidationError(
                "La unidad productiva origen no coincide con la ubicación actual del animal."
            )

        if origin_farm and origin_farm.organization_id != context.organization.id:
            raise ValidationError(
                "La unidad productiva origen no pertenece a la organización."
            )

        if origin_lot and origin_lot.organization_id != context.organization.id:
            raise BusinessException(
                "El lote origen no pertenece a la organización."
            )

        if destination_lot and destination_lot.organization_id != context.organization.id:
            raise BusinessException(
                "El lote destino no pertenece a la organización."
            )

        if origin_farm and not origin_farm.is_active:
            raise ValidationError(
                "La unidad productiva origen está inactiva."
            )

        if destination_farm and not destination_farm.is_active:
            raise ValidationError(
                "La unidad productiva destino está inactiva."
            )

        if origin_lot and not origin_lot.is_active:
            raise ValidationError(
                "El lote origen está inactivo."
            )

        if destination_lot and not destination_lot.is_active:
            raise ValidationError(
                "El lote destino está inactivo."
            )
        

        if origin_lot and not origin_farm:
            raise ValidationError(
                "No se puede indicar un lote origen sin una unidad productiva origen."
            )

        if destination_lot and not destination_farm:
            raise ValidationError(
                "No se puede indicar un lote destino sin una unidad productiva destino."
            )

        if origin_lot and origin_farm:
            if origin_lot.farm_id != origin_farm.id:
                raise ValidationError(
                    "El lote origen no pertenece a la unidad productiva origen."
                )

        if destination_lot and destination_farm:
            if destination_lot.farm_id != destination_farm.id:
                raise ValidationError(
                    "El lote destino no pertenece a la unidad productiva destino."
                )

        if (
            validate_current_location
            and origin_lot
            and animal.lot_id != origin_lot.id
        ):
            raise ValidationError(
                "El animal no se encuentra actualmente en el lote origen."
            )


    @staticmethod
    def _validate_business_rules(data, relations, is_update=False):

        if data.date > timezone.localdate():
            raise ValidationError(
                "La fecha del movimiento no puede ser futura."
            )

        movement_type = relations["movement_type"]

        if movement_type.code == "TRANSFER":
            if (
                not relations["origin_farm"]
                or not relations["origin_lot"]
                or not relations["destination_farm"]
                or not relations["destination_lot"]
            ):
                raise BusinessException(
                    "Un traslado requiere granja y lote de origen y de destino."
                )

        if movement_type.code in ["ENTRY", "PURCHASE"]:
            if (
                not relations["destination_farm"]
                or not relations["destination_lot"]
            ):
                raise BusinessException(
                    "Una entrada o compra requiere granja y lote de destino."
                )

            animal = relations["animal"]

            if (
                not is_update
                and (animal.farm_id or animal.lot_id)
            ):
                raise BusinessException(
                    "No se puede registrar una entrada o compra para un animal que ya tiene una ubicación."
                )


        if movement_type.code in ["EXIT", "SALE"]:
            if (
                not relations["origin_farm"]
                or not relations["origin_lot"]
            ):
                raise BusinessException(
                    "Una salida o venta requiere granja y lote de origen."
                )

            if (
                relations["destination_farm"]
                or relations["destination_lot"]
            ):
                raise BusinessException(
                    "Una salida o venta no debe tener granja ni lote de destino."
                )



        if (
            relations["destination_farm"]
            and not relations["destination_lot"]
        ):
            raise BusinessException(
                "Debe especificarse un lote de destino cuando existe una granja de destino."
            )



        if (
            movement_type.code == "TRANSFER"
            and data.origin_farm_id == data.destination_farm_id
            and data.origin_lot_id == data.destination_lot_id
        ):
            raise BusinessException(
                "El origen y el destino de un traslado no pueden ser iguales."
            )


    @staticmethod
    def _update_animal_location(animal, relations, origin_status=None,):

        movement_type = relations["movement_type"]

        if movement_type.code in ["EXIT", "SALE"]:
            animal.farm = None
            animal.lot = None

        elif relations["destination_farm"]:
            animal.farm = relations["destination_farm"]
            animal.lot = relations["destination_lot"]

        update_fields = [
            "farm",
            "lot",
        ]

        if movement_type.code == "SALE":
            sold_status = AnimalStatus.objects.get(
                code="SOLD",
                is_active=True,
            )

            animal.status = sold_status
            update_fields.append("status")

        elif origin_status:
            animal.status = origin_status
            update_fields.append("status")

        animal.save(
            update_fields=update_fields,
        )


    @staticmethod
    def _is_latest_movement(movement, animal):

        latest_movement = (
            AnimalMovement.objects
            .filter(
                organization=movement.organization,
                animal=animal,
                is_active=True,
            )
            .order_by(
                "-date",
                "-created_at",
            )
            .first()
        )

        return (
            latest_movement is not None
            and latest_movement.id == movement.id
        )


    @staticmethod
    def _validate_is_latest_movement(movement):

        latest_movement = (
            AnimalMovement.objects
            .filter(
                organization=movement.organization,
                animal=movement.animal,
                is_active=True,
            )
            .order_by(
                "-date",
                "-created_at",
            )
            .first()
        )

        if (
            latest_movement is None
            or latest_movement.id != movement.id
        ):
            raise BusinessException(
                "No se puede modificar un movimiento histórico cuando existen movimientos posteriores."
            )


    @staticmethod
    def _validate_updated_date(movement, new_date):

        previous_movement = (
            AnimalMovement.objects
            .filter(
                organization=movement.organization,
                animal=movement.animal,
                is_active=True,
            )
            .exclude(
                id=movement.id,
            )
            .order_by(
                "-date",
                "-created_at",
            )
            .first()
        )

        if (
            previous_movement
            and new_date < previous_movement.date
        ):
            raise BusinessException(
                "La fecha del movimiento no puede ser anterior a otro movimiento existente del animal."
            )


    @staticmethod
    @transaction.atomic
    def update(movement, context, data):

        AnimalMovementService._validate_is_latest_movement(
            movement,
        )

        AnimalMovementService._validate_updated_date(
            movement,
            data.date,
        )

        relations = AnimalMovementService._load_relations(data)

        AnimalMovementService._validate_relations(
            context,
            relations,
            validate_current_location=False,
        )

        AnimalMovementService._validate_business_rules(
            data,
            relations,
            is_update=True,
        )

        if movement.animal_id != relations["animal"].id:
            raise ValidationError(
                "No se puede cambiar el animal de un movimiento existente."
            )

        if (
            movement.origin_farm_id != data.origin_farm_id
            or movement.origin_lot_id != data.origin_lot_id
        ):
            raise BusinessException(
                "No se puede cambiar la ubicación de origen de un movimiento existente."
            )

        movement.animal = relations["animal"]
        movement.movement_type = relations["movement_type"]

        movement.origin_farm = relations["origin_farm"]
        movement.origin_lot = relations["origin_lot"]

        movement.destination_farm = relations["destination_farm"]
        movement.destination_lot = relations["destination_lot"]

        movement.date = data.date
        movement.reason = data.reason
        movement.notes = data.notes

        # is_latest_movement = AnimalMovementService._is_latest_movement(
        #     movement,
        #     relations["animal"],
        # )

        movement.full_clean()
        movement.save()

        AnimalMovementService._update_animal_location(
            relations["animal"],
            relations,
            origin_status=movement.origin_status,
        )

        return movement



    @staticmethod
    @transaction.atomic
    def delete(movement):

        AnimalMovementService._validate_is_latest_movement(
            movement,
        )

        animal = movement.animal
        origin_status = movement.origin_status

        movement = BaseCRUDService.soft_delete(
            movement,
        )

        animal.farm = movement.origin_farm
        animal.lot = movement.origin_lot

        update_fields = [
            "farm",
            "lot",
        ]

        if origin_status:
            animal.status = origin_status
            update_fields.append("status")

        animal.save(
            update_fields=update_fields,
        )

        return movement