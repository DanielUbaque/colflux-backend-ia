"""Embeddings y datos del proveedor de generacion.

Los embeddings se generan con Google. Es deliberado: Groq no ofrece modelos de
embeddings, solo de lenguaje, y la cuota de embeddings de Google es holgada.
La generacion de texto se delega a app/ia/proveedores.py, que permite cambiar
de proveedor con una variable de entorno.

Advertencia: si algun dia se cambia MODELO_EMBEDDING, hay que regenerar todos
los vectores guardados. Modelos distintos producen espacios numericos
incompatibles y las comparaciones darian resultados sin sentido, sin error
visible.
"""

import math
import os
from functools import lru_cache

from google import genai
from google.genai import types

MODELO_EMBEDDING = os.environ.get("IA_MODELO_EMBEDDING", "gemini-embedding-001")
DIMENSIONES = int(os.environ.get("IA_DIMENSIONES", "768"))
TAMANO_LOTE = 20


@lru_cache(maxsize=1)
def obtener_cliente():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY. Se necesita para los embeddings aunque la "
            "generacion de texto use otro proveedor."
        )
    return genai.Client(api_key=api_key)


def _normalizar(vector):
    norma = math.sqrt(sum(v * v for v in vector))
    if norma == 0:
        return list(vector)
    return [v / norma for v in vector]


def generar_embeddings(textos, task_type="SEMANTIC_SIMILARITY"):
    cliente = obtener_cliente()
    salida = []
    for inicio in range(0, len(textos), TAMANO_LOTE):
        lote = textos[inicio:inicio + TAMANO_LOTE]
        respuesta = cliente.models.embed_content(
            model=MODELO_EMBEDDING,
            contents=lote,
            config=types.EmbedContentConfig(
                output_dimensionality=DIMENSIONES,
                task_type=task_type,
            ),
        )
        for e in respuesta.embeddings:
            salida.append(_normalizar(e.values))
    return salida


def generar_embedding(texto, task_type="SEMANTIC_SIMILARITY"):
    return generar_embeddings([texto], task_type=task_type)[0]


def descripcion_proveedor():
    """Para el endpoint de salud."""
    from .proveedores import obtener_proveedor
    p = obtener_proveedor()
    return {"proveedor": p.nombre, "modelo_generacion": p.modelo,
            "modelo_embedding": MODELO_EMBEDDING, "dimensiones": DIMENSIONES}
