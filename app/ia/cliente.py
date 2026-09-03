"""Punto unico de contacto con la API de Google Gemini.

Todo el codigo del asistente pasa por aqui, para que cambiar de modelo o de
proveedor sea una edicion en un solo archivo.
"""

import math
import os
from functools import lru_cache

from google import genai
from google.genai import types

MODELO_GENERACION = "gemini-3.5-flash"
MODELO_EMBEDDING = "gemini-embedding-001"
DIMENSIONES = 768
TAMANO_LOTE = 20


@lru_cache(maxsize=1)
def obtener_cliente():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta la variable de entorno GEMINI_API_KEY. "
            "Agregala en .env.prod y recrea el contenedor."
        )
    return genai.Client(api_key=api_key)


def _normalizar(vector):
    """Google recomienda normalizar cuando se pide una dimensionalidad distinta
    a la nativa del modelo (3072). Sin esto las distancias quedan sesgadas."""
    norma = math.sqrt(sum(v * v for v in vector))
    if norma == 0:
        return list(vector)
    return [v / norma for v in vector]


def generar_embeddings(textos, task_type="SEMANTIC_SIMILARITY"):
    """Recibe una lista de textos y devuelve una lista de vectores de 768
    dimensiones, en el mismo orden. Va por lotes para no pasarse de los limites
    de la capa gratuita."""
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


def generar_texto(prompt, instruccion_sistema=None):
    """Llamada simple de generacion, sin herramientas. Util para pruebas."""
    cliente = obtener_cliente()
    config = None
    if instruccion_sistema:
        config = types.GenerateContentConfig(system_instruction=instruccion_sistema)
    respuesta = cliente.models.generate_content(
        model=MODELO_GENERACION,
        contents=prompt,
        config=config,
    )
    return (respuesta.text or "").strip()
