# ROADMAP.md

Estado del trabajo y próximos pasos. Se actualiza al final de cada sesión relevante — no es documentación estable (para eso está `CLAUDE.md`).

## Hecho

- **SQLite local eliminado** y bloqueado en código (`colflux/settings.py` exige `DATABASE_URL`, sin fallback).
- **Geometría de departamentos cargada** (33/33, incluye Bogotá D.C. agregada como nuevo registro). Comando: `python manage.py load_departamentos_geom data/departamentos.gpkg`.
- **Geometría de municipios cargada** (1121/1122, falta Mapiripaná sin match en el `.gpkg` del DANE). Comando `load_municipios_geom` (mismo patrón que departamentos, cruza por `MPIO_CDPMP`). Faltaban 2 municipios en la BD (San José de Uré 23682 y Tuchín 23815, Córdoba) — se agregaron con la migración de datos `0069_seed_municipios_faltantes`.
- **API geográfica ampliada:**
  - `/api/geo/series/`: filtros nuevos `municipio`, `region`, `desde`, `hasta` (antes solo `anio`).
  - `/api/geo/resumen/` (nuevo): agregado por `nivel=departamento|municipio|region|sitio`, mismos filtros que `series`.
- **`CLAUDE.md` y este `ROADMAP.md` creados.**
- **Migración a GeoDjango/PostGIS.** `Departamento.geom`/`Municipio.geom` pasaron de `JSONField` a `MultiPolygonField` (SRID 4326); DB corre en `postgis/postgis:16-3.4-alpine` (migraciones `0070_enable_postgis`, `0071_departamento_municipio_geom_postgis`). Se agregó `Sitio.geom` (`PointField`, SRID 4326, migración `0072_sitio_geom`), derivado automáticamente de `latitud`/`longitud` en `Sitio.save()` — `latitud`/`longitud` siguen siendo la fuente de verdad editable.
- **Backfill de `Sitio.municipio` resuelto.** Comando `backfill_sitio_municipio` (point-in-polygon: `Municipio.objects.filter(geom__contains=sitio.geom)`) — los 76 sitios existentes ya tienen `municipio` asignado. `/api/geo/resumen/` agrega correctamente en los 4 niveles (verificado; el dataset de seed actual está concentrado en Cundinamarca).
- **Nuevo modelo `Vereda`** (`app/models/geo.py`, migración `0073_vereda`): cubre vereda (rural) y manzana censal (urbana) del MGN en un solo modelo con campo `tipo`, FK a `Municipio`, `geom` (`MultiPolygonField`). Comando `load_veredas_geom <gpkg> --tipo vereda|manzana`. Veredas cargadas: 33.355/33.428 (73 filas venían como polígonos multi-parte con el mismo `codigo_dane` — se unieron con `GEOSGeometry.union()` en vez de `shapely.unary_union`, que rompe bajo emulación arm64/qemu, ver `CLAUDE.md`). Manzanas censales: 517.105/517.105 cargadas sin filas sin match. Total `Vereda`: 550.460 registros.

## Pendiente — corto plazo

1. **Revisar el modelo de datos, sección de relaciones entre entidades, para ver bien cuáles tablas son "tipos" (catálogos) vs. entidades propias.** Recordatorio: revisar en particular las entidades de **Parcela** y **Unidad Experimental**.
2. **Cuando se haga la próxima carga de datos (ETL de sitios/muestras), revisar también la sección de sistemas de referencia espacial** (`SistemaReferencia` en `app/models/geo.py`: EPSG:4326/4686/4674) — confirmar que los sitios cargados declaran el sistema correcto y que coincide con el supuesto de `Sitio.save()` (asume que `latitud`/`longitud` ya vienen en WGS84/EPSG:4326 al construir `Point(...)`; si un sitio viene en otro sistema, `geom` quedaría mal ubicado sin reproyectar primero). Extender esta revisión a `Vereda`: `vereda.gpkg` ya viene en EPSG:4326 pero `manzana.gpkg` viene en EPSG:4674 (se reproyecta al cargar, confirmar que se mantenga así con datasets futuros del DANE).
3. **`backfill_sitio_municipio` no corre automáticamente.** Falta engancharlo a la carga de datos (ETL) para que sitios nuevos con lat/lon pero sin `municipio` se resuelvan solos, en vez de requerir correr el comando a mano.
4. **`Sitio` no tiene FK a `Vereda` todavía.** Si se necesita agregación a ese nivel, falta agregar el campo y un backfill espacial análogo a `backfill_sitio_municipio` (point-in-polygon contra `Vereda.geom`, filtrando por `tipo` según si el sitio cae en área rural o urbana).

## Pendiente — diseño acordado, falta implementar

**Tabla materializada de resumen geográfico** (decisión tomada: opción de escalar mejor que cache HTTP simple, dado que los datos van a crecer).

- Nuevo modelo `ResumenGeoMensual`: grano `(sitio, proyecto, gas, año, mes)`, con `total_muestras`, `suma_valor`, `valor_min`, `valor_max`, `ultima_fecha`, `ultimo_valor`, `ultima_unidad`.
- `resumen_geografico` (en `app/api/geo/views.py`) pasa a leer de esta tabla en vez de iterar `SubmuestraGEI` directo — mismo agrupado en memoria, pero sobre un dataset mucho más chico. `desde`/`hasta` se filtran por año/mes (resolución suficiente para un agregado; `/series/` sigue sirviendo el dato crudo con fecha exacta).
- Management command `refrescar_resumen_geo` (patrón `generate_catalogo`) que recalcula la tabla — llamado automáticamente al final de `importar_carga` (`app/api/etl/views.py`) y de los comandos `load_departamentos_geom`/`load_municipios_geom`. Por ahora recalculo completo (barato al volumen actual); si crece mucho, acotar por `fuente_datos` recién importada.
- Opcional, encima de la tabla ya chica: `cache_page` corto en `resumen_geografico` para picos de tráfico.

**No implementado todavía** — falta: modelo + migración, el management command, engancharlo a `importar_carga`, y reescribir `resumen_geografico`.

## Ideas mencionadas, no decididas

- `Region.geom` (unión de sus departamentos) — se descartó por ahora a favor de que el front dibuje los departamentos miembros (ya viene la lista en `properties.departamentos` cuando `nivel=region`).
- **Migración a GeoDjango: completa para `Departamento`/`Municipio`/`Sitio`** (ver "Hecho" arriba). `DATABASES.ENGINE` es `django.contrib.gis.db.backends.postgis`.
  - Hallazgos de rendimiento en las vistas actuales, independientes de esa decisión:
    - `sitios_geojson` y `resumen_geografico` traen **todas** las `SubmuestraCO2` filtradas a Python y agregan a mano (conteos, min/max, última medición) en vez de usar `.values(...).annotate(Count/Avg/Min/Max)` y `DISTINCT ON` de Postgres. La tabla materializada `ResumenGeoMensual` (arriba) resuelve esto de raíz cuando se implemente.
    - `series_co2` no tiene paginación ni límite — devuelve el dataset filtrado completo en un solo response.
