"""El cerebro del asistente.

Le entrega al modelo una lista cerrada de funciones. El modelo decide cual
usar y con que parametros; este modulo las ejecuta, le devuelve el resultado y
deja que redacte la respuesta final. El modelo nunca toca la base de datos.

Es independiente del proveedor: habla el formato neutro definido en
app/ia/proveedores.py, asi que cambiar de Google a Groq es una variable de
entorno.

La unica funcion que escribe no escribe: propone. El dato queda pendiente en
RegistroChatIA hasta que la persona confirme explicitamente.
"""

import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from app.models import MedicionRapidaChat, RegistroChatIA, Sitio

from .busqueda import buscar_fragmentos, buscar_terminos
from .consultas import (
    VARIABLES_VALIDAS, _resolver_sitio, consultar_promedio,
    consultar_ultima_medicion, listar_sitios,
)
from .proveedores import ErrorProveedor, obtener_proveedor

MAX_VUELTAS = 5

# Por debajo de esta similitud un resultado no se cita como fuente.
UMBRAL_SIMILITUD = float(os.environ.get("ASISTENTE_UMBRAL_SIMILITUD", "0.75"))

# Cuantos intercambios anteriores se le recuerdan al modelo, y por cuanto
# tiempo. Sin esto cada mensaje empieza de cero y una conversacion de dos
# turnos entra en bucle: el modelo vuelve a pedir lo que ya le dijeron.
MEMORIA_TURNOS = int(os.environ.get("ASISTENTE_MEMORIA_TURNOS", "6"))
MEMORIA_MINUTOS = int(os.environ.get("ASISTENTE_MEMORIA_MINUTOS", "30"))

BASE_SISTEMA = """Eres el asistente de COLFLUX, una plataforma de monitoreo de
flujos de gases de efecto invernadero en ecosistemas colombianos, sobre todo
paramos y humedales.

Como responder:
- Siempre en espanol, breve y concreto.
- Escribe en texto plano. No uses notacion matematica de LaTeX como $CH_4$;
  escribe CH4.
- Si te saludan o hacen una pregunta general, conversa con naturalidad. No
  fuerces una busqueda cuando no hace falta.
- Nunca inventes cifras. Si una funcion dice que no hay datos, dilo tal cual.
- Cuando cites un dato numerico, menciona la fuente: medicion formal del ETL o
  registrada por chat.
- Si respondes con conocimiento general y no con datos de la plataforma,
  aclaralo.

Herramientas:
- Para observaciones cualitativas de campo (olores, colores, texturas del
  suelo, sensaciones ambientales) usa buscar_diccionario.
- Para preguntas sobre entrevistas, informes o notas usa buscar_documentos.
- Para cifras usa consultar_promedio o consultar_ultima_medicion.
- Si la persona quiere registrar una medicion usa proponer_guardar_medicion.
  Esa funcion NO guarda: solo prepara el dato. Muestra lo que entendiste y
  pide que confirmen escribiendo "confirmo".
- Si falta el sitio, la fecha, la variable o el valor, preguntalo antes de
  proponer nada. Pero en cuanto tengas esos cuatro, llama de una vez a
  proponer_guardar_medicion. No pidas una confirmacion previa de los
  campos: la funcion ya devuelve un resumen para confirmar.
- La unidad es opcional. No la exijas ni bloquees el registro por ella.
- Si la persona te dio un dato en un mensaje anterior de esta conversacion,
  usalo. No vuelvas a preguntarlo.
- Si dice hoy, ayer o una fecha en palabras, conviertela tu mismo a
  AAAA-MM-DD.
- No uses asteriscos para resaltar: el chat los muestra tal cual.
"""


