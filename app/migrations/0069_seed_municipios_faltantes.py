from django.db import migrations


MUNICIPIOS = [
    ("23682", "SAN JOSE DE URE"),
    ("23815", "TUCHIN"),
]


def seed_municipios(apps, schema_editor):
    Departamento = apps.get_model("app", "Departamento")
    Municipio = apps.get_model("app", "Municipio")
    cordoba = Departamento.objects.get(codigo_dane="23")
    for codigo, nombre in MUNICIPIOS:
        Municipio.objects.get_or_create(
            codigo_dane=codigo,
            defaults={"nombre": nombre, "departamento": cordoba},
        )


def unseed_municipios(apps, schema_editor):
    Municipio = apps.get_model("app", "Municipio")
    Municipio.objects.filter(codigo_dane__in=[codigo for codigo, _ in MUNICIPIOS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0068_municipio_geom'),
    ]

    operations = [
        migrations.RunPython(seed_municipios, unseed_municipios),
    ]
