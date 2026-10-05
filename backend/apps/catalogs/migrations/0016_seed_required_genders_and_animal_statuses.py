from django.db import migrations


def seed_required_catalogs(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    seeds = (
        (apps.get_model("catalogs", "Gender"), "F", "Hembra"),
        (apps.get_model("catalogs", "Gender"), "M", "Macho"),
        (apps.get_model("catalogs", "AnimalStatus"), "ACTIVE", "Activo"),
        (apps.get_model("catalogs", "AnimalStatus"), "SOLD", "Vendido"),
    )
    missing = []
    # Validate every missing seed before making any writes.
    for model, code, name in seeds:
        rows = model._base_manager.using(db_alias)
        if rows.filter(code=code).exists():
            continue
        conflicting_code = rows.filter(name=name).values_list("code", flat=True).first()
        if conflicting_code is not None:
            raise RuntimeError(
                f"No se puede crear {model._meta.label} code='{code}': "
                f"el nombre '{name}' ya pertenece a code='{conflicting_code}'. "
                "Resuelva el conflicto y vuelva a ejecutar migrate."
            )
        missing.append((model, code, name))

    for model, code, name in missing:
        model._base_manager.using(db_alias).create(code=code, name=name)


class Migration(migrations.Migration):
    atomic = True
    dependencies = [("catalogs", "0015_seed_production_types")]
    operations = [
        migrations.RunPython(seed_required_catalogs, migrations.RunPython.noop),
    ]
