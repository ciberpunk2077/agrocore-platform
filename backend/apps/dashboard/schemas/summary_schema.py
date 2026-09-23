from decimal import Decimal

from ninja import Schema


class DashboardSummarySchema(Schema):

    total_animals: int

    active_animals: int

    pregnancies: int

    births_this_month: int

    upcoming_births: int

    vaccinations_due: int

    average_weight: Decimal | None