"""El cerebro del asistente.

Le entrega a Gemini una lista cerrada de funciones. Gemini decide cual usar y
con que parametros; este modulo las ejecuta, le devuelve el resultado y deja
que redacte la respuesta final. Gemini nunca toca la base de datos.

La unica funcion que escribe no escribe: propone. El dato queda guardado como
pendiente en RegistroChatIA hasta que la persona confirme explicitamente.

La respuesta incluye las fuentes consultadas con el mismo formato que espera
el frontend: {source, content, score}.
"""

import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from google.genai import types

from app.models import MedicionRapidaChat, RegistroChatIA

from .busqueda import buscar_fragmentos, buscar_terminos
from .cliente import MODELO_GENERACION, obtener_cliente
from .consultas import (
    VARIABLES_VALIDAS, _resolver_sitio, consultar_promedio,
    consultar_ultima_medicion, listar_sitios,
)

MAX_VUELTAS = 5

# Por debajo de esta similitud un resultado no se considera relevante y no se
# cita como fuente. Evita que el asistente respalde una respuesta con una
# coincidencia que en realidad no venia al caso.
UMBRAL_SIMILITUD = float(os.environ.get("ASISTENTE_UMBRAL_SIMILITUD", "0.60"))

INSTRUCCION_SISTEMA = """Eres el asistente de COLFLUX, una plataforma de monitoreo
de flujos de gases de efecto invernadero en ecosistemas colombianos, sobre todo
paramos y humedales.

Como responder:
- Siempre en espanol, breve y concreto.
- Si te saludan o hacen una pregunta general, conversa con naturalidad. No
  fuerces una busqueda cuando no hace falta.
- Nunca inventes cifras. Si una funcion dice que no hay datos, dilo tal cual.
- Cuando cites un dato numerico, menciona de que fuente viene: medicion formal
  del ETL o registrada por chat.
- Si respondes con conocimiento general y no con datos de la plataforma,
  aclaralo.

Herramientas:
- Para observaciones cualitativas de campo (olores, colores, texturas del
  suelo, sensaciones ambientales) usa buscar_diccionario.
- Para preguntas sobre entrevistas, informes o notas usa buscar_documentos.
- Para cifras usa consultar_promedio o consultar_ultima_medicion. Si no sabes
  el nombre exacto de un sitio, resuelvelo antes con listar_sitios.
- Si la persona quiere registrar una medicion usa proponer_guardar_medicion.
  Esa funcion NO guarda: solo prepara el dato. Muestra lo que entendiste y
  pide que confirmen escribiendo "confirmo".
- Si falta el sitio, la fecha, la variable o el valor, preguntalo antes de
  proponer nada.
"""

FUNCIONES = [
    types.FunctionDeclaration(
        name="listar_sitios",
        description="Lista los sitios de monitoreo registrados. Util para resolver nombres parciales.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "filtro": types.Schema(
                    type=types.Type.STRING,
                    description="Texto parcial del nombre del sitio. Opcional.",
                ),
            },
        ),
    ),
    types.FunctionDeclaration(
        name="consultar_promedio",
        description="Promedio, minimo y maximo de una variable, opcionalmente por sitio y rango de fechas.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "variable": types.Schema(
                    type=types.Type.STRING, enum=VARIABLES_VALIDAS,
                    description="Variable a consultar.",
                ),
                "sitio": types.Schema(type=types.Type.STRING, description="Nombre del sitio. Opcional."),
                "desde": types.Schema(type=types.Type.STRING, description="Fecha inicial AAAA-MM-DD. Opcional."),
                "hasta": types.Schema(type=types.Type.STRING, description="Fecha final AAAA-MM-DD. Opcional."),
            },
            required=["variable"],
        ),
    ),
    types.FunctionDeclaration(
        name="consultar_ultima_medicion",
        description="La medicion mas reciente de una variable, opcionalmente en un sitio.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "variable": types.Schema(type=types.Type.STRING, enum=VARIABLES_VALIDAS),
                "sitio": types.Schema(type=types.Type.STRING, description="Nombre del sitio. Opcional."),
            },
            required=["variable"],
        ),
    ),
    types.FunctionDeclaration(
        name="buscar_diccionario",
        description=("Busca por significado en el diccionario de observaciones cualitativas de campo "
                     "del paramo. Devuelve la variable cuantitativa asociada y su regla de umbral."),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "texto": types.Schema(
                    type=types.Type.STRING,
                    description="La observacion de campo, tal como la describio la persona.",
                ),
            },
            required=["texto"],
        ),
    ),
    types.FunctionDeclaration(
        name="buscar_documentos",
        description=("Busca por significado en entrevistas, informes y notas de campo indexados. "
                     "Devuelve los parrafos mas relevantes con su documento de origen."),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "texto": types.Schema(type=types.Type.STRING, description="Lo que se quiere encontrar."),
            },
            required=["texto"],
        ),
    ),
    types.FunctionDeclaration(
        name="proponer_guardar_medicion",
        description=("Prepara el registro de una medicion dictada por chat. NO la guarda: "
                     "devuelve un resumen para que la persona lo confirme."),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "sitio": types.Schema(type=types.Type.STRING, description="Nombre del sitio."),
                "fecha": types.Schema(type=types.Type.STRING, description="Fecha AAAA-MM-DD."),
                "variable": types.Schema(type=types.Type.STRING, enum=VARIABLES_VALIDAS),
                "valor": types.Schema(type=types.Type.NUMBER, description="Valor numerico medido."),
                "unidad": types.Schema(type=types.Type.STRING, description="Unidad de medida. Opcional."),
            },
            required=["sitio", "fecha", "variable", "valor"],
        ),
    ),
]


