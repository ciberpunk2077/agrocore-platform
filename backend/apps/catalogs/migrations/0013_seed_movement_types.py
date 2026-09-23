from django.db import migrations


def seed_movement_types(apps, schema_editor):

    MovementType = apps.get_model(
        "catalogs",
        "MovementType",
    )

    movement_types = [
        ("TRANSFER", "Traslado"),
        ("ENTRY", "Ingreso"),
        ("EXIT", "Salida"),
        ("SALE", "Venta"),
        ("PURCHASE", "Compra"),
    ]

    for code, name in movement_types:

        MovementType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
            },
        )


def reverse_seed(apps, schema_editor):

    MovementType = apps.get_model(
        "catalogs",
        "MovementType",
    )

    MovementType.objects.filter(
        code__in=[
            "TRANSFER",
            "ENTRY",
            "EXIT",
            "SALE",
            "PURCHASE",
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "catalogs",
            "0012_breedingtype",
        ),
    ]

    operations = [
        migrations.RunPython(
            seed_movement_types,
            reverse_seed,
        ),
    ]