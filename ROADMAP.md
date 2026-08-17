# ROADMAP.md

Estado del trabajo y próximos pasos. Se actualiza al final de cada sesión relevante — no es documentación estable (para eso está `CLAUDE.md`).

## Hecho

- **SQLite local eliminado** y bloqueado en código (`colflux/settings.py` exige `DATABASE_URL`, sin fallback).
- **Geometría de departamentos cargada** (33/33, incluye Bogotá D.C. agregada como nuevo registro). Comando: `python manage.py load_departamentos_geom data/departamentos.gpkg`.
- **Geometría de municipios cargada** (1121/1121). Campo `Municipio.geom` (JSONField, migración `0068_municipio_geom`) y comando `load_municipios_geom` (mismo patrón que departamentos, cruza por `MPIO_CDPMP`). Faltaban 2 municipios en la BD (San José de Uré 23682 y Tuchín 23815, Córdoba) — se agregaron con la migración de datos `0069_seed_municipios_faltantes`.
- **API geográfica ampliada:**
  - `/api/geo/series/`: filtros nuevos `municipio`, `region`, `desde`, `hasta` (antes solo `anio`).
  - `/api/geo/resumen/` (nuevo): agregado por `nivel=departamento|municipio|region|sitio`, mismos filtros que `series`.
- **`CLAUDE.md` y este `ROADMAP.md` creados.**

## Pendiente — corto plazo

1. **Backfill de `Sitio.municipio`.** Los 76 sitios existentes tienen `municipio_id = null`. Sin esto, `/api/geo/resumen/?nivel=departamento|municipio|region` no puede agrupar nada (devuelve `features: []`). El usuario dijo que lo va a cargar — falta el comando/proceso concreto y verificar después.
2. Verificar `/api/geo/resumen/` en los tres niveles restantes una vez resuelto (1) — geometría de departamentos y municipios ya está cargada.
3. **Cargar geometría de nivel vereda y manzana.** No hay todavía modelo/campo ni comando (`load_municipios_geom` solo cubre hasta municipio) — falta definir cómo se relaciona con `Municipio`/`Sitio` y conseguir el `.gpkg` correspondiente del DANE (MGN vereda / manzana censal).

## Pendiente — diseño acordado, falta implementar

**Tabla materializada de resumen geográfico** (decisión tomada: opción de escalar mejor que cache HTTP simple, dado que los datos van a crecer).

- Nuevo modelo `ResumenGeoMensual`: grano `(sitio, proyecto, gas, año, mes)`, con `total_muestras`, `suma_valor`, `valor_min`, `valor_max`, `ultima_fecha`, `ultimo_valor`, `ultima_unidad`.
- `resumen_geografico` (en `app/api/geo/views.py`) pasa a leer de esta tabla en vez de iterar `SubmuestraGEI` directo — mismo agrupado en memoria, pero sobre un dataset mucho más chico. `desde`/`hasta` se filtran por año/mes (resolución suficiente para un agregado; `/series/` sigue sirviendo el dato crudo con fecha exacta).
- Management command `refrescar_resumen_geo` (patrón `generate_catalogo`) que recalcula la tabla — llamado automáticamente al final de `importar_carga` (`app/api/etl/views.py`) y de los comandos `load_departamentos_geom`/`load_municipios_geom`. Por ahora recalculo completo (barato al volumen actual); si crece mucho, acotar por `fuente_datos` recién importada.
- Opcional, encima de la tabla ya chica: `cache_page` corto en `resumen_geografico` para picos de tráfico.

**No implementado todavía** — falta: modelo + migración, el management command, engancharlo a `importar_carga`, y reescribir `resumen_geografico`.

## Ideas mencionadas, no decididas

- `Region.geom` (unión de sus departamentos) — se descartó por ahora a favor de que el front dibuje los departamentos miembros (ya viene la lista en `properties.departamentos` cuando `nivel=region`).
- **Revisión de `app/api/geo/views.py`: el proyecto no usa GeoDjango.** `DATABASES.ENGINE` es `postgresql` normal (no `postgis`), `Departamento.geom`/`Municipio.geom` son `JSONField` (GeoJSON crudo) y `Sitio.latitud`/`longitud` son `DecimalField` sueltos — no hay tipos espaciales ni índices GiST en la BD. `geopandas`/`shapely` solo se usan offline en los comandos `load_*_geom`. Sin decidir todavía si migrar a GeoDjango (PostGIS + `PointField`/`MultiPolygonField`, habilita bbox/distancia/simplificación en la propia query) o quedarnos como está.
  - Hallazgos de rendimiento en las vistas actuales, independientes de esa decisión:
    - `sitios_geojson` y `resumen_geografico` traen **todas** las `SubmuestraCO2` filtradas a Python y agregan a mano (conteos, min/max, última medición) en vez de usar `.values(...).annotate(Count/Avg/Min/Max)` y `DISTINCT ON` de Postgres. La tabla materializada `ResumenGeoMensual` (arriba) resuelve esto de raíz cuando se implemente.
    - `series_co2` no tiene paginación ni límite — devuelve el dataset filtrado completo en un solo response.
