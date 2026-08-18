from django.core.management.base import BaseCommand

from app.models import Sitio, Vereda


class Command(BaseCommand):
    help = (
        "Backfillea Sitio.vereda para los sitios sin vereda asignada, "
        "resolviendo por point-in-polygon (Sitio.geom dentro de Vereda.geom, "
        "sea tipo vereda o manzana)."
    )

    def handle(self, *args, **options):
        sitios = Sitio.objects.filter(vereda=None).exclude(geom=None)

        actualizados, sin_match = [], []
        for sitio in sitios:
            vereda = Vereda.objects.filter(geom__contains=sitio.geom).first()
            if vereda is None:
                sin_match.append(sitio.nombre)
                continue
            sitio.vereda = vereda
            actualizados.append(sitio)

        Sitio.objects.bulk_update(actualizados, ["vereda"])

        self.stdout.write(self.style.SUCCESS(f"Vereda asignada a {len(actualizados)} sitios."))
        if sin_match:
            self.stdout.write(self.style.WARNING(f"Sin match ({len(sin_match)}): {sin_match}"))

        sin_vereda = Sitio.objects.filter(vereda=None).count()
        if sin_vereda:
            self.stdout.write(self.style.WARNING(f"Sitios sin vereda tras el backfill: {sin_vereda}"))
