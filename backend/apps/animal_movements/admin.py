from django.contrib import admin

from apps.animal_movements.models import AnimalMovement


@admin.register(AnimalMovement)
class AnimalMovementAdmin(admin.ModelAdmin):

    list_display = (
        "animal",
        "movement_type",
        "date",
        "origin_lot",
        "destination_lot",
        "is_active",
    )

    list_filter = (
        "movement_type",
        "is_active",
    )

    search_fields = (
        "animal__internal_id",
        "animal__official_tag",
        "reason",
    )

    autocomplete_fields = (
        "organization",
        "animal",
        "movement_type",
        "origin_farm",
        "origin_lot",
        "destination_farm",
        "destination_lot",
    )

    ordering = (
        "-date",
    )