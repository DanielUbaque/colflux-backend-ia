# Plan de desarrollo — Pipeline ETL de carga de datos

## Contexto

El portal en `docs/` tiene `data.html`: una página que lista fuentes de datos (`FuenteDatos`) por
proyecto y permite registrar nuevas con estado `pendiente`. El backend Django expone esas fuentes
en `/api/fuentes-datos/`.

El archivo de ejemplo es `data/Base_de_Datos_2025.xlsx`:
- Hoja principal `Documentos2025_1`: 53 registros, ~110 columnas
- Cubre datos bibliográficos, ubicación geográfica, coberturas, contenidos de carbono y flujos de gases
- El modelo de dominio en Django (`app/models/`) tiene: `Publicacion`, `Sitio`, `Parcela`,
  `Cobertura`, `MonitoreoSuelo`, `ResultadoPublicacion`, entre otros

---

## Flujo completo

```
data.html
  └─ [card de fuente en estado "pendiente"]
       └─ botón "Iniciar carga" ──→ etl-upload.html?fuente=<id>
                                         │
                                    [Paso 1] Subir archivo
                                         │
                                    [Paso 2] Mapeo de columnas
                                         │  └─ sub-panel de mapeo de valores
                                         │     para campos con choices
                                    [Paso 3] Reporte de calidad
                                         │
                                    [Paso 4] Importar a BD
                                         │  └─ actualiza FuenteDatos.estado → "completo"
                                         │
                                    [Paso 5] Descargar CSV reconstruido
```

---

## Estado actual (ya implementado)

| Fase | Descripción | Estado |
|------|-------------|--------|
| Trigger en data.html | Botón "Iniciar carga" → `etl-upload.html?fuente=<id>` | ✅ |
| Backend upload + inspect | `CargaArchivo`, `POST /upload/` | ✅ |
| UI mapeo de columnas | `etl-upload.html` paso 2, `mapeo_carga`, `campos_destino` | ✅ |
| Backend validaciones | `validar_carga`, tipos: nulo, tipo_invalido, longitud, choices | ✅ |
| UI reporte de calidad | `etl-upload.html` paso 3 | ✅ |

---

## Fases pendientes

---

### Fase 1 — Sincronizar mapeo con modelos reales

#### 1.1 — `campos_destino` dinámico

**Problema actual**: el endpoint `GET /api/etl/campos-destino/` devuelve 5 modelos hardcodeados.
Si el modelo cambia, la UI queda desactualizada.

**Solución**: reemplazar el hardcode por introspección real usando `_meta.get_fields()`,
el mismo mecanismo que ya usa `AppConfig.ready()` para generar `catalogo.js`.

El endpoint debe devolver, para cada campo:
```json
{
  "Publicacion": [
    {
      "nombre": "tipo",
      "verbose_name": "Tipo de publicación",
      "tipo": "CharField",
      "requerido": true,
      "choices": [
        { "valor": "articulo_revista", "etiqueta": "Artículo de revista" },
        { "valor": "capitulo_libro",   "etiqueta": "Capítulo de libro" }
      ]
    }
  ]
}
```

**Archivos a tocar**:
- `app/views.py` — reescribir `campos_destino`
- Los modelos listados deben coincidir con `GRUPOS_CATALOGO` en `views.py`

---

#### 1.2 — Sub-panel de mapeo de valores para campos con choices

**Cuándo aparece**: el usuario mapea una columna a un campo que tiene `choices`.

**UI**:
```
Columna origen: "biblio_type"        → Campo destino: Publicacion.tipo
  muestra: "Journal Article"         ┌────────────────────────────────────┐
           "Book Chapter"            │ Mapeo de valores permitidos         │
           "Report"                  │  "Journal Article" → [articulo ▼]  │
                                     │  "Book Chapter"    → [capitulo ▼]  │
                                     │  "Report"          → [informe  ▼]  │
                                     └────────────────────────────────────┘
```

