import json

import django.contrib.gis.db.models.fields
from django.db import migrations


def _convertir_geom_json_a_postgis(modelo):
    from django.contrib.gis.geos import GEOSGeometry, MultiPolygon

    for obj in modelo.objects.exclude(geom=None):
        geom = GEOSGeometry(json.dumps(obj.geom))
        if geom.geom_type == "Polygon":
            geom = MultiPolygon(geom)
        obj.geom_postgis = geom
        obj.save(update_fields=["geom_postgis"])


def convertir_geometrias(apps, schema_editor):
    Departamento = apps.get_model("app", "Departamento")
    Municipio = apps.get_model("app", "Municipio")
    _convertir_geom_json_a_postgis(Departamento)
    _convertir_geom_json_a_postgis(Municipio)


def revertir_geometrias(apps, schema_editor):
    # No hace falta reconstruir el JSONField viejo: RemoveField ya lo eliminó
    # de forma irreversible en el forward. No-op en el reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0070_enable_postgis'),
    ]

    operations = [
        migrations.AddField(
            model_name='departamento',
            name='geom_postgis',
            field=django.contrib.gis.db.models.fields.MultiPolygonField(
                blank=True, null=True, srid=4326, verbose_name='geometría',
            ),
        ),
        migrations.AddField(
            model_name='municipio',
            name='geom_postgis',
            field=django.contrib.gis.db.models.fields.MultiPolygonField(
                blank=True, null=True, srid=4326, verbose_name='geometría',
            ),
        ),
        migrations.RunPython(convertir_geometrias, revertir_geometrias),
        migrations.RemoveField(
            model_name='departamento',
            name='geom',
        ),
        migrations.RemoveField(
            model_name='municipio',
            name='geom',
        ),
        migrations.RenameField(
            model_name='departamento',
            old_name='geom_postgis',
            new_name='geom',
        ),
        migrations.RenameField(
            model_name='municipio',
            old_name='geom_postgis',
            new_name='geom',
        ),
    ]
