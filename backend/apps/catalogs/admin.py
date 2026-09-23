from django.contrib import admin

from .models import FarmType
from .models import FarmType, Species, Gender, AnimalStatus, Breed, WeighingMethod, MovementType, BreedingType

@admin.register(FarmType)
class FarmTypeAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "is_active",
    )


    list_filter = (
        "is_active",
    )


    search_fields = (
        "code",
        "name",
    )


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "scientific_name",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
        "scientific_name",
    )

    ordering = (
        "name",
    )

@admin.register(Gender)
class GenderAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )

    ordering = (
        "name",
    )


@admin.register(AnimalStatus)
class AnimalStatusAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )

    ordering = (
        "name",
    )

@admin.register(Breed)
class BreedAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "species",
        "is_active",
    )

    list_filter = (
        "species",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )

    autocomplete_fields = (
        "species",
    )

    ordering = (
        "species",
        "name",
    )


@admin.register(WeighingMethod)
class WeighingMethodAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )

    ordering = (
        "name",
    )

@admin.register(MovementType)
class MovementTypeAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )

    ordering = (
        "name",
    )

@admin.register(BreedingType)
class BreedingTypeAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
    )

    list_filter = (
        "is_active",
    )
