import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0066_seed_bogota_dc'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='MuestraCO2',
            new_name='MuestraGEI',
        ),
        migrations.RenameModel(
            old_name='SubmuestraCO2',
            new_name='SubmuestraGEI',
        ),
        migrations.AlterModelOptions(
            name='muestragei',
            options={'ordering': ['-created_at'], 'verbose_name': 'muestra GEI', 'verbose_name_plural': 'muestras GEI'},
        ),
        migrations.AlterModelOptions(
            name='submuestragei',
            options={'ordering': ['muestra', 'n_toma'], 'verbose_name': 'submuestra GEI', 'verbose_name_plural': 'submuestras GEI'},
        ),
        migrations.AlterField(
            model_name='muestragei',
            name='analizador',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='muestras_gei', to='app.equipo', verbose_name='analizador'),
        ),
        migrations.AlterField(
            model_name='muestragei',
            name='unidad_medida',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='muestras_gei', to='app.unidadmedida', verbose_name='unidad de medida'),
        ),
        migrations.AlterField(
            model_name='muestragei',
            name='unidad_muestreo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='muestras_gei', to='app.unidadmuestreo', verbose_name='unidad de muestreo'),
        ),
        migrations.AlterField(
            model_name='submuestragei',
            name='muestra',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submuestras', to='app.muestragei', verbose_name='muestra GEI'),
        ),
        migrations.AlterField(
            model_name='cargaarchivo',
            name='pks_importados',
            field=models.JSONField(blank=True, default=dict, help_text='Acumula, por modelo, los pk que esta carga creó o reutilizó al importar. Ej: {"SubmuestraGEI": [10, 11, 12]}. Permite mostrar solo los datos de esta carga en el panel de visualización.', verbose_name='pks creados/vinculados por esta carga'),
        ),
        migrations.RemoveIndex(
            model_name='muestragei',
            name='app_muestra_analiza_04b67d_idx',
        ),
        migrations.AddIndex(
            model_name='muestragei',
            index=models.Index(fields=['analizador'], name='app_muestra_analiza_576fb6_idx'),
        ),
    ]
