from django.db import migrations


def backfill_gas_co2(apps, schema_editor):
    MuestraCO2 = apps.get_model("app", "MuestraCO2")
    MuestraCO2.objects.filter(gas="").update(gas="CO2")


def reverse_noop(apps, schema_editor):
    # No se revierte: no hay forma de distinguir qué filas tenían gas=""
    # antes de este backfill de las que se marcaron CO2 legítimamente después.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0063_muestraco2_gas"),
    ]

    operations = [
        migrations.RunPython(backfill_gas_co2, reverse_noop),
    ]
