import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app.reglas.autollenado import (
    REGLAS, actualizar_parametros, aplicar_regla, deshacer_lote, detalle_regla, listar_reglas, previsualizar_regla,
)


def reglas_autollenado(request):
    return JsonResponse({"reglas": listar_reglas()}, json_dumps_params={"ensure_ascii": False})


def detalle_regla_autollenado(request, codigo):
    if codigo not in REGLAS:
        return JsonResponse({"error": f"Regla desconocida: {codigo}"}, status=404)
    return JsonResponse(detalle_regla(codigo), json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def parametros_regla_autollenado(request, codigo):
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    if codigo not in REGLAS:
        return JsonResponse({"error": f"Regla desconocida: {codigo}"}, status=404)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    parametros = actualizar_parametros(codigo, body.get("parametros") or {})
    return JsonResponse({"parametros": parametros}, json_dumps_params={"ensure_ascii": False})


def previsualizar_regla_autollenado(request, codigo):
    if codigo not in REGLAS:
        return JsonResponse({"error": f"Regla desconocida: {codigo}"}, status=404)
    return JsonResponse({"candidatos": previsualizar_regla(codigo)}, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def aplicar_regla_autollenado(request, codigo):
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    if codigo not in REGLAS:
        return JsonResponse({"error": f"Regla desconocida: {codigo}"}, status=404)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    aplicados = aplicar_regla(codigo, objeto_ids=body.get("objeto_ids"))
    return JsonResponse({"aplicados": aplicados}, json_dumps_params={"ensure_ascii": False})


@csrf_exempt
def deshacer_lote_autollenado(request, lote_id):
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)
    try:
        deshechas = deshacer_lote(lote_id)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    return JsonResponse({"deshechas": deshechas}, json_dumps_params={"ensure_ascii": False})
