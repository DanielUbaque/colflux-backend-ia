import django.contrib.gis.db.models.fields
from django.db import migrations


def poblar_geom(apps, schema_editor):
    from django.contrib.gis.geos import Point

    Sitio = apps.get_model("app", "Sitio")
    actualizados = []
    for sitio in Sitio.objects.exclude(latitud=None).exclude(longitud=None):
        sitio.geom = Point(float(sitio.longitud), float(sitio.latitud), srid=4326)
        actualizados.append(sitio)
    Sitio.objects.bulk_update(actualizados, ["geom"])


def revertir_geom(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0071_departamento_municipio_geom_postgis'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitio',
            name='geom',
            field=django.contrib.gis.db.models.fields.PointField(
                blank=True, editable=False, null=True, srid=4326, verbose_name='geometría',
            ),
        ),
        migrations.RunPython(poblar_geom, revertir_geom),
    ]
