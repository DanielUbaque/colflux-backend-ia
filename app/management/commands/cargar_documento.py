"""Carga un documento de texto (entrevista, informe, nota de campo) y lo deja
consultable por el asistente.

Guarda el texto completo para trazabilidad, lo parte en fragmentos y genera el
embedding de cada uno. A partir de ahi la funcion buscar_documentos del
asistente puede citar el parrafo exacto que responde a una pregunta.
"""

import os
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.ia.cliente import generar_embeddings
from app.ia.fragmentacion import fragmentar
from app.models import DocumentoConocimiento, FragmentoConocimiento, Sitio

TIPOS = ["entrevista", "diccionario", "informe", "nota_campo", "otro"]


class Command(BaseCommand):
    help = "Indexa un documento de texto para que el asistente pueda consultarlo."

    def add_arguments(self, parser):
        parser.add_argument("--archivo", required=True, help="Ruta a un .txt o .md")
        parser.add_argument("--titulo", help="Titulo del documento. Por defecto, el nombre del archivo.")
        parser.add_argument("--tipo", default="entrevista", choices=TIPOS)
        parser.add_argument("--fecha", help="Fecha del documento, AAAA-MM-DD. Opcional.")
        parser.add_argument("--autor", default="", help="Quien lo produjo. Opcional.")
        parser.add_argument("--sitio", help="Nombre del sitio al que se refiere. Opcional.")
        parser.add_argument("--reemplazar", action="store_true",
                            help="Si el documento ya existe, borra sus fragmentos y los rehace.")
        parser.add_argument("--sin-embeddings", action="store_true",
                            help="Guarda los fragmentos sin llamar a la API.")

    def handle(self, *args, **opciones):
        ruta = opciones["archivo"]
        if not os.path.exists(ruta):
            raise CommandError(f"No existe el archivo: {ruta}")

        with open(ruta, "r", encoding="utf-8") as f:
            texto = f.read()
        if not texto.strip():
            raise CommandError("El archivo esta vacio.")

        titulo = opciones["titulo"] or os.path.splitext(os.path.basename(ruta))[0]

        fecha = None
        if opciones["fecha"]:
            try:
                fecha = datetime.strptime(opciones["fecha"][:10], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("La fecha debe tener el formato AAAA-MM-DD.")

        sitio = None
        if opciones["sitio"]:
            coincidencias = list(Sitio.objects.filter(nombre__icontains=opciones["sitio"])[:5])
            if not coincidencias:
                raise CommandError(f"No hay ningun sitio que contenga '{opciones['sitio']}'.")
            if len(coincidencias) > 1:
                nombres = ", ".join(s.nombre for s in coincidencias)
                raise CommandError(f"'{opciones['sitio']}' coincide con varios sitios: {nombres}")
            sitio = coincidencias[0]

        fragmentos = fragmentar(texto)
        if not fragmentos:
            raise CommandError("El texto no produjo ningun fragmento util.")

        largos = [len(f) for f in fragmentos]
        self.stdout.write(
            f"Texto de {len(texto)} caracteres -> {len(fragmentos)} fragmentos "
            f"(min {min(largos)}, promedio {sum(largos) // len(largos)}, max {max(largos)})"
        )

        with transaction.atomic():
            documento, creado = DocumentoConocimiento.objects.update_or_create(
                titulo=titulo,
                defaults={
                    "tipo": opciones["tipo"],
                    "texto_completo": texto,
                    "fecha": fecha,
                    "autor": opciones["autor"],
                    "sitio": sitio,
                    "archivo_origen": os.path.basename(ruta),
                    "procesado": False,
                },
            )
            self.stdout.write(f"Documento {'creado' if creado else 'actualizado'}: id={documento.id}")

            existentes = documento.fragmentos.count()
            if existentes and not opciones["reemplazar"]:
                raise CommandError(
                    f"El documento ya tiene {existentes} fragmentos. "
                    "Usa --reemplazar para rehacerlos."
                )
            if existentes:
                documento.fragmentos.all().delete()
                self.stdout.write(f"Fragmentos anteriores borrados: {existentes}")

            objetos = [
                FragmentoConocimiento(documento=documento, orden=i, texto=t,
                                      metadatos={"caracteres": len(t)})
                for i, t in enumerate(fragmentos)
            ]
            FragmentoConocimiento.objects.bulk_create(objetos)
            self.stdout.write(f"Fragmentos creados: {len(objetos)}")

        if opciones["sin_embeddings"]:
            self.stdout.write(self.style.WARNING("Sin embeddings (--sin-embeddings)."))
            return

        pendientes = list(documento.fragmentos.filter(embedding__isnull=True).order_by("orden"))
        self.stdout.write(f"Generando embeddings para {len(pendientes)} fragmentos...")
        vectores = generar_embeddings([f.texto for f in pendientes])
        for fragmento, vector in zip(pendientes, vectores):
            fragmento.embedding = vector
        FragmentoConocimiento.objects.bulk_update(pendientes, ["embedding"], batch_size=50)

        documento.procesado = True
        documento.save(update_fields=["procesado", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"Listo. '{titulo}' indexado con {len(pendientes)} fragmentos consultables."
        ))
