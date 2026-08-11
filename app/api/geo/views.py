from django.http import JsonResponse
from django.views.decorators.http import require_GET

from app.models import Sitio, SubmuestraCO2


@require_GET
def sitios_geojson(request):
    """GeoJSON (FeatureCollection) de los Sitio georreferenciados, con sus
    unidades de muestreo, proyecto(s) y un resumen de sus mediciones de CO₂
    como metadata. Pensado para consumirse directo desde un cliente Leaflet
    (L.geoJSON(url))."""
    sitios = (
        Sitio.objects
        .select_related("municipio", "municipio__departamento")
        .prefetch_related(
            "unidades_muestreo__tipo",
            "unidades_muestreo__unidad_experimental__proyecto",
        )
    )

    # Última lectura, conteo y rango de fechas por sitio, en una sola pasada
    # (evita N+1: una query para todas las submuestras en vez de una por sitio).
    resumen_por_sitio = {}
    submuestras = (
        SubmuestraCO2.objects
        .exclude(fecha=None)
        .select_related("muestra__unidad_muestreo", "muestra__unidad_medida")
        .order_by("fecha")
    )
    for sub in submuestras:
        sitio_id = sub.muestra.unidad_muestreo_id and sub.muestra.unidad_muestreo.sitio_id
        if sitio_id is None:
            continue
        resumen = resumen_por_sitio.setdefault(sitio_id, {
            "total_muestras": 0, "primera_fecha": None, "ultima_fecha": None,
            "ultimo_valor": None, "ultima_unidad": None,
        })
        resumen["total_muestras"] += 1
        if resumen["primera_fecha"] is None or sub.fecha < resumen["primera_fecha"]:
            resumen["primera_fecha"] = sub.fecha
        if resumen["ultima_fecha"] is None or sub.fecha >= resumen["ultima_fecha"]:
            resumen["ultima_fecha"] = sub.fecha
            resumen["ultimo_valor"] = float(sub.valor) if sub.valor is not None else None
            resumen["ultima_unidad"] = sub.muestra.unidad_medida.codigo if sub.muestra.unidad_medida_id else None

    features = []
    for sitio in sitios:
        proyectos = {}
        unidades_muestreo = []
        for um in sitio.unidades_muestreo.all():
            unidades_muestreo.append({
                "id": um.pk,
                "nombre": um.nombre,
                "tipo": um.tipo.nombre if um.tipo_id else None,
            })
            ue = um.unidad_experimental
            if ue is not None and ue.proyecto_id and ue.proyecto_id not in proyectos:
                proyectos[ue.proyecto_id] = {"id": ue.proyecto_id, "nombre": ue.proyecto.nombre}

        resumen = resumen_por_sitio.get(sitio.pk, {})

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(sitio.longitud), float(sitio.latitud)],
            },
            "properties": {
                "id": sitio.pk,
                "nombre": sitio.nombre,
                "municipio": sitio.municipio.nombre if sitio.municipio_id else None,
                "departamento": (
                    sitio.municipio.departamento.nombre
                    if sitio.municipio_id and sitio.municipio.departamento_id else None
                ),
                "altitud": float(sitio.altitud) if sitio.altitud is not None else None,
                "uso_actual": sitio.get_uso_actual_display() if sitio.uso_actual else None,
                "proyectos": list(proyectos.values()),
                "unidades_muestreo": unidades_muestreo,
                "total_muestras_co2": resumen.get("total_muestras", 0),
                "rango_fechas": {
                    "desde": resumen["primera_fecha"].isoformat() if resumen.get("primera_fecha") else None,
                    "hasta": resumen["ultima_fecha"].isoformat() if resumen.get("ultima_fecha") else None,
                },
                "ultima_medicion_co2": (
                    {"fecha": resumen["ultima_fecha"].isoformat(), "valor": resumen["ultimo_valor"], "unidad": resumen["ultima_unidad"]}
                    if resumen.get("ultima_fecha") else None
                ),
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def series_co2(request):
    """Lecturas crudas de flujo de CO₂ (una fila por SubmuestraCO2 con fecha),
    con filtros opcionales por año, sitio, proyecto y departamento. No agrega
    ni convierte unidades -eso queda a criterio de quien consuma la serie-,
    solo devuelve el dato tal como está en la base para que el geoportal (u
    otro cliente) arme sus propios gráficos de tendencia/agregados."""
    qs = (
        SubmuestraCO2.objects
        .exclude(fecha=None)
        .select_related(
            "muestra__unidad_medida",
            "muestra__unidad_muestreo__sitio__municipio__departamento",
            "muestra__unidad_muestreo__unidad_experimental__proyecto",
        )
        .order_by("fecha")
    )

    anio = request.GET.get("anio")
    if anio:
        qs = qs.filter(fecha__year=anio)

    sitio_id = request.GET.get("sitio")
    if sitio_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio_id=sitio_id)

    proyecto_id = request.GET.get("proyecto")
    if proyecto_id:
        qs = qs.filter(muestra__unidad_muestreo__unidad_experimental__proyecto_id=proyecto_id)

    departamento_id = request.GET.get("departamento")
    if departamento_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio__municipio__departamento_id=departamento_id)

    resultados = []
    for sub in qs:
        um = sub.muestra.unidad_muestreo
        sitio = um.sitio if um else None
        ue = um.unidad_experimental if um else None
        resultados.append({
            "fecha": sub.fecha.isoformat(),
            "valor": float(sub.valor) if sub.valor is not None else None,
            "unidad": sub.muestra.unidad_medida.codigo if sub.muestra.unidad_medida_id else None,
            "gas": "CO2",
            "sitio_id": sitio.pk if sitio else None,
            "sitio_nombre": sitio.nombre if sitio else None,
            "departamento_id": sitio.municipio.departamento_id if sitio and sitio.municipio_id else None,
            "departamento": (
                sitio.municipio.departamento.nombre
                if sitio and sitio.municipio_id and sitio.municipio.departamento_id else None
            ),
            "proyecto_id": ue.proyecto_id if ue else None,
            "proyecto_nombre": ue.proyecto.nombre if ue and ue.proyecto_id else None,
        })

    return JsonResponse({"count": len(resultados), "resultados": resultados})
