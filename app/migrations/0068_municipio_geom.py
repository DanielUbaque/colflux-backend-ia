from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0067_rename_muestraco2_muestragei'),
    ]

    operations = [
        migrations.AddField(
            model_name='municipio',
            name='geom',
            field=models.JSONField(blank=True, null=True, verbose_name='geometría (GeoJSON)'),
        ),
    ]