Cada valor distinto que aparece en la muestra de la columna se lista con un `<select>`
que muestra las opciones del campo destino. El usuario elige el mapeo o selecciona
`— ignorar —` para descartar esa fila.

**Modelo**: agregar `mapeo_valores` a `MapeoColumna` como JSONField:
```python
# en app/models/datos.py — MapeoColumna
mapeo_valores = models.JSONField("mapeo de valores", default=dict, blank=True)
# Estructura: { "Journal Article": "articulo_revista", "Book Chapter": "capitulo_libro" }
```

**Migración**: nueva migración para el campo `mapeo_valores`.

**Endpoint de guardado**: `POST /api/fuentes-datos/{id}/carga/{carga_id}/mapeo/` ya existe —
agregar `mapeo_valores` al payload por columna:
```json
{
  "mapeos": [
    {
      "columna_origen": "biblio_type",
      "modelo_destino": "Publicacion",
      "campo_destino": "tipo",
      "transformacion": "directo",
      "mapeo_valores": {
        "Journal Article": "articulo_revista",
        "Book Chapter":    "capitulo_libro"
      }
    }
  ]
}
```

**Archivos a tocar**:
- `app/models/datos.py` — agregar `mapeo_valores` a `MapeoColumna`
- `app/views.py` — actualizar `mapeo_carga` para leer/escribir `mapeo_valores`
- `docs/pages/etl-upload.html` — agregar sub-panel al paso 2

---

### Fase 2 — Validación de calidad considera mapeo de valores

**Problema actual**: `validar_carga` marca como `fuera_de_vocabulario` cualquier valor que no
esté en `choices`. Si el usuario ya mapeó `"Journal Article" → "articulo_revista"`, ese valor
debe pasar la validación.

**Corrección**: en `_validar_columna`, leer `mapeo.mapeo_valores` y aplicar la traducción antes
de validar contra `choices`.

Flujo:
1. Leer valor de la celda
2. Si `mapeo.mapeo_valores` tiene una entrada para ese valor → sustituir por el valor canónico
3. Luego validar tipo, longitud, choices, etc.

**Archivos a tocar**:
- `app/views.py` — `_validar_columna` + `validar_carga`

---

### Fase 3 — Importación a base de datos

**Endpoint nuevo**:
```
POST /api/fuentes-datos/<id>/carga/<carga_id>/importar/
Response:
{
  "importados": 40,
  "omitidos":   13,
  "errores_fila": [
    { "fila": 5, "columna": "latitud", "motivo": "tipo_invalido" }
  ],
  "estado_fuente": "completo"
}
```

**Lógica**:
1. Cargar el archivo (Excel/CSV) desde `CargaArchivo.archivo`
2. Leer los mapeos (`MapeoColumna`) incluyendo `mapeo_valores`
3. Por cada fila del DataFrame:
   - Agrupar campos por `modelo_destino`
   - Aplicar `mapeo_valores` donde corresponda
   - Intentar `Model.objects.update_or_create(...)` con los campos mapeados
   - Registrar errores sin detener el proceso
4. Actualizar `CargaArchivo.estado → "importado"`
5. Si no hay errores: `FuenteDatos.estado → "completo"`
6. Si hay errores: `FuenteDatos.estado → "con_errores"`

**Orden de creación de modelos** (respetar dependencias FK):
```
Region → Sitio → Parcela → Publicacion → ResultadoPublicacion
                          └─ Cobertura ─┘
```

**URL nueva**:
```python
path("api/fuentes-datos/<int:fuente_id>/carga/<int:carga_id>/importar/", views.importar_carga)
```

**Archivos a tocar**:
- `app/views.py` — nueva función `importar_carga`
- `app/urls.py` — agregar URL
- `docs/pages/etl-upload.html` — reemplazar `alert` del paso 4 con pantalla de resultado