def _instruccion_sistema():
    """Incluye la lista de sitios para que el modelo no gaste una peticion
    entera preguntandolos. Son pocos y casi nunca cambian."""
    nombres = list(Sitio.objects.order_by("nombre").values_list("nombre", flat=True)[:40])
    bloque = ""
    if nombres:
        bloque = ("\nSitios de monitoreo registrados: " + "; ".join(nombres) +
                  ".\nUsa estos nombres tal cual. Solo llama a listar_sitios si "
                  "necesitas coordenadas o si la lista parece incompleta.")
    return f"{BASE_SISTEMA}{bloque}\nHoy es {date.today().isoformat()}."


def _obj(props, requeridos=None):
    esquema = {"type": "object", "properties": props}
    if requeridos:
        esquema["required"] = requeridos
    return esquema


FUNCIONES = [
    {
        "name": "listar_sitios",
        "description": "Lista los sitios de monitoreo con sus coordenadas.",
        "parameters": _obj({
            "filtro": {"type": "string", "description": "Texto parcial del nombre. Opcional."},
        }),
    },
    {
        "name": "consultar_promedio",
        "description": "Promedio, minimo y maximo de una variable, opcionalmente por sitio y fechas.",
        "parameters": _obj({
            "variable": {"type": "string", "enum": VARIABLES_VALIDAS,
                         "description": "Variable a consultar."},
            "sitio": {"type": "string", "description": "Nombre del sitio. Opcional."},
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD. Opcional."},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD. Opcional."},
        }, ["variable"]),
    },
    {
        "name": "consultar_ultima_medicion",
        "description": "La medicion mas reciente de una variable, opcionalmente en un sitio.",
        "parameters": _obj({
            "variable": {"type": "string", "enum": VARIABLES_VALIDAS},
            "sitio": {"type": "string", "description": "Nombre del sitio. Opcional."},
        }, ["variable"]),
    },
    {
        "name": "buscar_diccionario",
        "description": ("Busca por significado en el diccionario de observaciones cualitativas de "
                        "campo del paramo. Devuelve la variable asociada y su regla de umbral."),
        "parameters": _obj({
            "texto": {"type": "string",
                      "description": "La observacion, tal como la describio la persona."},
        }, ["texto"]),
    },
    {
        "name": "buscar_documentos",
        "description": ("Busca por significado en entrevistas, informes y notas de campo. "
                        "Devuelve los parrafos mas relevantes con su documento de origen."),
        "parameters": _obj({
            "texto": {"type": "string", "description": "Lo que se quiere encontrar."},
        }, ["texto"]),
    },
    {
        "name": "proponer_guardar_medicion",
        "description": ("Prepara el registro de una medicion dictada por chat. NO la guarda: "
                        "devuelve un resumen para que la persona lo confirme."),
        "parameters": _obj({
            "sitio": {"type": "string", "description": "Nombre del sitio."},
            "fecha": {"type": "string", "description": "Fecha AAAA-MM-DD."},
            "variable": {"type": "string", "enum": VARIABLES_VALIDAS},
            "valor": {"type": "number", "description": "Valor numerico medido."},
            "unidad": {"type": "string", "description": "Unidad de medida. Opcional."},
        }, ["sitio", "fecha", "variable", "valor"]),
    },
]


def _similitud(distancia):
    return round(max(0.0, min(1.0, 1 - float(distancia))), 4)


def _buscar_diccionario(texto, fuentes, limite=4):
    coincidencias = []
    for t in buscar_terminos(texto, limite=limite):
        score = _similitud(t.distancia)
        if score < UMBRAL_SIMILITUD:
            continue
        contenido = " | ".join(p for p in [
            t.observacion_campo, t.definicion_ecologica,
            f"variable: {t.variable_asociada}" if t.variable_asociada else "",
            f"regla: {t.regla_cuantitativa}" if t.regla_cuantitativa else "",
            f"interpretacion: {t.interpretacion}" if t.interpretacion else "",
        ] if p)
        coincidencias.append({
            "similitud": score, "categoria": t.categoria,
            "observacion": t.observacion_campo,
            "variable_asociada": t.variable_asociada,
            "regla": t.regla_cuantitativa, "interpretacion": t.interpretacion,
        })
        fuentes.append({
            "source": f"Diccionario de campo - {t.categoria}" if t.categoria else "Diccionario de campo",
            "content": contenido, "score": score,
        })
    if not coincidencias:
        return {"coincidencias": [],
                "mensaje": "Ninguna entrada supera el umbral de relevancia."}
    return {"coincidencias": coincidencias}


