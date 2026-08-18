import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0072_sitio_geom'),
    ]

    operations = [
        migrations.CreateModel(
            name='Vereda',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('nombre', models.CharField(blank=True, max_length=160)),
                ('codigo_dane', models.CharField(max_length=25, unique=True, verbose_name='código DANE')),
                ('tipo', models.CharField(choices=[('vereda', 'Vereda'), ('manzana', 'Manzana censal')], max_length=10)),
                ('geom', django.contrib.gis.db.models.fields.MultiPolygonField(blank=True, null=True, srid=4326, verbose_name='geometría')),
                ('municipio', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='veredas', to='app.municipio')),
            ],
            options={
                'verbose_name': 'vereda',
                'verbose_name_plural': 'veredas',
                'ordering': ['municipio__nombre', 'nombre'],
            },
        ),
    ]
