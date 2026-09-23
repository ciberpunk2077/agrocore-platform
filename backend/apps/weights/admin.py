from django.contrib import admin

from .models import Weight

@admin.register(Weight)
class WeightAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "animal",
        "weighing_method",
        "date",
        "weight",
        "is_active",
    )

    list_filter = (
        "organization",
        "weighing_method",
        "is_active",
    )

    search_fields = (
        "organization__name",
        "animal__code",
        "animal__name",
    )

    ordering = (
        "-date",
    )