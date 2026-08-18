from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError

from app.models.geo import Municipio


class Command(BaseCommand):
    help = (
        "Carga la geometría de municipios desde un GeoPackage del MGN (DANE), "
        "cruzando por código DANE (columna MPIO_CDPMP) contra Municipio.codigo_dane."
    )

    def add_arguments(self, parser):
        parser.add_argument("gpkg_path", help="Ruta al archivo .gpkg de municipios")
        parser.add_argument(
            "--tolerancia",
            type=float,
            default=0.001,
            help="Tolerancia de simplificación en grados (default 0.001 ≈ 100 m)",
        )

    def handle(self, *args, **options):
        try:
            import geopandas as gpd
        except ImportError as exc:
            raise CommandError(
                "Falta geopandas. Instala requirements.txt (incluye geopandas/pyogrio/shapely)."
            ) from exc

        gdf = gpd.read_file(options["gpkg_path"])
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        gdf["geometry"] = gdf.geometry.simplify(options["tolerancia"], preserve_topology=True)

        codigos_bd = {m.codigo_dane: m for m in Municipio.objects.exclude(codigo_dane=None)}

        actualizados, sin_match = [], []
        for _, row in gdf.iterrows():
            codigo = str(row["MPIO_CDPMP"]).zfill(5)
            municipio = codigos_bd.get(codigo)
            if municipio is None:
                sin_match.append((codigo, row.get("MPIO_CNMBR")))
                continue
            geom = GEOSGeometry(row.geometry.wkt, srid=4326)
            if geom.geom_type == "Polygon":
                geom = MultiPolygon(geom)
            municipio.geom = geom
            actualizados.append(municipio)

        Municipio.objects.bulk_update(actualizados, ["geom"])

        self.stdout.write(self.style.SUCCESS(f"Geometría cargada para {len(actualizados)} municipios."))
        if sin_match:
            self.stdout.write(self.style.WARNING(f"Sin match en BD ({len(sin_match)}): {sin_match}"))

        sin_geom = Municipio.objects.filter(geom=None).values_list("nombre", flat=True)
        if sin_geom:
            self.stdout.write(self.style.WARNING(f"Municipios sin geometría tras la carga: {list(sin_geom)}"))
