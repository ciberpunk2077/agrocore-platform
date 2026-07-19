from apps.organizations.models.organization import Organization


def validate_unique_code(code: str):
    """
    Valida que el código de organización no exista.
    """
    if Organization.objects.filter(code=code).exists():
        raise ValueError(
            "Ya existe una organización con ese código."
        )