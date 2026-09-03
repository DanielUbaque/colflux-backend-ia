"""Prueba manual de la busqueda por significado."""

from django.core.management.base import BaseCommand

from app.ia.busqueda import buscar_fragmentos, buscar_terminos


class Command(BaseCommand):
    help = "Busca en el diccionario de terminos por significado."

    def add_arguments(self, parser):
        parser.add_argument("--texto", required=True, help="Frase a buscar.")
        parser.add_argument("--limite", type=int, default=4)
        parser.add_argument(
            "--fragmentos", action="store_true",
            help="Buscar tambien en documentos crudos.",
        )

    def handle(self, *args, **opciones):
        texto = opciones["texto"]
        limite = opciones["limite"]

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(f'PREGUNTA: "{texto}"'))
        self.stdout.write("")

        resultados = buscar_terminos(texto, limite=limite)
        if not resultados:
            self.stdout.write(self.style.WARNING("Sin resultados en el diccionario."))
        for i, t in enumerate(resultados, 1):
            similitud = (1 - t.distancia) * 100
            self.stdout.write(f"{i}. [{similitud:.1f}% similar] {t.categoria} - {t.observacion_campo}")
            if t.variable_asociada:
                self.stdout.write(f"   variable: {t.variable_asociada}")
            if t.regla_cuantitativa:
                self.stdout.write(f"   regla:    {t.regla_cuantitativa[:110]}")
            if t.interpretacion:
                self.stdout.write(f"   lectura:  {t.interpretacion[:110]}")
            self.stdout.write("")

        if opciones["fragmentos"]:
            self.stdout.write(self.style.HTTP_INFO("--- fragmentos de documentos ---"))
            for i, f in enumerate(buscar_fragmentos(texto, limite=limite), 1):
                similitud = (1 - f.distancia) * 100
                self.stdout.write(f"{i}. [{similitud:.1f}%] {f.documento.titulo} #{f.orden}")
                self.stdout.write(f"   {f.texto[:160]}")
                self.stdout.write("")
