# from apps.pregnancy.models import Pregnancy


# class PregnancySelector:

#     @staticmethod
#     def list():

#         return (
#             Pregnancy.objects
#             .select_related(
#                 "animal",
#                 "breeding",
#             )
#             .filter(
#                 is_active=True,
#             )
#             .order_by(
#                 "-diagnosis_date",
#             )
#         )

#     @staticmethod
#     def get_by_id(pregnancy_id):

#         return (
#             Pregnancy.objects
#             .select_related(
#                 "animal",
#                 "breeding",
#             )
#             .filter(
#                 id=pregnancy_id,
#                 is_active=True,
#             )
#             .first()
#         )

from apps.pregnancy.models import Pregnancy


class PregnancySelector:

    @staticmethod
    def list(context):

        return (
            Pregnancy.objects
            .select_related(
                "animal",
                "breeding",
            )
            .filter(
                organization=context.organization,
                is_active=True,
            )
            .order_by(
                "-diagnosis_date",
            )
        )

    @staticmethod
    def get_by_id(context, pregnancy_id):

        return (
            Pregnancy.objects
            .select_related(
                "animal",
                "breeding",
            )
            .filter(
                id=pregnancy_id,
                organization=context.organization,
                is_active=True,
            )
            .first()
        )