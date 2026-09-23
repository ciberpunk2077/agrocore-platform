from django.db.models import Avg

from apps.weights.models import Weight


class WeightDashboardService:

    @staticmethod
    def average_weight(context):

        return Weight.objects.filter(
            organization=context.organization,
            is_active=True,
        ).aggregate(
            average=Avg("weight"),
        )["average"]