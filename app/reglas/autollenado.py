"""Motor de reglas de autollenado: cada regla sabe calcular, para los registros
con un campo vacío, qué valor debería llevar. `REGLAS` es el registro central;
`aplicar_regla` persiste los valores calculados y deja auditoría en
`AplicacionRegla`.

Cada regla acepta `parametros` (dict) que ajustan su cálculo sin tocar código;
los valores guardados en `ReglaAutollenado.parametros` pisan a
`parametros_default`. Agregar una regla nueva = escribir una función
`calcular_candidatos(parametros)` y añadir su entrada a `REGLAS`.
"""

import uuid
from datetime import datetime, time, timedelta

from django.apps import apps
from django.db import transaction
from django.db.models import Count, Max, Min
from django.db.models.functions import ExtractHour
from django.utils import timezone

from app.models import AplicacionRegla, ReglaAutollenado, SubmuestraGEI


def _parsear_hora(valor):
    return datetime.strptime(valor, "%H:%M").time()


def _candidatos_hora_submuestra_gei(parametros):
    """SubmuestraGEI.hora nula: si ya existe alguna toma con hora conocida
    para la misma fecha (de cualquier muestra), esa hora se usa como
    referencia para todas las tomas sin hora de ese día, en vez del valor
    por defecto. Si no hay ninguna hora de referencia para la fecha, se
    infiere de `condicion_luz` de la propia toma (día → `hora_dia`,
    noche/noche simulada → `hora_noche`). En ambos casos, las tomas que
    comparten la misma base (misma fecha con referencia, o misma
    MuestraGEI sin ella) se separan `incremento_minutos` entre sí (en
    orden de `n_toma`) para no repetir la hora."""
    hora_dia = _parsear_hora(parametros["hora_dia"])
    hora_noche = _parsear_hora(parametros["hora_noche"])
    incremento = int(parametros["incremento_minutos"])

    todas = (
        SubmuestraGEI.objects
        .exclude(condicion_luz="")
        .select_related("muestra")
        .order_by("fecha", "muestra_id", "n_toma")
    )

    referencia_por_fecha = {}
    for sub in todas:
        fecha = sub.fecha
        if fecha is not None and sub.hora is not None and fecha not in referencia_por_fecha:
            referencia_por_fecha[fecha] = sub.hora

    contador = {}
    candidatos = []
    for sub in todas:
        if sub.hora is not None:
            continue
        fecha = sub.fecha
        referencia = referencia_por_fecha.get(fecha) if fecha is not None else None
        if referencia is not None:
            base = referencia
            clave = ("fecha", fecha)
            caso = "referencia_fecha"
        else:
            base = hora_dia if sub.condicion_luz == "dia" else hora_noche
            clave = ("muestra", sub.muestra_id, base)
            caso = "hora_base"
        indice = contador.get(clave, 0)
        contador[clave] = indice + 1
        valor_nuevo = (datetime.combine(datetime.min, base) + timedelta(minutes=incremento * indice)).time()
        candidatos.append({
            "objeto": sub,
            "valor_nuevo": valor_nuevo,
            "contexto": {
                "caso": caso,
                "muestra_id": sub.muestra_id,
                "n_toma": sub.n_toma,
                "fecha": fecha.isoformat() if fecha else None,
                "condicion_luz": sub.get_condicion_luz_display(),
            },
        })
    return candidatos


def _contar_pendientes_hora_submuestra_gei():
    """Cuenta cuántas SubmuestraGEI tienen `hora` nula (mismo filtro que
    `_candidatos_hora_submuestra_gei`, pero sin traer ni procesar filas: solo
    para saber cuántas hay pendientes, p. ej. para el badge de la UI)."""
    return SubmuestraGEI.objects.exclude(condicion_luz="").filter(hora__isnull=True).count()


CASOS_ETIQUETAS = {
    "referencia_fecha": "Con hora de referencia en la misma fecha",
    "hora_base": "Sin referencia — usa la hora base por condición de luz",
}


def _agrupar_por_caso(candidatos):
    """Agrupa candidatos en secciones según `contexto['caso']`, conservando
    el orden de aparición y contando cuántos hay en cada una."""
    grupos = {}
    orden = []
    for c in candidatos:
        clave = c["contexto"].get("caso", "general")
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
        grupos[clave].append(c)
    return [
        {
            "clave": clave,
            "etiqueta": CASOS_ETIQUETAS.get(clave, clave),
            "cantidad": len(grupos[clave]),
            "ejemplo": [
                {"objeto_id": c["objeto"].pk, "valor_nuevo": str(c["valor_nuevo"]), "contexto": c["contexto"]}
                for c in grupos[clave][:5]
            ],
        }
        for clave in orden
    ]


