from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError

from app.models.geo import Municipio, Vereda

# Los .gpkg de vereda y manzana censal del MGN traen esquemas de columnas
# distintos (una es capa rural, la otra urbana), pero ambas se cargan en el
# mismo modelo Vereda (campo `tipo`). Este mapa dice, por tipo, qué columna
# trae el código DANE del municipio (para cruzar contra Municipio.codigo_dane),
# cuál trae el código DANE propio de la subdivisión, y cuál el nombre.
COLUMNAS_POR_TIPO = {
    Vereda.VEREDA: {"municipio": "DPTOMPIO", "codigo": "CODIGO_VER", "nombre": "NOMBRE_VER"},
    Vereda.MANZANA: {"municipio": "COD_MPIO", "codigo": "COD_DANE", "nombre": None},
}


class Command(BaseCommand):
    help = (
        "Carga veredas o manzanas censales desde un GeoPackage del MGN (DANE), "
        "cruzando por código DANE del municipio contra Municipio.codigo_dane."
    )

    def add_arguments(self, parser):
        parser.add_argument("gpkg_path", help="Ruta al archivo .gpkg de veredas o manzanas")
        parser.add_argument(
            "--tipo", choices=[Vereda.VEREDA, Vereda.MANZANA], required=True,
            help="Tipo de subdivisión que trae el .gpkg (vereda o manzana)",
        )
        parser.add_argument(
            "--tolerancia",
            type=float,
            default=0.0005,
            help="Tolerancia de simplificación en grados (default 0.0005 ≈ 50 m)",
        )
        parser.add_argument(
            "--batch-size", type=int, default=1000,
            help="Tamaño de lote para bulk_create/bulk_update (default 1000)",
        )

    def handle(self, *args, **options):
        try:
            import geopandas as gpd
        except ImportError as exc:
            raise CommandError(
                "Falta geopandas. Instala requirements.txt (incluye geopandas/pyogrio/shapely)."
            ) from exc

        tipo = options["tipo"]
        columnas = COLUMNAS_POR_TIPO[tipo]
        batch_size = options["batch_size"]

        gdf = gpd.read_file(options["gpkg_path"])
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        gdf["geometry"] = gdf.geometry.simplify(options["tolerancia"], preserve_topology=True)

        municipios_bd = {m.codigo_dane: m for m in Municipio.objects.exclude(codigo_dane=None)}
        existentes = set(Vereda.objects.filter(tipo=tipo).values_list("codigo_dane", flat=True))

        # Algunas subdivisiones vienen partidas en varias filas con el mismo
        # código DANE (polígonos multi-parte, p. ej. exclaves) — se acumulan
        # acá y se unen con GEOSGeometry.union (no shapely.unary_union: bajo
        # emulación arm64/qemu esa función rompe con un TypeError de numpy).
        acumulado = {}
        sin_match_municipio = []
        for _, row in gdf.iterrows():
            codigo_dane = str(row[columnas["codigo"]])
            if codigo_dane in existentes:
                continue

            codigo_municipio = str(row[columnas["municipio"]]).zfill(5)
            municipio = municipios_bd.get(codigo_municipio)
            if municipio is None:
                sin_match_municipio.append((codigo_municipio, codigo_dane))
                continue

            geom = GEOSGeometry(row.geometry.wkt, srid=4326)

            if codigo_dane in acumulado:
                acumulado[codigo_dane]["geom"] = acumulado[codigo_dane]["geom"].union(geom)
            else:
                nombre = str(row[columnas["nombre"]]) if columnas["nombre"] else ""
                acumulado[codigo_dane] = {"nombre": nombre, "municipio": municipio, "geom": geom}

        nuevas = []
        for codigo_dane, datos in acumulado.items():
            geom = datos["geom"]
            if geom.geom_type == "Polygon":
                geom = MultiPolygon(geom)
            nuevas.append(Vereda(
                nombre=datos["nombre"], codigo_dane=codigo_dane, tipo=tipo,
                municipio=datos["municipio"], geom=geom,
            ))

        Vereda.objects.bulk_create(nuevas, batch_size=batch_size)

        self.stdout.write(self.style.SUCCESS(
            f"{tipo}: {len(nuevas)} creadas, {len(existentes)} ya existentes en BD (omitidas)."
        ))
        if sin_match_municipio:
            self.stdout.write(self.style.WARNING(
                f"Sin match de municipio en BD ({len(sin_match_municipio)}), primeros 10: "
                f"{sin_match_municipio[:10]}"
            ))
