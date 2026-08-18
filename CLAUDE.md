# CLAUDE.md

Contexto persistente para trabajar en este repo. Se carga automáticamente al inicio de cada sesión — no hace falta pegarlo. Para el estado actual del trabajo (qué está hecho, qué sigue), ver `ROADMAP.md`.

## Qué es este proyecto

Backend Django (`colflux`, app `app`) para inventariar y visualizar datos de flujo de gases de efecto invernadero (CO₂, CH₄, N₂O) medidos en sitios de estudio en Colombia. Incluye ETL de datos crudos (Excel/CSV), catálogos geográficos (región/departamento/municipio) y un geoportal que consume GeoJSON.

## Infraestructura

- Base de datos: **Postgres 16 + PostGIS vía Docker** (`docker-compose.yml`, imagen `postgis/postgis:16-3.4-alpine`, servicios `db` y `web`). No hay fallback a SQLite — `colflux/settings.py` lanza `RuntimeError` si falta `DATABASE_URL`. Esto fue una decisión explícita para evitar confundir datos locales en sqlite con los de Postgres.
- La imagen `web` instala libs nativas GEOS/GDAL/PROJ (`Dockerfile`) que requiere `django.contrib.gis` en runtime — si corrés Django fuera de Docker (`.venv-run-check`) necesitás esas libs instaladas en el host (p. ej. `brew install gdal`) para que `manage.py` arranque.
- **`shapely.unary_union`/`shapely.union_all` rompen bajo emulación arm64/qemu** (host Apple Silicon corriendo la imagen `linux/amd64`): tiran `TypeError: ufunc 'create_collection' not supported...` incluso con geometrías triviales. Para unir geometrías (p. ej. dedupe de polígonos multi-parte al cargar `Vereda`), usar `GEOSGeometry.union()` de `django.contrib.gis.geos` en vez de shapely — pasa por el binding de GEOS de Django, no por el ufunc de numpy que falla.
- Entorno local (fuera de Docker): usar `.venv-run-check` (tiene Django y todo `requirements.txt` instalado) en vez de `.venv` (vacío, solo `pip`). Si `.venv` alguna vez se puebla correctamente, se puede consolidar.
- Levantar todo: `docker compose up -d --build`. La API queda en `localhost:8000`.

## Decisiones de arquitectura

- **GeoDjango/PostGIS para `Departamento.geom`, `Municipio.geom` y `Sitio.geom`** (`MultiPolygonField`/`PointField`, SRID 4326). Se migró desde `JSONField` con GeoJSON crudo para poder hacer cálculos agregados por geometría en la base (point-in-polygon, `ST_Intersects`, agregaciones espaciales) en vez de traer todo a Python. `Sitio.latitud`/`longitud` (`DecimalField`) siguen siendo la fuente de verdad editable; `Sitio.geom` es de solo lectura (`editable=False`) y se recalcula en `Sitio.save()` a partir de esos dos campos — **asume que ya vienen en WGS84/EPSG:4326**, sin reproyectar (ver `SistemaReferencia` en el modelo, hoy no se usa para eso).
- **Geometría simplificada al cargar**, no en cada request: `shapely`/`geopandas` `.simplify(tolerance, preserve_topology=True)` al momento del `load_*_geom`, para no servir polígonos con miles de vértices desde la API.
- **Fuente de geometrías: DANE MGN 2021** (Marco Geoestadístico Nacional), en `.gpkg` (GeoPackage), reproyectado de EPSG:4686 a EPSG:4326 (WGS84) al cargar.
- **Patrón de carga de datos geográficos:** management command en `app/management/commands/load_<nivel>_geom.py`, cruza por `codigo_dane` contra el modelo (`Departamento`, a futuro `Municipio`). Ver `load_departamentos_geom.py` como referencia.
- **Migraciones de datos (seed)** con `RunPython` + `apps.get_model`, patrón ya establecido (`0019_seed_regiones_departamentos.py`, `0025_seed_municipios.py`, `0066_seed_bogota_dc.py`).
- **Archivos fuente de datos** (Excel, CSV, `.gpkg`) van en `data/` en la raíz del backend — está gitignoreado (excepto `data/dump.sql`), así que nunca se commitean datasets pesados o con datos sensibles.

## Modelos geográficos (`app/models/geo.py`)

`Region` → `Departamento` (con `geom`, `codigo_dane`) → `Municipio` (con `geom`, `codigo_dane`) → `Vereda` (con `geom`, `codigo_dane`, FK a `Municipio`). `Vereda` es un solo modelo para dos niveles del MGN que en la práctica son mutuamente excluyentes por municipio (rural vs. urbano): campo `tipo` (`"vereda"` | `"manzana"`, esta última son manzanas censales urbanas). Se cargan con `load_veredas_geom <gpkg> --tipo vereda|manzana` — columnas de origen distintas por tipo (`COLUMNAS_POR_TIPO` en el comando). `Sitio` (en `app/models/sitio.py`) tiene lat/lon planos + `geom` derivado, y FK a `Municipio` (no a `Vereda` todavía) — se backfillea con el comando `backfill_sitio_municipio` (point-in-polygon contra `Municipio.geom`); no corre automáticamente en la carga de datos todavía (ver ROADMAP).

## API geográfica (`app/api/geo/views.py`)

- `GET /api/geo/sitios/` — GeoJSON de sitios con resumen de mediciones embebido.
- `GET /api/geo/series/` — lecturas crudas (`SubmuestraGEI`), filtros: `gas`, `anio`, `desde`, `hasta`, `sitio`, `proyecto`, `municipio`, `departamento`, `region`.
- `GET /api/geo/resumen/?nivel=departamento|municipio|region|sitio` — agregado (conteo/promedio/min/max/última medición) por nivel geográfico, mismos filtros que `series`. `region` no tiene geometría propia: sale con `geometry=null` y una lista `departamentos` para que el cliente dibuje/resalte los departamentos que la componen.

## Modelo de mediciones (`app/models/co2.py`)

`MuestraGEI` (evento de medición, un tubo/equipo conectado) → `SubmuestraGEI` (cada toma individual, ahí vive `valor`). El modelo se llamaba `MuestraCO2`/`SubmuestraCO2` — renombrado a `*GEI` porque mide los tres gases del catálogo (`TipoMuestra.GAS_CHOICES`: CO2/CH4/N2O), no solo CO₂.

## Convenciones generales

- Comandos de management (`app/management/commands/`) son el patrón para operaciones de carga repetibles (`generate_catalogo`, `seed_ghg_data`, `load_departamentos_geom`).
- Nunca volcar geometría/coordenadas crudas en la conversación al depurar — usar scripts o el shell de Django y reportar solo conteos/resúmenes.
