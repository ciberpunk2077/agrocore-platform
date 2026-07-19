from django.db import models
from apps.common.models import SoftDeleteModel


class TestModel(SoftDeleteModel):
    name = models.CharField(max_length=100)

    class Meta:
        app_label = "common"