def _buscar_documentos(texto, fuentes, limite=4):
    resultados = []
    for f in buscar_fragmentos(texto, limite=limite):
        score = _similitud(f.distancia)
        if score < UMBRAL_SIMILITUD:
            continue
        resultados.append({
            "similitud": score, "documento": f.documento.titulo,
            "tipo": f.documento.get_tipo_display(), "texto": f.texto,
        })
        fuentes.append({"source": f.documento.titulo, "content": f.texto, "score": score})
    if not resultados:
        return {"fragmentos": [], "mensaje": "No hay documentos indexados que respondan a eso."}
    return {"fragmentos": resultados}


def _proponer_guardar(sitio, fecha, variable, valor, unidad=""):
    obj_sitio, error = _resolver_sitio(sitio)
    if error:
        return error
    if obj_sitio is None:
        return {"error": "Falta indicar el sitio."}
    if variable not in VARIABLES_VALIDAS:
        return {"error": f"Variable no reconocida: '{variable}'.",
                "variables_validas": VARIABLES_VALIDAS}
    try:
        fecha_obj = datetime.strptime(str(fecha)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"error": f"Fecha invalida: '{fecha}'. Usa el formato AAAA-MM-DD."}
    if fecha_obj > date.today():
        return {"error": f"La fecha {fecha_obj} esta en el futuro."}
    try:
        valor_dec = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, TypeError):
        return {"error": f"Valor no numerico: '{valor}'."}

    return {
        "pendiente_de_confirmacion": True,
        "resumen": {
            "sitio": obj_sitio.nombre, "sitio_id": obj_sitio.id,
            "fecha": fecha_obj.isoformat(), "variable": variable,
            "valor": float(valor_dec), "unidad": unidad or "",
        },
        "instruccion": "Muestra este resumen y pide que confirmen escribiendo 'confirmo'.",
    }


