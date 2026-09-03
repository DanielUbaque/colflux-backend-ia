"""Capa que aisla al asistente del proveedor de modelo de lenguaje.

El problema que resuelve: cada proveedor tiene su propio formato para declarar
funciones y para representar la conversacion. Google usa objetos de su SDK;
Groq usa el formato de OpenAI, que es JSON plano. Sin esta capa, cambiar de
proveedor obligaria a reescribir el orquestador.

Aqui se define un formato neutro y dos traductores. El orquestador habla
neutro y no sabe con quien esta hablando.

Formato neutro de mensajes:
    {"rol": "usuario",    "texto": str}
    {"rol": "asistente",  "texto": str, "llamadas": [LlamadaHerramienta]}
    {"rol": "herramienta","id": str, "nombre": str, "resultado": dict}

Formato neutro de herramientas (JSON Schema, como OpenAI):
    {"name": str, "description": str,
     "parameters": {"type": "object", "properties": {...}, "required": [...]}}
"""

import json
import os
import uuid
from dataclasses import dataclass, field

import requests


@dataclass
class LlamadaHerramienta:
    nombre: str
    argumentos: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class RespuestaModelo:
    texto: str = ""
    llamadas: list = field(default_factory=list)


class ErrorProveedor(RuntimeError):
    """Fallo al hablar con el proveedor. Lleva el mensaje original."""

    def __init__(self, proveedor, mensaje, codigo=None):
        self.proveedor = proveedor
        self.codigo = codigo
        super().__init__(f"[{proveedor}] {mensaje}")


# --------------------------------------------------------------------
# Google Gemini
# --------------------------------------------------------------------

class ProveedorGemini:
    nombre = "gemini"

    def __init__(self):
        self.modelo = os.environ.get("IA_MODELO_GENERACION", "gemini-3.5-flash")

    def _cliente(self):
        from google import genai
        clave = os.environ.get("GEMINI_API_KEY")
        if not clave:
            raise ErrorProveedor(self.nombre, "Falta GEMINI_API_KEY.")
        return genai.Client(api_key=clave)

    def _esquema(self, dic):
        from google.genai import types
        tipos = {
            "object": types.Type.OBJECT, "string": types.Type.STRING,
            "number": types.Type.NUMBER, "integer": types.Type.INTEGER,
            "boolean": types.Type.BOOLEAN, "array": types.Type.ARRAY,
        }
        kwargs = {"type": tipos.get(dic.get("type", "string"), types.Type.STRING)}
        if dic.get("description"):
            kwargs["description"] = dic["description"]
        if dic.get("enum"):
            kwargs["enum"] = list(dic["enum"])
        if dic.get("properties"):
            kwargs["properties"] = {k: self._esquema(v) for k, v in dic["properties"].items()}
        if dic.get("required"):
            kwargs["required"] = list(dic["required"])
        if dic.get("items"):
            kwargs["items"] = self._esquema(dic["items"])
        return types.Schema(**kwargs)

    def _traducir_mensajes(self, mensajes):
        from google.genai import types
        contenidos = []
        for m in mensajes:
            if m["rol"] == "usuario":
                contenidos.append(types.Content(
                    role="user", parts=[types.Part(text=m["texto"])]))
            elif m["rol"] == "asistente":
                partes = []
                if m.get("texto"):
                    partes.append(types.Part(text=m["texto"]))
                for ll in m.get("llamadas", []):
                    partes.append(types.Part(function_call=types.FunctionCall(
                        name=ll.nombre, args=ll.argumentos)))
                if partes:
                    contenidos.append(types.Content(role="model", parts=partes))
            elif m["rol"] == "herramienta":
                contenidos.append(types.Content(role="user", parts=[
                    types.Part.from_function_response(
                        name=m["nombre"], response={"resultado": m["resultado"]})]))
        return contenidos

    def conversar(self, mensajes, herramientas, instruccion_sistema, temperatura=0.2):
        from google.genai import types
        cliente = self._cliente()
        declaraciones = [
            types.FunctionDeclaration(
                name=h["name"], description=h.get("description", ""),
                parameters=self._esquema(h["parameters"]),
            )
            for h in herramientas
        ]
        config = types.GenerateContentConfig(
            system_instruction=instruccion_sistema,
            tools=[types.Tool(function_declarations=declaraciones)] if declaraciones else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=temperatura,
        )
        try:
            r = cliente.models.generate_content(
                model=self.modelo,
                contents=self._traducir_mensajes(mensajes),
                config=config,
            )
        except Exception as exc:
            codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            raise ErrorProveedor(self.nombre, str(exc)[:500], codigo) from exc

        llamadas = [
            LlamadaHerramienta(nombre=fc.name, argumentos=dict(fc.args or {}))
            for fc in (r.function_calls or [])
        ]
        return RespuestaModelo(texto=(r.text or "").strip(), llamadas=llamadas)


