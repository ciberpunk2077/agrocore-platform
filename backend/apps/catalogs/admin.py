from django.contrib import admin

from .models import FarmType


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