def _ejecutar(nombre, argumentos, fuentes):
    try:
        if nombre == "listar_sitios":
            return listar_sitios(argumentos.get("filtro"))
        if nombre == "consultar_promedio":
            return consultar_promedio(**argumentos)
        if nombre == "consultar_ultima_medicion":
            return consultar_ultima_medicion(**argumentos)
        if nombre == "buscar_diccionario":
            return _buscar_diccionario(argumentos.get("texto", ""), fuentes)
        if nombre == "buscar_documentos":
            return _buscar_documentos(argumentos.get("texto", ""), fuentes)
        if nombre == "proponer_guardar_medicion":
            return _proponer_guardar(**argumentos)
        return {"error": f"Funcion desconocida: {nombre}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


CONFIRMACIONES = {"confirmo", "confirmar", "si confirmo", "si, confirmo",
                  "sí, confirmo", "sí confirmo"}


def confirmar_pendiente(usuario_externo_id, origen="api"):
    registro = (
        RegistroChatIA.objects
        .filter(usuario_externo_id=usuario_externo_id, origen=origen,
                confirmado=False, datos_pendientes_confirmar__isnull=False)
        .order_by("-created_at").first()
    )
    if not registro:
        return {"error": "No hay ningun dato pendiente de confirmar."}

    datos = registro.datos_pendientes_confirmar or {}
    medicion = MedicionRapidaChat.objects.create(
        sitio_id=datos["sitio_id"], fecha=datos["fecha"],
        variable=datos["variable"], valor=Decimal(str(datos["valor"])),
        unidad=datos.get("unidad", ""), observacion_texto=registro.pregunta,
        registro_chat=registro,
    )
    registro.confirmado = True
    registro.save(update_fields=["confirmado", "updated_at"])
    return {"guardado": True, "id": medicion.id,
            "mensaje": (f"Guardado: {datos['variable']} = {datos['valor']} "
                        f"en {datos['sitio']} el {datos['fecha']}.")}


def _historial(usuario_externo_id, origen):
    """Reconstruye los ultimos intercambios de esta persona desde la bitacora.

    El frontend solo envia el mensaje actual, sin historial. Sin esta memoria
    el modelo no recuerda lo que ya le dijeron y vuelve a preguntarlo.
    """
    desde = timezone.now() - timedelta(minutes=MEMORIA_MINUTOS)
    registros = list(
        RegistroChatIA.objects
        .filter(usuario_externo_id=usuario_externo_id, origen=origen,
                created_at__gte=desde)
        .order_by("-created_at")[:MEMORIA_TURNOS]
    )
    mensajes = []
    for r in reversed(registros):
        if r.pregunta:
            mensajes.append({"rol": "usuario", "texto": r.pregunta})
        if r.respuesta:
            mensajes.append({"rol": "asistente", "texto": r.respuesta, "llamadas": []})
    return mensajes


def responder(pregunta, usuario_externo_id="cli", origen="api"):
    """Punto de entrada unico. Devuelve {answer, sources, herramientas, ...}."""
    texto = (pregunta or "").strip()

    if texto.lower().rstrip(".!") in CONFIRMACIONES:
        resultado = confirmar_pendiente(usuario_externo_id, origen)
        mensaje = resultado.get("mensaje") or resultado.get("error", "")
        RegistroChatIA.objects.create(
            origen=origen, usuario_externo_id=usuario_externo_id,
            pregunta=texto, respuesta=mensaje,
            herramienta_usada="confirmar_pendiente", confirmado=True,
        )
        return {"answer": mensaje, "sources": [],
                "herramientas": ["confirmar_pendiente"],
                "pendiente_de_confirmacion": None}

    proveedor = obtener_proveedor()
    instruccion = _instruccion_sistema()
    mensajes = _historial(usuario_externo_id, origen)
    mensajes.append({"rol": "usuario", "texto": texto})

    herramientas_usadas = []
    fuentes = []
    pendiente = None
    respuesta = None

    for _ in range(MAX_VUELTAS):
        respuesta = proveedor.conversar(mensajes, FUNCIONES, instruccion)
        if not respuesta.llamadas:
            break

        mensajes.append({"rol": "asistente", "texto": respuesta.texto,
                         "llamadas": respuesta.llamadas})
        for llamada in respuesta.llamadas:
            herramientas_usadas.append(llamada.nombre)
            salida = _ejecutar(llamada.nombre, llamada.argumentos, fuentes)
            if isinstance(salida, dict) and salida.get("pendiente_de_confirmacion"):
                pendiente = salida["resumen"]
            mensajes.append({"rol": "herramienta", "id": llamada.id,
                             "nombre": llamada.nombre, "resultado": salida})

    texto_respuesta = respuesta.texto if respuesta else ""

    unicas = {}
    for f in fuentes:
        clave = (f["source"], f["content"][:80])
        if clave not in unicas or f["score"] > unicas[clave]["score"]:
            unicas[clave] = f
    fuentes_finales = sorted(unicas.values(), key=lambda f: f["score"], reverse=True)

    RegistroChatIA.objects.create(
        origen=origen, usuario_externo_id=usuario_externo_id,
        pregunta=texto, respuesta=texto_respuesta,
        herramienta_usada=", ".join(dict.fromkeys(herramientas_usadas))[:60],
        datos_pendientes_confirmar=pendiente, confirmado=False,
    )

    return {
        "answer": texto_respuesta,
        "sources": fuentes_finales,
        "herramientas": list(dict.fromkeys(herramientas_usadas)),
        "pendiente_de_confirmacion": pendiente,
        "proveedor": proveedor.nombre,
    }
