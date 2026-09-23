from django.contrib import admin

from apps.vaccinations.models import Vaccination


@admin.register(Vaccination)
class VaccinationAdmin(admin.ModelAdmin):

    list_display = (
        "animal",
        "vaccine_name",
        "application_date",
        "next_application_date",
        "dose",
        "veterinarian",
        "is_active",
    )

    search_fields = (
        "animal__internal_id",
        "animal__official_tag",
        "vaccine_name",
    )

    list_filter = (
        "application_date",
        "is_active",
    )

    ordering = (
        "-application_date",
    )