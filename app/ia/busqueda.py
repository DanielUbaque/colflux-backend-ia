"""Busqueda por significado sobre el conocimiento cualitativo.

Convierte la pregunta en un vector y busca las filas cuyo vector este mas
cerca, usando el operador de distancia coseno de pgvector. La comparacion la
hace PostgreSQL, no Python: solo viajan los resultados.
"""

from pgvector.django import CosineDistance

from app.models import FragmentoConocimiento, TerminoCampo

from .cliente import generar_embedding

TASK_TYPE = "SEMANTIC_SIMILARITY"


def buscar_terminos(texto, limite=5, solo_confirmados=True):
    """Busca en el diccionario de terminos de campo (conocimiento destilado)."""
    vector = generar_embedding(texto, task_type=TASK_TYPE)
    consulta = TerminoCampo.objects.exclude(embedding=None)
    if solo_confirmados:
        consulta = consulta.filter(confirmado=True)
    return list(
        consulta.annotate(distancia=CosineDistance("embedding", vector))
        .order_by("distancia")[:limite]
    )


def buscar_fragmentos(texto, limite=5, tipo_documento=None):
    """Busca en los fragmentos de documentos crudos (entrevistas, informes)."""
    vector = generar_embedding(texto, task_type=TASK_TYPE)
    consulta = FragmentoConocimiento.objects.exclude(embedding=None)
    if tipo_documento:
        consulta = consulta.filter(documento__tipo=tipo_documento)
    return list(
        consulta.select_related("documento")
        .annotate(distancia=CosineDistance("embedding", vector))
        .order_by("distancia")[:limite]
    )