def _validar_hora_submuestra_gei():
    """Rango (mín/máx) de `hora` ya asignada en SubmuestraGEI, agrupado por
    condición de luz, más un histograma por hora del día (0-23). Sirve para
    detectar a simple vista horas fuera de lo esperado (p. ej. una toma
    'noche' con hora de mediodía)."""
    etiquetas = dict(SubmuestraGEI.CONDICION_LUZ_CHOICES)
    base = SubmuestraGEI.objects.exclude(condicion_luz="").filter(hora__isnull=False)

    resumen = (
        base
        .values("condicion_luz")
        .annotate(cantidad=Count("id"), hora_min=Min("hora"), hora_max=Max("hora"))
        .order_by("condicion_luz")
    )
    conteo_horas = (
        base
        .annotate(hora_del_dia=ExtractHour("hora"))
        .values("condicion_luz", "hora_del_dia")
        .annotate(cantidad=Count("id"))
    )
    histogramas = {}
    for fila in conteo_horas:
        histogramas.setdefault(fila["condicion_luz"], {})[fila["hora_del_dia"]] = fila["cantidad"]

    return [
        {
            "condicion_luz": fila["condicion_luz"],
            "etiqueta": etiquetas.get(fila["condicion_luz"], fila["condicion_luz"]),
            "cantidad": fila["cantidad"],
            "hora_min": fila["hora_min"].strftime("%H:%M") if fila["hora_min"] else None,
            "hora_max": fila["hora_max"].strftime("%H:%M") if fila["hora_max"] else None,
            "histograma": [histogramas.get(fila["condicion_luz"], {}).get(h, 0) for h in range(24)],
        }
        for fila in resumen
    ]


REGLAS = {
    "hora_submuestra_gei": {
        "nombre": "Hora de toma faltante",
        "descripcion": (
            "Si ya hay una toma con hora conocida en la misma fecha, esa hora se usa como referencia para "
            "todas las tomas sin hora de ese día. Si no hay ninguna referencia para la fecha, se usa la hora "
            "base de día (mediodía por defecto) o de noche/noche simulada (medianoche por defecto) según la "
            "condición de luz. Entre tomas que comparten la misma base, suma el incremento configurado por "
            "cada una para no repetir la hora."
        ),
        "modelo_destino": "SubmuestraGEI",
        "campo_destino": "hora",
        "parametros_default": {"hora_dia": "12:00", "hora_noche": "00:00", "incremento_minutos": 3},
        "parametros_schema": [
            {"clave": "hora_dia", "etiqueta": "Hora base — condición de luz 'día'", "tipo": "time"},
            {"clave": "hora_noche", "etiqueta": "Hora base — condición de luz 'noche' / 'noche simulada'", "tipo": "time"},
            {"clave": "incremento_minutos", "etiqueta": "Incremento entre tomas de la misma muestra (minutos)", "tipo": "number"},
        ],
        "calcular_candidatos": _candidatos_hora_submuestra_gei,
        "contar_pendientes": _contar_pendientes_hora_submuestra_gei,
        "validar_valores": _validar_hora_submuestra_gei,
    },
}


def obtener_parametros(codigo):
    config = REGLAS[codigo]
    parametros = dict(config.get("parametros_default", {}))
    fila = ReglaAutollenado.objects.filter(codigo=codigo).first()
    if fila and fila.parametros:
        parametros.update(fila.parametros)
    return parametros


def listar_reglas():
    resultado = []
    for codigo, config in REGLAS.items():
        contar_pendientes = config.get("contar_pendientes")
        if contar_pendientes:
            pendientes = contar_pendientes()
        else:
            pendientes = len(config["calcular_candidatos"](obtener_parametros(codigo)))
        resultado.append({
            "codigo": codigo,
            "nombre": config["nombre"],
            "descripcion": config["descripcion"],
            "modelo_destino": config["modelo_destino"],
            "campo_destino": config["campo_destino"],
            "pendientes": pendientes,
            "tiene_validacion": bool(config.get("validar_valores")),
        })
    return resultado


def detalle_regla(codigo):
    config = REGLAS[codigo]
    parametros = obtener_parametros(codigo)
    candidatos = config["calcular_candidatos"](parametros)
    return {
        "codigo": codigo,
        "nombre": config["nombre"],
        "descripcion": config["descripcion"],
        "modelo_destino": config["modelo_destino"],
        "campo_destino": config["campo_destino"],
        "parametros": parametros,
        "parametros_schema": config["parametros_schema"],
        "pendientes": len(candidatos),
        "ejemplo": [
            {"objeto_id": c["objeto"].pk, "valor_nuevo": str(c["valor_nuevo"]), "contexto": c["contexto"]}
            for c in candidatos[:5]
        ],
        "casos": _agrupar_por_caso(candidatos),
        "validacion": config["validar_valores"]() if config.get("validar_valores") else None,
        "historial": historial_regla(codigo),
    }


