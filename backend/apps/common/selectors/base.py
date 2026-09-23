class BaseSelector:
    """
    Selector base para consultas simples.
    """

    model = None

    @classmethod
    def get_queryset(cls):
        return cls.model.objects.all()

    @classmethod
    def get_by_id(cls, id):
        return cls.get_queryset().filter(
            id=id,
        ).first()

    @classmethod
    def list(cls):
        return cls.get_queryset()