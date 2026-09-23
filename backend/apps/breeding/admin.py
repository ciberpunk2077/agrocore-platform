from django.contrib import admin

from .models import BreedingEvent


@admin.register(BreedingEvent)
class BreedingEventAdmin(admin.ModelAdmin):

    list_display = (
        "animal",
        "breeding_type",
        "date",
        "expected_birth",
        "is_active",
    )

    search_fields = (
        "animal__internal_id",
        "animal__official_tag",
    )

    list_filter = (
        "breeding_type",
        "is_active",
    )