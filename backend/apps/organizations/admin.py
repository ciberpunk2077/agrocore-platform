from django.contrib import admin

from .models.organization import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "email",
        "phone",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    # search_fields = (
    #     "name",
    #     "code",
    #     "tax_id",
    # )

    # ordering = ("name",)

    search_fields = (
        "name",
        "code",
        "tax_id",
        "email",
    )

    ordering = ("name",)

    readonly_fields = (
        "id",
        "slug",
        "created_at",
        "updated_at",
        "deleted_at",
    )

    fieldsets = (
        (
            "Información General",
            {
                "fields": (
                    "name",
                    "code",
                    "timezone",
                    "slug",
                    "tax_id",
                )
            },
        ),
        (
            "Contacto",
            {
                "fields": (
                    "email",
                    "phone",
                    "website",
                )
            },
        ),
        (
            "Descripción",
            {
                "fields": (
                    "description",
                )
            },
        ),
        (
            "Estado",
            {
                "fields": (
                    "is_active",
                )
            },
        ),
        (
            "Auditoría",
            {
                "classes": ("collapse",),
                "fields": (
                    "id",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                ),
            },
        ),
    )
