"""Parte un texto largo en fragmentos aptos para buscar por significado.

El criterio: un fragmento debe ser lo bastante grande para que su embedding
capture una idea completa, y lo bastante pequeno para que al citarlo la
persona vea el pasaje exacto y no tres paginas.

Se respeta la estructura del texto. Primero se agrupan parrafos completos
hasta llegar al tamano objetivo; solo si un parrafo por si solo es enorme se
parte por frases. Ademas cada fragmento arrastra el final del anterior, para
que una idea partida en el limite siga siendo encontrable desde los dos lados.
"""

import re

TAMANO_OBJETIVO = 900
TAMANO_MAXIMO = 1400
SOLAPAMIENTO = 150
MINIMO_UTIL = 60

_FRASE = re.compile(r"(?<=[.!?])\s+")


def _partir_parrafo_largo(parrafo):
    frases = _FRASE.split(parrafo)
    bloques, actual = [], ""
    for frase in frases:
        if not frase.strip():
            continue
        if actual and len(actual) + len(frase) + 1 > TAMANO_MAXIMO:
            bloques.append(actual.strip())
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if actual.strip():
        bloques.append(actual.strip())
    return bloques


def _cola(texto, largo=SOLAPAMIENTO):
    """Ultimas frases completas del fragmento, para dar contexto al siguiente."""
    if len(texto) <= largo:
        return texto
    recorte = texto[-largo:]
    corte = _FRASE.search(recorte)
    if corte:
        return recorte[corte.end():].strip()
    return recorte.strip()


def fragmentar(texto):
    """Devuelve una lista de fragmentos listos para generar su embedding."""
    if not texto or not texto.strip():
        return []

    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]

    unidades = []
    for parrafo in parrafos:
        if len(parrafo) > TAMANO_MAXIMO:
            unidades.extend(_partir_parrafo_largo(parrafo))
        else:
            unidades.append(parrafo)

    fragmentos, actual = [], ""
    for unidad in unidades:
        if actual and len(actual) + len(unidad) + 2 > TAMANO_OBJETIVO:
            fragmentos.append(actual.strip())
            arrastre = _cola(actual)
            actual = f"{arrastre}\n\n{unidad}" if arrastre else unidad
        else:
            actual = f"{actual}\n\n{unidad}".strip() if actual else unidad

    if actual.strip():
        fragmentos.append(actual.strip())

    return [f for f in fragmentos if len(f) >= MINIMO_UTIL]
