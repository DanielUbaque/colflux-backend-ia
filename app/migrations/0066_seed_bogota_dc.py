from django.db import migrations


def seed(apps, schema_editor):
    Region = apps.get_model("app", "Region")
    Departamento = apps.get_model("app", "Departamento")
    region_andes = Region.objects.get(nombre="Andes")
    Departamento.objects.get_or_create(
        nombre="Bogota_DC",
        defaults={"region": region_andes, "codigo_dane": "11"},
    )


def unseed(apps, schema_editor):
    Departamento = apps.get_model("app", "Departamento")
    Departamento.objects.filter(nombre="Bogota_DC", municipios__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0065_departamento_geom_alter_departamento_nombre"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