**UI del resultado (paso 4)**:
```
┌─ Importación completada ───────────────────────────────────────┐
│  ✅ 40 registros importados                                     │
│  ⚠️  13 filas omitidas (con errores)                            │
│                                                                 │
│  Errores detalle:                                               │
│  Fila 5  · latitud    · "N/A" no es número                     │
│  Fila 12 · tipo       · valor no reconocido                    │
│                                                                 │
│  [ Descargar CSV ↓ ]     [ Ver fuente en data.html ]           │
└─────────────────────────────────────────────────────────────────┘
```

---

### Fase 4 — Descarga Excel post-importación ✅

**Qué**: exportar los registros que se importaron tal como quedaron en BD — con las columnas
del modelo Django y los valores canónicos (no el archivo original). Un único `.xlsx` con
una pestaña por cada vista desnormalizada (`submuestra_gei`, `unidad_muestreo`), igual a como
se ven en `etl-datos.html`.

**Endpoint**:
```
GET /api/fuentes-datos/<id>/carga/<carga_id>/exportar/
Response: archivo .xlsx (Content-Disposition: attachment), una hoja por vista con datos
```

**Lógica**: `carga.pks_importados` (ya guardado por `importar_carga`) da, por modelo, los pk
creados/reutilizados por esta carga. `_preparar_vista_carga` arma el queryset desnormalizado
por vista (compartido con `datos_carga`); `exportar_carga` recorre todas las vistas, arma un
`DataFrame` por cada una con datos y las escribe con `pandas.ExcelWriter(engine="openpyxl")`.

**Archivos tocados**:
- `app/api/etl/views.py` — `_preparar_vista_carga`, `_fila_desde_objeto` (refactor compartido),
  `exportar_carga`
- `app/api/urls.py` — URL `exportar-carga`
- `docs/pages/etl-datos.html` — botón "⬇ Descargar Excel"

---

### Fase 5 — Visor de modelo de datos (v2 — dejar para el final)

UI para que el equipo proponga cambios al modelo de datos sin tocar código:
- Agregar campos a modelos existentes
- Modificar opciones (`choices`) de campos
- Agregar nuevas entidades

**Decisión**: no implementar en esta iteración. Anotar como deuda técnica.

---

## Orden de ejecución recomendado

| # | Fase | Depende de | Esfuerzo |
|---|------|------------|---------|
| 1 | `campos_destino` dinámico (1.1) | — | pequeño |
| 2 | Migración + lógica `mapeo_valores` (1.2) | 1 | mediano |
| 3 | UI sub-panel de valores en etl-upload.html (1.2) | 2 | mediano |
| 4 | `_validar_columna` considera `mapeo_valores` | 2 | pequeño |
| 5 | Backend `importar_carga` + URL | 2 | mediano |
| 6 | UI resultado importación en etl-upload.html | 5 | pequeño |
| 7 | Backend `exportar_carga` + `ids_importados` | 5 | mediano |
| 8 | Botón descarga CSV en UI | 7 | pequeño |

---

## Mapeo inicial sugerido — `data/Base_de_Datos_2025.xlsx`

Hoja `Documentos2025_1`:

| Columna Excel | Modelo.campo Django |
|---|---|
| Author | `Publicacion.autores` |
| Title | `Publicacion.titulo` |
| DOI | `Publicacion.doi` |
| Year | `Publicacion.anio` |
| biblio_type / Publication Type | `Publicacion.tipo` (campo con choices) |
| Region Natural | `Region.nombre` |
| Departamento | `Sitio.departamento` |
| Municipio | `Sitio.municipio` |
| Latitud | `Sitio.latitud` |
| Longitud | `Sitio.longitud` |
| Altitud | `Sitio.altitud` |
| Ecosistema / Cobertura | `Cobertura.nombre` |
| Cobertura IPCC | `Cobertura.cobertura_ipcc` |
| Contenido de Carbono en biomasa aérea (tC/ha) | `ResultadoPublicacion.carbono_ba_tc_ha` |
| CO2 Flux | `ResultadoPublicacion.co2_flux` |
| CH4 Flux | `ResultadoPublicacion.ch4_flux` |
| N2O Flux | `ResultadoPublicacion.n2o_flux` |
