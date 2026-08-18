from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0069_seed_municipios_faltantes'),
    ]

    operations = [
        CreateExtension('postgis'),
    ]
