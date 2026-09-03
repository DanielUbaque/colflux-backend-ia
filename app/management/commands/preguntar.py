"""Prueba del asistente desde la linea de comandos."""

import json

from django.core.management.base import BaseCommand

from app.ia.asistente import responder


class Command(BaseCommand):
    help = "Hace una pregunta al asistente de IA."

    def add_arguments(self, parser):
        parser.add_argument("--texto", required=True)
        parser.add_argument("--usuario", default="cli")
        parser.add_argument("--json", action="store_true", help="Salida completa en JSON.")

    def handle(self, *args, **opciones):
        resultado = responder(opciones["texto"], usuario_externo_id=opciones["usuario"])
        if opciones["json"]:
            self.stdout.write(json.dumps(resultado, indent=2, ensure_ascii=False))
            return
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(f'> {opciones["texto"]}'))
        self.stdout.write("")
        self.stdout.write(resultado["respuesta"] or "(sin respuesta)")
        if resultado.get("herramientas"):
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "herramientas usadas: " + ", ".join(resultado["herramientas"])))
        if resultado.get("pendiente_de_confirmacion"):
            self.stdout.write(self.style.WARNING(
                "PENDIENTE: " + json.dumps(resultado["pendiente_de_confirmacion"], ensure_ascii=False)))
        self.stdout.write("")
