# Generated manually: makemigrations no puede correr en modo no interactivo
# para este cambio (pide un valor por defecto "one-off" para la conversión
# null=True -> null=False). El default de abajo no se llega a usar: antes de
# esta migración ya se hizo backfill/limpieza de todas las filas con
# unidad_muestreo nulo, así que no queda ninguna fila que lo necesite.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0047_muestraambiental_water_level'),
    ]

    operations = [
        migrations.AlterField(
            model_name='muestraambiental',
            name='unidad_muestreo',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='muestras_ambientales',
                to='app.unidadmuestreo',
                verbose_name='unidad de muestreo',
            ),
        ),
    ]