# --------------------------------------------------------------------
# Groq (formato compatible con OpenAI)
# --------------------------------------------------------------------

class ProveedorGroq:
    nombre = "groq"
    BASE = "https://api.groq.com/openai/v1"

    def __init__(self):
        self.modelo = os.environ.get("IA_MODELO_GENERACION", "llama-3.3-70b-versatile")

    def _clave(self):
        clave = os.environ.get("GROQ_API_KEY")
        if not clave:
            raise ErrorProveedor(self.nombre, "Falta GROQ_API_KEY.")
        return clave

    def _traducir_mensajes(self, mensajes, instruccion_sistema):
        salida = [{"role": "system", "content": instruccion_sistema}]
        for m in mensajes:
            if m["rol"] == "usuario":
                salida.append({"role": "user", "content": m["texto"]})
            elif m["rol"] == "asistente":
                msg = {"role": "assistant", "content": m.get("texto") or ""}
                if m.get("llamadas"):
                    msg["tool_calls"] = [
                        {"id": ll.id, "type": "function",
                         "function": {"name": ll.nombre,
                                      "arguments": json.dumps(ll.argumentos, ensure_ascii=False)}}
                        for ll in m["llamadas"]
                    ]
                salida.append(msg)
            elif m["rol"] == "herramienta":
                salida.append({
                    "role": "tool", "tool_call_id": m["id"], "name": m["nombre"],
                    "content": json.dumps(m["resultado"], ensure_ascii=False, default=str),
                })
        return salida

    def conversar(self, mensajes, herramientas, instruccion_sistema, temperatura=0.2):
        cuerpo = {
            "model": self.modelo,
            "messages": self._traducir_mensajes(mensajes, instruccion_sistema),
            "temperature": temperatura,
        }
        if herramientas:
            cuerpo["tools"] = [{"type": "function", "function": h} for h in herramientas]
            cuerpo["tool_choice"] = "auto"

        try:
            r = requests.post(
                f"{self.BASE}/chat/completions",
                headers={"Authorization": f"Bearer {self._clave()}",
                         "Content-Type": "application/json"},
                json=cuerpo, timeout=90,
            )
        except requests.RequestException as exc:
            raise ErrorProveedor(self.nombre, f"Sin conexion: {exc}") from exc

        if r.status_code != 200:
            raise ErrorProveedor(self.nombre, r.text[:500], r.status_code)

        datos = r.json()
        mensaje = datos["choices"][0]["message"]
        llamadas = []
        for tc in mensaje.get("tool_calls") or []:
            try:
                argumentos = json.loads(tc["function"].get("arguments") or "{}")
            except ValueError:
                argumentos = {}
            llamadas.append(LlamadaHerramienta(
                nombre=tc["function"]["name"], argumentos=argumentos, id=tc["id"]))
        return RespuestaModelo(texto=(mensaje.get("content") or "").strip(), llamadas=llamadas)

    def listar_modelos(self):
        r = requests.get(f"{self.BASE}/models",
                         headers={"Authorization": f"Bearer {self._clave()}"}, timeout=30)
        if r.status_code != 200:
            raise ErrorProveedor(self.nombre, r.text[:300], r.status_code)
        return sorted(m["id"] for m in r.json().get("data", []))


PROVEEDORES = {"gemini": ProveedorGemini, "groq": ProveedorGroq}


def obtener_proveedor(nombre=None):
    elegido = (nombre or os.environ.get("IA_PROVEEDOR", "gemini")).strip().lower()
    if elegido not in PROVEEDORES:
        raise ErrorProveedor(elegido, f"Proveedor desconocido. Opciones: {', '.join(PROVEEDORES)}")
    return PROVEEDORES[elegido]()
