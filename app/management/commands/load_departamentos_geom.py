import json

from django.core.management.base import BaseCommand, CommandError

from app.models.geo import Departamento


class Command(BaseCommand):
    help = (
        "Carga la geometría de departamentos desde un GeoPackage del MGN (DANE), "
        "cruzando por código DANE (columna DPTO_CCDGO) contra Departamento.codigo_dane."
    )

    def add_arguments(self, parser):
        parser.add_argument("gpkg_path", help="Ruta al archivo .gpkg de departamentos")
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

        codigos_bd = {d.codigo_dane: d for d in Departamento.objects.exclude(codigo_dane=None)}

        actualizados, sin_match = [], []
        for _, row in gdf.iterrows():
            codigo = str(row["DPTO_CCDGO"]).zfill(2)
            depto = codigos_bd.get(codigo)
            if depto is None:
                sin_match.append((codigo, row.get("DPTO_CNMBR")))
                continue
            depto.geom = json.loads(gpd.GeoSeries([row.geometry]).to_json())["features"][0]["geometry"]
            actualizados.append(depto)

        Departamento.objects.bulk_update(actualizados, ["geom"])

        self.stdout.write(self.style.SUCCESS(f"Geometría cargada para {len(actualizados)} departamentos."))
        if sin_match:
            self.stdout.write(self.style.WARNING(f"Sin match en BD ({len(sin_match)}): {sin_match}"))

        sin_geom = Departamento.objects.filter(geom=None).values_list("nombre", flat=True)
        if sin_geom:
            self.stdout.write(self.style.WARNING(f"Departamentos sin geometría tras la carga: {list(sin_geom)}"))
