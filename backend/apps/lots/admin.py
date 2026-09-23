from django.contrib import admin

from .models import Lot


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "farm",
        "organization",
        "capacity",
        "is_active",
    )

    list_filter = (
        "organization",
        "farm",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )

    autocomplete_fields = (
        "organization",
        "farm",
    )

    ordering = (
        "farm",
        "name",
    )