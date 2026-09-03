"""El cerebro del asistente.

Le entrega a Gemini una lista cerrada de funciones. Gemini decide cual usar y
con que parametros; este modulo las ejecuta, le devuelve el resultado y deja
que redacte la respuesta final. Gemini nunca toca la base de datos.

La unica funcion que escribe no escribe: propone. El dato queda guardado como
pendiente en RegistroChatIA hasta que la persona confirme explicitamente.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from google.genai import types

from app.models import MedicionRapidaChat, RegistroChatIA

from .busqueda import buscar_terminos
from .cliente import MODELO_GENERACION, obtener_cliente
from .consultas import (
    VARIABLES_VALIDAS, _resolver_sitio, consultar_promedio,
    consultar_ultima_medicion, listar_sitios,
)

MAX_VUELTAS = 5

INSTRUCCION_SISTEMA = """Eres el asistente de COLFLUX, una plataforma de monitoreo
de flujos de gases de efecto invernadero en ecosistemas colombianos, sobre todo
paramos y humedales.

Reglas:
- Responde siempre en espanol, de forma breve y concreta.
- Nunca inventes cifras. Si una funcion dice que no hay datos, dilo tal cual.
- Cuando cites un dato numerico, menciona de que fuente viene (medicion formal
  del ETL o registrada por chat).
- Para preguntas sobre observaciones cualitativas de campo (olores, colores,
  texturas del suelo, sensaciones ambientales) usa buscar_diccionario.
- Si la persona quiere registrar una medicion, usa proponer_guardar_medicion.
  Esa funcion NO guarda: solo prepara el dato. Muestra a la persona lo que
  entendiste y pidele que confirme escribiendo "confirmo".
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


def _buscar_diccionario(texto, limite=4):
    resultados = buscar_terminos(texto, limite=limite)
    return {
        "coincidencias": [
            {
                "similitud": round((1 - t.distancia) * 100, 1),
                "categoria": t.categoria,
                "observacion": t.observacion_campo,
                "variable_asociada": t.variable_asociada,
                "regla": t.regla_cuantitativa,
                "interpretacion": t.interpretacion,
            }
            for t in resultados
        ]
    }


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


EJECUTORES = {
    "listar_sitios": lambda **kw: listar_sitios(kw.get("filtro")),
    "consultar_promedio": lambda **kw: consultar_promedio(**kw),
    "consultar_ultima_medicion": lambda **kw: consultar_ultima_medicion(**kw),
    "buscar_diccionario": lambda **kw: _buscar_diccionario(kw.get("texto", "")),
    "proponer_guardar_medicion": lambda **kw: _proponer_guardar(**kw),
}


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
    """Punto de entrada unico. Devuelve un diccionario con la respuesta."""
    texto = (pregunta or "").strip()
    if texto.lower() in {"confirmo", "confirmar", "si, confirmo", "sí, confirmo"}:
        resultado = confirmar_pendiente(usuario_externo_id, origen)
        RegistroChatIA.objects.create(
            origen=origen, usuario_externo_id=usuario_externo_id,
            pregunta=texto, respuesta=resultado.get("mensaje") or resultado.get("error", ""),
            herramienta_usada="confirmar_pendiente", confirmado=True,
        )
        return {"respuesta": resultado.get("mensaje") or resultado.get("error"),
                "herramientas": ["confirmar_pendiente"]}

    cliente = obtener_cliente()
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCCION_SISTEMA + f"\nHoy es {date.today().isoformat()}.",
        tools=[types.Tool(function_declarations=FUNCIONES)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )

    historial = [types.Content(role="user", parts=[types.Part(text=texto)])]
    herramientas_usadas = []
    pendiente = None

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
            ejecutor = EJECUTORES.get(nombre)
            if ejecutor is None:
                salida = {"error": f"Funcion desconocida: {nombre}"}
            else:
                try:
                    salida = ejecutor(**argumentos)
                except Exception as exc:
                    salida = {"error": f"{type(exc).__name__}: {exc}"}
            if isinstance(salida, dict) and salida.get("pendiente_de_confirmacion"):
                pendiente = salida["resumen"]
            partes.append(types.Part.from_function_response(name=nombre, response={"resultado": salida}))
        historial.append(types.Content(role="user", parts=partes))

    texto_respuesta = (respuesta.text or "").strip()

    RegistroChatIA.objects.create(
        origen=origen, usuario_externo_id=usuario_externo_id,
        pregunta=texto, respuesta=texto_respuesta,
        herramienta_usada=", ".join(dict.fromkeys(herramientas_usadas))[:60],
        datos_pendientes_confirmar=pendiente,
        confirmado=False,
    )

    return {
        "respuesta": texto_respuesta,
        "herramientas": list(dict.fromkeys(herramientas_usadas)),
        "pendiente_de_confirmacion": pendiente,
    }
