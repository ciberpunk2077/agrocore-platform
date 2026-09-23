from django.db import transaction


class BaseCRUDService:

    @staticmethod
    @transaction.atomic
    def soft_delete(instance):

        instance.is_active = False

        instance.save(
            update_fields=[
                "is_active",
            ]
        )

        return instance