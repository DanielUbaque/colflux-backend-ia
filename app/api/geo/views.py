from django.http import JsonResponse
from django.views.decorators.http import require_GET

from app.models import Sitio, SubmuestraGEI


@require_GET
def sitios_geojson(request):
    """GeoJSON (FeatureCollection) de los Sitio georreferenciados, con sus
    unidades de muestreo, proyecto(s) y un resumen de sus mediciones como
    metadata: un resumen agregado (todos los gases, campos *_co2 por
    compatibilidad hacia atrás) y uno desagregado por gas en
    "resumen_por_gas" (CO2/CH4/N2O). Pensado para consumirse directo desde
    un cliente Leaflet (L.geoJSON(url))."""
    sitios = (
        Sitio.objects
        .select_related("municipio", "municipio__departamento")
        .prefetch_related(
            "unidades_muestreo__tipo",
            "unidades_muestreo__unidad_experimental__proyecto",
        )
    )

    # Última lectura, conteo y rango de fechas por sitio y por gas, en una
    # sola pasada (evita N+1: una query para todas las submuestras en vez de
    # una por sitio). Se acumula tanto el resumen agregado (todos los gases,
    # para no romper clientes que ya consumen total_muestras_co2 /
    # ultima_medicion_co2) como el resumen desagregado por gas.
    def _actualizar(resumen, sub):
        resumen["total_muestras"] += 1
        if resumen["primera_fecha"] is None or sub.fecha < resumen["primera_fecha"]:
            resumen["primera_fecha"] = sub.fecha
        if resumen["ultima_fecha"] is None or sub.fecha >= resumen["ultima_fecha"]:
            resumen["ultima_fecha"] = sub.fecha
            resumen["ultimo_valor"] = float(sub.valor) if sub.valor is not None else None
            resumen["ultima_unidad"] = sub.muestra.unidad_medida.codigo if sub.muestra.unidad_medida_id else None

    resumen_por_sitio = {}
    resumen_por_sitio_y_gas = {}
    submuestras = (
        SubmuestraGEI.objects
        .exclude(fecha=None)
        .select_related("muestra__unidad_muestreo", "muestra__unidad_medida")
        .order_by("fecha")
    )
    for sub in submuestras:
        sitio_id = sub.muestra.unidad_muestreo_id and sub.muestra.unidad_muestreo.sitio_id
        if sitio_id is None:
            continue
        gas = sub.muestra.gas or None

        _actualizar(resumen_por_sitio.setdefault(sitio_id, {
            "total_muestras": 0, "primera_fecha": None, "ultima_fecha": None,
            "ultimo_valor": None, "ultima_unidad": None,
        }), sub)
        if gas is not None:
            _actualizar(resumen_por_sitio_y_gas.setdefault(sitio_id, {}).setdefault(gas, {
                "total_muestras": 0, "primera_fecha": None, "ultima_fecha": None,
                "ultimo_valor": None, "ultima_unidad": None,
            }), sub)

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
        resumen_gases = resumen_por_sitio_y_gas.get(sitio.pk, {})

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
                # Resumen desagregado por gas (CO2/CH4/N2O), para las tarjetas
                # del panel RESUMEN y el filtrado por gas en el mapa. Solo
                # incluye los gases con muestras registradas en el sitio.
                "resumen_por_gas": {
                    gas: {
                        "total_muestras": r["total_muestras"],
                        "rango_fechas": {
                            "desde": r["primera_fecha"].isoformat() if r["primera_fecha"] else None,
                            "hasta": r["ultima_fecha"].isoformat() if r["ultima_fecha"] else None,
                        },
                        "ultima_medicion": (
                            {"fecha": r["ultima_fecha"].isoformat(), "valor": r["ultimo_valor"], "unidad": r["ultima_unidad"]}
                            if r["ultima_fecha"] else None
                        ),
                    }
                    for gas, r in resumen_gases.items()
                },
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def series_co2(request):
    """Lecturas crudas de flujo de gas (una fila por SubmuestraGEI con fecha),
    con filtros opcionales por año o rango de fechas, gas (CO2/CH4/N2O),
    sitio, proyecto, municipio, departamento y región. Sin ?gas= devuelve los
    tres gases mezclados -cada resultado trae su propio campo "gas" para que
    el cliente filtre/agrupe-. No agrega ni convierte unidades -eso queda a
    criterio de quien consuma la serie-, solo devuelve el dato tal como está
    en la base para que el geoportal (u otro cliente) arme sus propios
    gráficos de tendencia/agregados."""
    qs = (
        SubmuestraGEI.objects
        .exclude(fecha=None)
        .select_related(
            "muestra__unidad_medida",
            "muestra__unidad_muestreo__sitio__municipio__departamento__region",
            "muestra__unidad_muestreo__unidad_experimental__proyecto",
        )
        .order_by("fecha")
    )

    anio = request.GET.get("anio")
    if anio:
        qs = qs.filter(fecha__year=anio)

    desde = request.GET.get("desde")
    if desde:
        qs = qs.filter(fecha__gte=desde)

    hasta = request.GET.get("hasta")
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    gas = request.GET.get("gas")
    if gas:
        qs = qs.filter(muestra__gas=gas.upper())

    sitio_id = request.GET.get("sitio")
    if sitio_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio_id=sitio_id)

    proyecto_id = request.GET.get("proyecto")
    if proyecto_id:
        qs = qs.filter(muestra__unidad_muestreo__unidad_experimental__proyecto_id=proyecto_id)

    municipio_id = request.GET.get("municipio")
    if municipio_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio__municipio_id=municipio_id)

    departamento_id = request.GET.get("departamento")
    if departamento_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio__municipio__departamento_id=departamento_id)

    region_id = request.GET.get("region")
    if region_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio__municipio__departamento__region_id=region_id)

    resultados = []
    for sub in qs:
        um = sub.muestra.unidad_muestreo
        sitio = um.sitio if um else None
        ue = um.unidad_experimental if um else None
        resultados.append({
            "fecha": sub.fecha.isoformat(),
            "valor": float(sub.valor) if sub.valor is not None else None,
            "unidad": sub.muestra.unidad_medida.codigo if sub.muestra.unidad_medida_id else None,
            "gas": sub.muestra.gas or None,
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


@require_GET
def resumen_geografico(request):
    """Resumen agregado (conteo, promedio, mínimo, máximo, última medición)
    de SubmuestraGEI, agrupado por un nivel geográfico: ?nivel=departamento
    (default), municipio, region o sitio. Acepta los mismos filtros que
    /api/geo/series/ (gas, desde, hasta, proyecto, departamento, municipio,
    región) para acotar antes de agregar. Pensado para mapas tipo choropleth
    y tarjetas de resumen del geoportal.

    "region" no tiene geometría propia en el modelo (solo departamento y
    sitio la tienen): sus features salen con geometry=null y una lista
    "departamentos" con los departamentos que la componen, para que el
    cliente los dibuje/resalte. Igual pasa con "municipio" mientras no se
    cargue su geometría (geometry=null hasta entonces)."""
    nivel = request.GET.get("nivel", "departamento")
    if nivel not in ("departamento", "municipio", "region", "sitio"):
        return JsonResponse(
            {"error": "nivel debe ser uno de: departamento, municipio, region, sitio"}, status=400,
        )

    qs = (
        SubmuestraGEI.objects
        .exclude(fecha=None)
        .select_related(
            "muestra__unidad_medida",
            "muestra__unidad_muestreo__sitio__municipio__departamento__region",
            "muestra__unidad_muestreo__unidad_experimental__proyecto",
        )
    )

    gas = request.GET.get("gas")
    if gas:
        qs = qs.filter(muestra__gas=gas.upper())

    desde = request.GET.get("desde")
    if desde:
        qs = qs.filter(fecha__gte=desde)

    hasta = request.GET.get("hasta")
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    proyecto_id = request.GET.get("proyecto")
    if proyecto_id:
        qs = qs.filter(muestra__unidad_muestreo__unidad_experimental__proyecto_id=proyecto_id)

    municipio_id = request.GET.get("municipio")
    if municipio_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio__municipio_id=municipio_id)

    departamento_id = request.GET.get("departamento")
    if departamento_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio__municipio__departamento_id=departamento_id)

    region_id = request.GET.get("region")
    if region_id:
        qs = qs.filter(muestra__unidad_muestreo__sitio__municipio__departamento__region_id=region_id)

    grupos = {}
    for sub in qs:
        um = sub.muestra.unidad_muestreo
        sitio = um.sitio if um else None
        if sitio is None:
            continue
        municipio = sitio.municipio if sitio.municipio_id else None
        departamento = municipio.departamento if municipio and municipio.departamento_id else None

        if nivel != "sitio" and municipio is None:
            # departamento/municipio/region no se pueden agregar sin saber a
            # qué municipio pertenece el sitio.
            continue

        if nivel == "sitio":
            clave, nombre, geom = sitio.pk, sitio.nombre, {
                "type": "Point", "coordinates": [float(sitio.longitud), float(sitio.latitud)],
            }
            extra = {
                "municipio_id": municipio.pk if municipio else None,
                "municipio": municipio.nombre if municipio else None,
                "departamento_id": departamento.pk if departamento else None,
                "departamento": departamento.nombre if departamento else None,
            }
        elif nivel == "municipio":
            clave, nombre, geom = municipio.pk, municipio.nombre, municipio.geom
            extra = {
                "departamento_id": departamento.pk if departamento else None,
                "departamento": departamento.nombre if departamento else None,
            }
        elif nivel == "region":
            if departamento is None or departamento.region_id is None:
                continue
            region = departamento.region
            clave, nombre, geom = region.pk, region.get_nombre_display(), None
            extra = {}
        else:  # departamento
            if departamento is None:
                continue
            clave, nombre, geom = departamento.pk, departamento.nombre, departamento.geom
            extra = {
                "region_id": departamento.region_id,
                "region": departamento.region.get_nombre_display() if departamento.region_id else None,
            }

        g = grupos.setdefault(clave, {
            "nombre": nombre, "geom": geom, "extra": extra, "total_muestras": 0,
            "valores": [], "primera_fecha": None, "ultima_fecha": None,
            "ultimo_valor": None, "ultima_unidad": None, "departamentos": {},
        })
        g["total_muestras"] += 1
        if sub.valor is not None:
            g["valores"].append(float(sub.valor))
        if g["primera_fecha"] is None or sub.fecha < g["primera_fecha"]:
            g["primera_fecha"] = sub.fecha
        if g["ultima_fecha"] is None or sub.fecha >= g["ultima_fecha"]:
            g["ultima_fecha"] = sub.fecha
            g["ultimo_valor"] = float(sub.valor) if sub.valor is not None else None
            g["ultima_unidad"] = sub.muestra.unidad_medida.codigo if sub.muestra.unidad_medida_id else None
        if nivel == "region" and departamento is not None:
            g["departamentos"][departamento.pk] = departamento.nombre

    features = []
    for clave, g in grupos.items():
        valores = g["valores"]
        properties = {
            "id": clave,
            "nombre": g["nombre"],
            "total_muestras": g["total_muestras"],
            "promedio": sum(valores) / len(valores) if valores else None,
            "minimo": min(valores) if valores else None,
            "maximo": max(valores) if valores else None,
            "rango_fechas": {
                "desde": g["primera_fecha"].isoformat() if g["primera_fecha"] else None,
                "hasta": g["ultima_fecha"].isoformat() if g["ultima_fecha"] else None,
            },
            "ultima_medicion": (
                {"fecha": g["ultima_fecha"].isoformat(), "valor": g["ultimo_valor"], "unidad": g["ultima_unidad"]}
                if g["ultima_fecha"] else None
            ),
            **g["extra"],
        }
        if nivel == "region":
            properties["departamentos"] = [
                {"id": pk, "nombre": nom} for pk, nom in sorted(g["departamentos"].items(), key=lambda x: x[1])
            ]

        features.append({"type": "Feature", "geometry": g["geom"], "properties": properties})

    return JsonResponse({"type": "FeatureCollection", "features": features})
