"""Endpoint HTTP del asistente.

Habla el mismo protocolo que el motor ia-functions, para que el frontend de
chat ya construido funcione sin cambios:

    POST /api/asistente/chat/   {"message": "..."}
    ->  {"answer": "...", "sources": [{"source", "content", "score"}]}

Control de uso: quien envie la cabecera X-API-Key correcta pasa sin limite
(pensado para el bot de Telegram y otros llamadores de servidor). El resto
queda limitado por IP, porque una clave dentro del frontend seria publica de
todos modos y no protegeria nada.
"""

import json
import os

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

CLAVE_SERVIDOR = os.environ.get("ASISTENTE_API_KEY", "")
LIMITE_POR_HORA = int(os.environ.get("ASISTENTE_LIMITE_HORA", "30"))
LARGO_MAXIMO = 2000


def _ip(request):
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "desconocida")


def _excede_limite(request):
    clave = f"asistente:cuota:{_ip(request)}"
    usos = cache.get(clave, 0)
    if usos >= LIMITE_POR_HORA:
        return True
    cache.set(clave, usos + 1, 3600)
    return False


@csrf_exempt
@require_http_methods(["POST"])
def chat(request):
    from app.ia.asistente import responder

    try:
        cuerpo = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "El cuerpo debe ser JSON valido."}, status=400)

    mensaje = (cuerpo.get("message") or "").strip()
    if not mensaje:
        return JsonResponse({"error": "Falta el campo 'message'."}, status=400)
    if len(mensaje) > LARGO_MAXIMO:
        return JsonResponse(
            {"error": f"El mensaje supera los {LARGO_MAXIMO} caracteres."}, status=400)

    confiable = bool(CLAVE_SERVIDOR) and request.headers.get("X-API-Key") == CLAVE_SERVIDOR
    if not confiable and _excede_limite(request):
        return JsonResponse(
            {"error": "Demasiadas preguntas desde esta direccion. Intenta mas tarde."},
            status=429)

    usuario = (cuerpo.get("usuario") or _ip(request))[:120]
    origen = cuerpo.get("origen") if cuerpo.get("origen") in {"web", "telegram", "api"} else "web"

    try:
        resultado = responder(mensaje, usuario_externo_id=usuario, origen=origen)
    except Exception as exc:
        return JsonResponse(
            {"error": f"El asistente no pudo responder: {type(exc).__name__}"}, status=502)

    return JsonResponse({
        "answer": resultado.get("answer", ""),
        "sources": resultado.get("sources", []),
        "herramientas": resultado.get("herramientas", []),
        "pendiente_de_confirmacion": resultado.get("pendiente_de_confirmacion"),
    })


@csrf_exempt
@require_http_methods(["GET"])
def salud(request):
    """Chequeo rapido: no llama al modelo, solo confirma que el modulo carga."""
    from app.ia.cliente import MODELO_EMBEDDING, MODELO_GENERACION

    return JsonResponse({
        "status": "ok",
        "modelo_generacion": MODELO_GENERACION,
        "modelo_embedding": MODELO_EMBEDDING,
        "clave_configurada": bool(os.environ.get("GEMINI_API_KEY")),
        "limite_por_hora": LIMITE_POR_HORA,
    })
