from apps.production.models import ProductionRecord


class ProductionSelector:

    @staticmethod
    def list(context):
        return (
            ProductionRecord.objects
            .select_related("animal", "production_type")
            .filter(organization=context.organization, is_active=True)
        )

    @staticmethod
    def get_by_id(context, record_id):
        return ProductionSelector.list(context).filter(id=record_id).first()

    @staticmethod
    def history(context, animal_id):
        return ProductionSelector.list(context).filter(animal_id=animal_id)