def _similitud(distancia):
    return round(max(0.0, min(1.0, 1 - float(distancia))), 4)


def _buscar_diccionario(texto, fuentes, limite=4):
    encontrados = buscar_terminos(texto, limite=limite)
    coincidencias = []
    for t in encontrados:
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
            "similitud": score,
            "categoria": t.categoria,
            "observacion": t.observacion_campo,
            "variable_asociada": t.variable_asociada,
            "regla": t.regla_cuantitativa,
            "interpretacion": t.interpretacion,
        })
        fuentes.append({
            "source": f"Diccionario de campo - {t.categoria}" if t.categoria else "Diccionario de campo",
            "content": contenido,
            "score": score,
        })
    if not coincidencias:
        return {"coincidencias": [],
                "mensaje": "Ninguna entrada del diccionario supera el umbral de relevancia."}
    return {"coincidencias": coincidencias}


def _buscar_documentos(texto, fuentes, limite=4):
    encontrados = buscar_fragmentos(texto, limite=limite)
    resultados = []
    for f in encontrados:
        score = _similitud(f.distancia)
        if score < UMBRAL_SIMILITUD:
            continue
        resultados.append({
            "similitud": score,
            "documento": f.documento.titulo,
            "tipo": f.documento.get_tipo_display(),
            "texto": f.texto,
        })
        fuentes.append({
            "source": f.documento.titulo,
            "content": f.texto,
            "score": score,
        })
    if not resultados:
        return {"fragmentos": [],
                "mensaje": "No hay documentos indexados que respondan a eso."}
    return {"fragmentos": resultados}


def _proponer_guardar(sitio, fecha, variable, valor, unidad=""):
    """Valida sin escribir. Devuelve la propuesta o el motivo del rechazo."""
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
        valor_dec = Decimal(str(valor))
    except (InvalidOperation, TypeError):
        return {"error": f"Valor no numerico: '{valor}'."}

    return {
        "pendiente_de_confirmacion": True,
        "resumen": {
            "sitio": obj_sitio.nombre,
            "sitio_id": obj_sitio.id,
            "fecha": fecha_obj.isoformat(),
            "variable": variable,
            "valor": float(valor_dec),
            "unidad": unidad or "",
        },
        "instruccion": "Muestra este resumen y pide que confirmen escribiendo 'confirmo'.",
    }


def _ejecutar(nombre, argumentos, fuentes):
    """Despacha una llamada de funcion. Nunca lanza excepciones hacia afuera:
    un error se devuelve como resultado para que el modelo pueda corregirse."""
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


CONFIRMACIONES = {"confirmo", "confirmar", "si confirmo", "si, confirmo", "sí, confirmo", "sí confirmo"}


def confirmar_pendiente(usuario_externo_id, origen="api"):
    """Ejecuta la escritura que quedo pendiente en la ultima interaccion."""
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
        sitio_id=datos["sitio_id"],
        fecha=datos["fecha"],
        variable=datos["variable"],
        valor=Decimal(str(datos["valor"])),
        unidad=datos.get("unidad", ""),
        observacion_texto=registro.pregunta,
        registro_chat=registro,
    )
    registro.confirmado = True
    registro.save(update_fields=["confirmado", "updated_at"])
    return {
        "guardado": True,
        "id": medicion.id,
        "mensaje": (f"Guardado: {datos['variable']} = {datos['valor']} "
                    f"en {datos['sitio']} el {datos['fecha']}."),
    }


def responder(pregunta, usuario_externo_id="cli", origen="api"):
    """Punto de entrada unico. Devuelve {answer, sources, ...}."""
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

    cliente = obtener_cliente()
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCCION_SISTEMA + f"\nHoy es {date.today().isoformat()}.",
        tools=[types.Tool(function_declarations=FUNCIONES)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )

    historial = [types.Content(role="user", parts=[types.Part(text=texto)])]
    herramientas_usadas = []
    fuentes = []
    pendiente = None
    respuesta = None

    for _ in range(MAX_VUELTAS):
        respuesta = cliente.models.generate_content(
            model=MODELO_GENERACION, contents=historial, config=config,
        )
        llamadas = respuesta.function_calls or []
        if not llamadas:
            break

        historial.append(respuesta.candidates[0].content)
        partes = []
        for llamada in llamadas:
            nombre = llamada.name
            argumentos = dict(llamada.args or {})
            herramientas_usadas.append(nombre)
            salida = _ejecutar(nombre, argumentos, fuentes)
            if isinstance(salida, dict) and salida.get("pendiente_de_confirmacion"):
                pendiente = salida["resumen"]
            partes.append(types.Part.from_function_response(
                name=nombre, response={"resultado": salida}))
        historial.append(types.Content(role="user", parts=partes))

    texto_respuesta = (respuesta.text or "").strip() if respuesta else ""

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
        datos_pendientes_confirmar=pendiente,
        confirmado=False,
    )

    return {
        "answer": texto_respuesta,
        "sources": fuentes_finales,
        "herramientas": list(dict.fromkeys(herramientas_usadas)),
        "pendiente_de_confirmacion": pendiente,
    }
