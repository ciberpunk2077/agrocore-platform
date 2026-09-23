from apps.weights.models import Weight
from apps.animal_movements.models import AnimalMovement
from apps.vaccinations.models import Vaccination
from apps.births.models import Birth
from apps.breeding.models import BreedingEvent
from apps.pregnancy.models import Pregnancy


class TimelineSelector:

    @staticmethod
    def history(context, animal_id):

        events = []

        #
        # Pesajes
        #
        for weight in (
            Weight.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .select_related("weighing_method")
        ):

            events.append({
                "id": weight.id,
                "date": weight.date,
                "event_type": "weight",
                "title": "Pesaje",
                "description": (
                    f"{weight.weight} kg "
                    f"({weight.weighing_method.name})"
                ),
            })

        #
        # Movimientos
        #
        for movement in (
            AnimalMovement.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .select_related(
                "movement_type",
                "origin_lot",
                "destination_lot",
            )
        ):

            origin = (
                movement.origin_lot.name
                if movement.origin_lot
                else "-"
            )

            destination = (
                movement.destination_lot.name
                if movement.destination_lot
                else "-"
            )

            events.append({
                "id": movement.id,
                "date": movement.date,
                "event_type": "movement",
                "title": movement.movement_type.name,
                "description": f"{origin} → {destination}",
            })

        #
        # Vacunaciones
        #
        for vaccination in (
            Vaccination.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
        ):

            description = (
                f"{vaccination.vaccine_name} - "
                f"Dosis: {vaccination.dose}"
            )

            if vaccination.veterinarian:
                description += (
                    f" - Veterinario: "
                    f"{vaccination.veterinarian}"
                )

            events.append({
                "id": vaccination.id,
                "date": vaccination.application_date,
                "event_type": "vaccination",
                "title": "Vacunación",
                "description": description,
            })



        #
        # Partos
        #
        for birth in (
            Birth.objects
            .filter(
                organization=context.organization,
                mother_id=animal_id,
                is_active=True,
            )
            .select_related(
                "calf",
                "calf_gender",
            )
        ):

            calf = (
                birth.calf.name
                or birth.calf.internal_id
                if birth.calf
                else "Sin cría registrada"
               )

            description = (
                f"Cría: {calf} - "
                f"Peso: {birth.birth_weight} kg"
            )

            if birth.calf_gender:
                description += (
                    f" - Sexo: {birth.calf_gender.name}"
           )
 
            if birth.dystocia:
                description += " - Parto con distocia"

            events.append({
                "id": birth.id,
                "date": birth.birth_date,
                "event_type": "birth",
                "title": "Parto",
                "description": description,
            })

        #
        # Eventos reproductivos
        #
        for breeding in (
            BreedingEvent.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
            .select_related(
                "breeding_type",
                "male",
            )
        ):

            description = (
                f"Tipo: {breeding.breeding_type.name}"
            )

            if breeding.male:
                male = (
                    breeding.male.name
                    or breeding.male.internal_id
                )

                description += (
                    f" - Macho: {male}"
                )

            if breeding.expected_birth:
                description += (
                    f" - Parto estimado: "
                    f"{breeding.expected_birth}"
                )

            if breeding.technician:
                description += (
                    f" - Técnico: "
                    f"{breeding.technician}"
                )

            events.append({
                "id": breeding.id,
                "date": breeding.date,
                "event_type": "breeding",
                "title": "Evento reproductivo",
                "description": description,
            })



        #
        # Gestaciones
        #
        for pregnancy in (
            Pregnancy.objects
            .filter(
                organization=context.organization,
                animal_id=animal_id,
                is_active=True,
            )
        ):

            status = pregnancy.get_status_display()

            description = (
                f"Estado: {status} - "
                f"Parto estimado: {pregnancy.expected_birth}"
            )

            if pregnancy.confirmed:
                description += " - Confirmada"
            else:
                description += " - No confirmada"

            events.append({
                "id": pregnancy.id,
                "date": pregnancy.diagnosis_date,
                "event_type": "pregnancy",
                "title": "Diagnóstico de gestación",
                "description": description,
            })




        events.sort(
            key=lambda x: x["date"],
            reverse=True,
        )

        return events