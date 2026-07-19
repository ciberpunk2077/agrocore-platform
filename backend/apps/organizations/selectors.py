# """
# Consultas del módulo Organizations.
# """

# from apps.organizations.models import Organization


# def get_organization_by_id(id):
#     """
#     Obtiene una organización por su UUID.
#     """
#     return Organization.objects.filter(id=id).first()


# def get_organization_by_code(code):
#     """
#     Obtiene una organización por su código.
#     """
#     return Organization.objects.filter(code=code).first()


# def list_active_organizations():
#     """
#     Lista únicamente organizaciones activas.
#     """
#     return Organization.objects.filter(is_active=True)

"""
Consultas del módulo Organizations.
"""

from django.db.models import QuerySet

from apps.organizations.models.organization import Organization


def list_organizations() -> QuerySet[Organization]:
    """
    Retorna todas las organizaciones.
    """
    return Organization.objects.all()


def list_active_organizations() -> QuerySet[Organization]:
    """
    Retorna únicamente organizaciones activas.
    """
    return Organization.objects.filter(
        is_active=True
    )


def get_organization_by_id(
    organization_id,
) -> Organization | None:
    """
    Busca una organización por UUID.
    """
    return Organization.objects.filter(
        id=organization_id
    ).first()


def get_organization_by_code(
    code: str,
) -> Organization | None:
    """
    Busca una organización por código.
    """
    return Organization.objects.filter(
        code=code
    ).first()