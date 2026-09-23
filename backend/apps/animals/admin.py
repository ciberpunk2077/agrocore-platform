from django.contrib import admin

from .models import Animal


@admin.register(Animal)
class AnimalAdmin(admin.ModelAdmin):

    list_display = (
        "internal_id",
        "official_tag",
        "species",
        "breed",
        "gender",
        "status",
        "farm",
        "lot",
        "is_active",
    )

    list_filter = (
        "species",
        "breed",
        "gender",
        "status",
        "farm",
        "lot",
        "is_active",
    )

    search_fields = (
        "internal_id",
        "official_tag",
        "electronic_tag",
        "name",
    )

    autocomplete_fields = (
        "organization",
        "farm",
        "lot",
        "species",
        "breed",
        "gender",
        "status",
        "mother",
        "father",
    )