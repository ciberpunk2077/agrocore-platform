class OrganizationError(Exception):
    """Excepción base del módulo Organizations."""


class OrganizationAlreadyExists(OrganizationError):
    """La organización ya existe."""


class OrganizationNotFound(OrganizationError):
    """La organización no existe."""