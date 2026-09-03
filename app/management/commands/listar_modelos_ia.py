"""Lista los modelos disponibles en la cuenta del proveedor configurado.

Se consulta la cuenta en vez de confiar en la documentacion: los nombres
cambian entre versiones y no todos los modelos estan habilitados para todas
las cuentas. Este comando ya evito un error una vez.
"""

from django.core.management.base import BaseCommand

from app.ia.proveedores import ErrorProveedor, obtener_proveedor


class Command(BaseCommand):
    help = "Lista los modelos disponibles en el proveedor de IA configurado."

    def add_arguments(self, parser):
        parser.add_argument("--proveedor", help="gemini o groq. Por defecto, el configurado.")
        parser.add_argument("--filtro", default="", help="Muestra solo los que contengan este texto.")

    def handle(self, *args, **opciones):
        try:
            proveedor = obtener_proveedor(opciones["proveedor"])
        except ErrorProveedor as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        self.stdout.write(self.style.HTTP_INFO(
            f"Proveedor: {proveedor.nombre} | modelo configurado: {proveedor.modelo}"))
        self.stdout.write("")

        filtro = opciones["filtro"].lower()

        if proveedor.nombre == "groq":
            try:
                modelos = proveedor.listar_modelos()
            except ErrorProveedor as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                return
            for m in modelos:
                if filtro and filtro not in m.lower():
                    continue
                self.stdout.write(f"  {m}")
            return

        from app.ia.cliente import obtener_cliente
        for m in obtener_cliente().models.list():
            acciones = getattr(m, "supported_actions", None) or []
            if "generateContent" not in acciones:
                continue
            nombre = m.name
            if filtro and filtro not in nombre.lower():
                continue
            self.stdout.write(f"  {nombre}")
