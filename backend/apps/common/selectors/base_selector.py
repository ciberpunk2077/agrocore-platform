class BaseSelector:

    model = None

    @classmethod
    def list(cls):

        return cls.model.objects.filter(
            is_active=True,
        )

    @classmethod
    def get_by_id(cls, object_id):

        return cls.model.objects.filter(
            id=object_id,
            is_active=True,
        ).first()