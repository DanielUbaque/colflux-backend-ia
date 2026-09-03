"""Consultas que el asistente puede pedir.

Cada funcion es una operacion cerrada y validada. El modelo de lenguaje elige
cual usar y con que parametros, pero nunca escribe SQL ni toca el ORM: solo
llega hasta aqui. Todas devuelven diccionarios simples, listos para entregarle
el resultado de vuelta al modelo.
"""

from datetime import date, datetime
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min

from app.models import (
    MedicionRapidaChat, MuestraAmbiental, Sitio, SubmuestraGEI,
)

GASES = {"CO2", "CH4", "N2O"}

AMBIENTALES = {
    "temperatura_suelo": ("soil_temp", "grados C"),
    "temperatura_aire": ("air_temp", "grados C"),
    "humedad_relativa": ("relat_humid", "%"),
    "nivel_agua": ("water_level", "cm"),
    "presion_atmosferica": ("atm_press", "hPa"),
    "punto_rocio": ("dew_point", "grados C"),
}

VARIABLES_VALIDAS = sorted(GASES | set(AMBIENTALES))


def _num(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def _fecha(valor):
    if not valor:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()[:10]
    return str(valor)[:10]


def _parsear_fecha(texto):
    if not texto:
        return None
    try:
        return datetime.strptime(str(texto)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def listar_sitios(filtro=None):
    """Devuelve los sitios registrados. Sirve para que el asistente resuelva
    nombres parciales antes de consultar."""
    consulta = Sitio.objects.all()
    if filtro:
        consulta = consulta.filter(nombre__icontains=filtro)
    sitios = consulta.order_by("nombre")[:40]
    return {
        "total": consulta.count(),
        "sitios": [
            {"id": s.id, "nombre": s.nombre, "latitud": _num(s.latitud),
             "longitud": _num(s.longitud)}
            for s in sitios
        ],
    }


def _resolver_sitio(nombre_sitio):
    """Busca un sitio por nombre. Devuelve (sitio, error)."""
    if not nombre_sitio:
        return None, None
    coincidencias = list(Sitio.objects.filter(nombre__icontains=nombre_sitio)[:6])
    if not coincidencias:
        return None, {
            "error": f"No hay ningun sitio cuyo nombre contenga '{nombre_sitio}'.",
            "sugerencia": "Usa listar_sitios para ver los nombres disponibles.",
        }
    if len(coincidencias) > 1:
        return None, {
            "error": f"'{nombre_sitio}' coincide con varios sitios.",
            "candidatos": [s.nombre for s in coincidencias],
            "sugerencia": "Pide a la persona que precise cual.",
        }
    return coincidencias[0], None


def _base_gei(variable, sitio, desde, hasta):
    consulta = SubmuestraGEI.objects.filter(muestra__gas__iexact=variable)
    if sitio:
        consulta = consulta.filter(muestra__unidad_muestreo__sitio=sitio)
    if desde:
        consulta = consulta.filter(fecha__gte=desde)
    if hasta:
        consulta = consulta.filter(fecha__lte=hasta)
    return consulta


def _base_ambiental(campo, sitio, desde, hasta):
    consulta = MuestraAmbiental.objects.filter(**{f"{campo}__isnull": False})
    if sitio:
        consulta = consulta.filter(unidad_muestreo__sitio=sitio)
    if desde:
        consulta = consulta.filter(fecha__gte=desde)
    if hasta:
        consulta = consulta.filter(fecha__lte=hasta)
    return consulta


def _base_chat(variable, sitio, desde, hasta):
    consulta = MedicionRapidaChat.objects.filter(variable=variable)
    if sitio:
        consulta = consulta.filter(sitio=sitio)
    if desde:
        consulta = consulta.filter(fecha__gte=desde)
    if hasta:
        consulta = consulta.filter(fecha__lte=hasta)
    return consulta


def consultar_promedio(variable, sitio=None, desde=None, hasta=None):
    """Promedio de una variable, opcionalmente acotado por sitio y fechas.

    Reporta por separado los datos del ETL formal y los registrados por chat,
    para que quede claro de donde sale cada cifra."""
    variable = (variable or "").strip()
    if variable not in VARIABLES_VALIDAS:
        return {"error": f"Variable no reconocida: '{variable}'.",
                "variables_validas": VARIABLES_VALIDAS}

    obj_sitio, error = _resolver_sitio(sitio)
    if error:
        return error

    d, h = _parsear_fecha(desde), _parsear_fecha(hasta)
    resultado = {
        "variable": variable,
        "sitio": obj_sitio.nombre if obj_sitio else "todos los sitios",
        "desde": _fecha(d), "hasta": _fecha(h),
        "fuentes": {},
    }

    if variable in GASES:
        agg = _base_gei(variable, obj_sitio, d, h).aggregate(
            promedio=Avg("valor"), n=Count("id"),
            minimo=Min("valor"), maximo=Max("valor"),
        )
    else:
        campo, unidad = AMBIENTALES[variable]
        agg = _base_ambiental(campo, obj_sitio, d, h).aggregate(
            promedio=Avg(campo), n=Count("id"),
            minimo=Min(campo), maximo=Max(campo),
        )
        resultado["unidad"] = unidad

    if agg["n"]:
        resultado["fuentes"]["mediciones_formales"] = {
            "n": agg["n"], "promedio": round(_num(agg["promedio"]), 4),
            "minimo": _num(agg["minimo"]), "maximo": _num(agg["maximo"]),
        }

    agg_chat = _base_chat(variable, obj_sitio, d, h).aggregate(
        promedio=Avg("valor"), n=Count("id"),
        minimo=Min("valor"), maximo=Max("valor"),
    )
    if agg_chat["n"]:
        resultado["fuentes"]["registradas_por_chat"] = {
            "n": agg_chat["n"], "promedio": round(_num(agg_chat["promedio"]), 4),
            "minimo": _num(agg_chat["minimo"]), "maximo": _num(agg_chat["maximo"]),
        }

    if not resultado["fuentes"]:
        resultado["sin_datos"] = True
        resultado["mensaje"] = "No hay mediciones que cumplan esos criterios."
    return resultado


def consultar_ultima_medicion(variable, sitio=None):
    """La medicion mas reciente de una variable."""
    variable = (variable or "").strip()
    if variable not in VARIABLES_VALIDAS:
        return {"error": f"Variable no reconocida: '{variable}'.",
                "variables_validas": VARIABLES_VALIDAS}

    obj_sitio, error = _resolver_sitio(sitio)
    if error:
        return error

    candidatos = []

    if variable in GASES:
        fila = _base_gei(variable, obj_sitio, None, None).select_related(
            "muestra__unidad_muestreo__sitio").order_by("-fecha", "-hora").first()
        if fila:
            candidatos.append({
                "fecha": _fecha(fila.fecha),
                "valor": _num(fila.valor),
                "sitio": getattr(fila.muestra.unidad_muestreo.sitio, "nombre", None),
                "fuente": "medicion formal (ETL)",
            })
    else:
        campo, unidad = AMBIENTALES[variable]
        fila = _base_ambiental(campo, obj_sitio, None, None).select_related(
            "unidad_muestreo__sitio").order_by("-fecha", "-hora").first()
        if fila:
            candidatos.append({
                "fecha": _fecha(fila.fecha),
                "valor": _num(getattr(fila, campo)),
                "unidad": unidad,
                "sitio": getattr(fila.unidad_muestreo.sitio, "nombre", None),
                "fuente": "medicion formal (ETL)",
            })

    fila_chat = _base_chat(variable, obj_sitio, None, None).select_related(
        "sitio").order_by("-fecha", "-created_at").first()
    if fila_chat:
        candidatos.append({
            "fecha": _fecha(fila_chat.fecha),
            "valor": _num(fila_chat.valor),
            "unidad": fila_chat.unidad or None,
            "sitio": fila_chat.sitio.nombre,
            "fuente": "registrada por chat",
        })

    if not candidatos:
        return {"variable": variable, "sin_datos": True,
                "mensaje": "No hay mediciones registradas de esa variable."}

    candidatos.sort(key=lambda c: c["fecha"] or "", reverse=True)
    return {"variable": variable, "ultima": candidatos[0],
            "otras_fuentes": candidatos[1:]}
