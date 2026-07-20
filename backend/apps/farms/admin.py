from django.contrib import admin

from .models import Farm


# @admin.register(Farm)
# class FarmAdmin(admin.ModelAdmin):

#     list_display = (
#         "code",
#         "name",
#         "organization",
#         "farm_type",
#         "is_active",
#     )

#     list_filter = (
#         "farm_type",
#         "organization",
#         "is_active",
#     )

#     search_fields = (
#         "code",
#         "name",
#     )

#     ordering = (
#         "name",
#     )

@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "name",
        "organization",
        "farm_type",
        "city",
        "is_active",
    )

    list_filter = (
        "organization",
        "farm_type",
        "is_active",
    )

    search_fields = (
        "code",
        "name",
        "city",
    )

    ordering = (
        "organization",
        "name",
    )

    autocomplete_fields = (
        "organization",
        "farm_type",
    )