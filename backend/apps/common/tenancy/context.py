from contextvars import ContextVar


_current_organization = ContextVar(
    "current_organization",
    default=None,
)


def set_current_organization(organization):
    """
    Define la organización actual.
    """

    _current_organization.set(
        organization
    )


def get_current_organization():
    """
    Obtiene la organización actual.
    """

    return _current_organization.get()


def clear_current_organization():
    """
    Limpia el contexto.
    """

    _current_organization.set(None)