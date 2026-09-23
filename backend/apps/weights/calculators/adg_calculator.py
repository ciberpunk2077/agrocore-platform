from decimal import Decimal


class ADGCalculator:

    @staticmethod
    def calculate(previous_weight, current_weight):

        if previous_weight is None:
            return None

        days = (current_weight.date - previous_weight.date).days

        if days <= 0:
            return None

        gain = current_weight.weight - previous_weight.weight

        adg = gain / Decimal(days)

        return {
            "previous_weight": previous_weight.weight,
            "current_weight": current_weight.weight,
            "gain": gain,
            "days": days,
            "adg": round(adg, 3),
        }