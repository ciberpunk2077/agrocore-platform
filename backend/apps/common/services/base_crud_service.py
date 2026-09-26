
from django.db import transaction


class BaseCRUDService:

    @staticmethod
    @transaction.atomic
    def soft_delete(instance):

        instance.delete()

        return instance