def actualizar_parametros(codigo, parametros_nuevos):
    config = REGLAS[codigo]
    claves_validas = {p["clave"] for p in config["parametros_schema"]}
    parametros_limpios = {k: v for k, v in parametros_nuevos.items() if k in claves_validas}

    ReglaAutollenado.objects.update_or_create(
        codigo=codigo,
        defaults={
            "nombre": config["nombre"],
            "descripcion": config["descripcion"],
            "modelo_destino": config["modelo_destino"],
            "campo_destino": config["campo_destino"],
            "parametros": {**obtener_parametros(codigo), **parametros_limpios},
        },
    )
    return obtener_parametros(codigo)


def previsualizar_regla(codigo):
    config = REGLAS[codigo]
    candidatos = config["calcular_candidatos"](obtener_parametros(codigo))
    return [
        {"objeto_id": c["objeto"].pk, "valor_nuevo": str(c["valor_nuevo"]), "contexto": c["contexto"]}
        for c in candidatos
    ]


def aplicar_regla(codigo, objeto_ids=None):
    config = REGLAS[codigo]
    parametros = obtener_parametros(codigo)
    candidatos = config["calcular_candidatos"](parametros)
    if objeto_ids is not None:
        objeto_ids = {int(i) for i in objeto_ids}
        candidatos = [c for c in candidatos if c["objeto"].pk in objeto_ids]

    regla, _ = ReglaAutollenado.objects.update_or_create(
        codigo=codigo,
        defaults={
            "nombre": config["nombre"],
            "descripcion": config["descripcion"],
            "modelo_destino": config["modelo_destino"],
            "campo_destino": config["campo_destino"],
            "parametros": parametros,
        },
    )

    campo = config["campo_destino"]
    lote = uuid.uuid4()
    aplicados = 0
    with transaction.atomic():
        for c in candidatos:
            obj = c["objeto"]
            valor_anterior = getattr(obj, campo)
            setattr(obj, campo, c["valor_nuevo"])
            obj.save(update_fields=[campo])
            AplicacionRegla.objects.create(
                regla=regla,
                lote=lote,
                objeto_id=obj.pk,
                valor_anterior=str(valor_anterior) if valor_anterior is not None else "",
                valor_nuevo=str(c["valor_nuevo"]),
            )
            aplicados += 1
    return aplicados


def historial_regla(codigo):
    """Lotes (ejecuciones de `aplicar_regla`) para esta regla, más recientes
    primero, con cuántos registros tocó cada uno y si ya fue deshecho."""
    entradas = (
        AplicacionRegla.objects
        .filter(regla__codigo=codigo)
        .order_by("-created_at")
    )
    lotes = {}
    for e in entradas:
        clave = str(e.lote)
        info = lotes.setdefault(clave, {
            "lote": clave, "fecha": e.created_at, "cantidad": 0, "deshecho": True, "deshecha_en": None,
        })
        info["cantidad"] += 1
        if e.created_at > info["fecha"]:
            info["fecha"] = e.created_at
        if e.deshecha_en is None:
            info["deshecho"] = False
        elif info["deshecha_en"] is None or e.deshecha_en > info["deshecha_en"]:
            info["deshecha_en"] = e.deshecha_en
    return sorted(lotes.values(), key=lambda x: x["fecha"], reverse=True)


def deshacer_lote(lote_id):
    """Revierte todos los cambios de un lote que aún no se hayan deshecho,
    devolviendo cada registro a su `valor_anterior` guardado en la auditoría."""
    entradas = list(
        AplicacionRegla.objects
        .filter(lote=lote_id, deshecha_en__isnull=True)
        .select_related("regla")
    )
    if not entradas:
        raise ValueError("Este lote no tiene cambios pendientes de deshacer.")

    regla = entradas[0].regla
    modelo_cls = apps.get_model("app", regla.modelo_destino)
    campo = regla.campo_destino
    field = modelo_cls._meta.get_field(campo)

    ahora = timezone.now()
    deshechas = 0
    with transaction.atomic():
        for e in entradas:
            obj = modelo_cls.objects.filter(pk=e.objeto_id).first()
            if obj is not None:
                valor = field.to_python(e.valor_anterior) if e.valor_anterior else None
                setattr(obj, campo, valor)
                obj.save(update_fields=[campo])
            e.deshecha_en = ahora
            e.save(update_fields=["deshecha_en"])
            deshechas += 1
    return deshechas
