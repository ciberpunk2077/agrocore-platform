
"""
Servicios de negocio para el módulo Organizations.

Toda la lógica de negocio debe implementarse aquí y no en los modelos.
"""

from apps.organizations.models.organization import Organization


def create_organization(**data) -> Organization:
    """
    Crea una nueva organización.
    """
    organization = Organization(**data)
    Organization._meta.get_field("timezone").clean(organization.timezone, organization)
    organization.save()
    return organization


def update_organization(
    organization: Organization,
    **data,
) -> Organization:
    """
    Actualiza una organización existente.
    """

    Organization._meta.get_field("timezone").clean(data.get("timezone", organization.timezone), organization)
    for field, value in data.items():
        setattr(organization, field, value)

    organization.save()

    return organization


def deactivate_organization(
    organization: Organization,
) -> Organization:
    """
    Desactiva una organización.
    """

    organization.delete()

    return organization


def restore_organization(
    organization: Organization,
) -> Organization:
    """
    Restaura una organización eliminada.
    """

    organization.restore()

    return organization
