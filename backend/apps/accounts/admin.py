
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Membership


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Administración personalizada de usuarios.
    """

    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "created_at",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = (
        "email",
        "first_name",
        "last_name",
    )

    ordering = (
        "email",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "last_login",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "password",
                )
            },
        ),
        (
            "Información personal",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone",
                    "avatar",
                )
            },
        ),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Fechas importantes",
            {
                "fields": (
                    "last_login",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": (
                    "wide",
                ),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                ),
            },
        ),
    )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    """
    Administración de las membresías de usuarios.
    """

    list_display = (
        "user",
        "organization",
        "role",
        "is_default",
        "is_active",
        "created_at",
    )

    list_filter = (
        "role",
        "is_default",
        "is_active",
    )

    search_fields = (
        "user__email",
        "organization__name",
    )

    autocomplete_fields = (
        "user",
        "organization",
    )

    ordering = (
        "organization",
        "user",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )