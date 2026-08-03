import uuid

from django.db import models

from .base import TimestampedModel


class ReglaAutollenado(TimestampedModel):
    """Regla registrada en `app.reglas` que puede rellenar un campo vacío de un
    modelo aplicando una lógica propia (ver `app/reglas/autollenado.py`)."""

    codigo = models.CharField("código", max_length=80, unique=True)
    nombre = models.CharField("nombre", max_length=255)
    descripcion = models.TextField("descripción", blank=True)
    modelo_destino = models.CharField("modelo destino", max_length=100)
    campo_destino = models.CharField("campo destino", max_length=100)
    activa = models.BooleanField("activa", default=True)
    parametros = models.JSONField(
        "parámetros", default=dict, blank=True,
        help_text="Valores que ajustan el cálculo de la regla (ver parametros_default en el registro Python). "
                   "Si una clave no está aquí, se usa el valor por defecto del código.",
    )

    class Meta:
        verbose_name = "regla de autollenado"
        verbose_name_plural = "reglas de autollenado"
        ordering = ["modelo_destino", "campo_destino"]

    def __str__(self):
        return f"{self.nombre} ({self.modelo_destino}.{self.campo_destino})"


class AplicacionRegla(TimestampedModel):
    """Registro de auditoría de cada valor que una regla completó: qué
    registro, qué valor tenía antes (vacío) y cuál se le asignó. Todas las
    filas creadas por una misma ejecución de `aplicar_regla` comparten
    `lote`, lo que permite deshacer esa ejecución completa más adelante."""

    regla = models.ForeignKey(
        ReglaAutollenado, on_delete=models.CASCADE,
        related_name="aplicaciones", verbose_name="regla",
    )
    lote = models.UUIDField("lote", default=uuid.uuid4, editable=False)
    objeto_id = models.PositiveIntegerField("id del objeto")
    valor_anterior = models.CharField("valor anterior", max_length=500, blank=True, default="")
    valor_nuevo = models.CharField("valor nuevo", max_length=500)
    deshecha_en = models.DateTimeField("deshecha en", null=True, blank=True)

    class Meta:
        verbose_name = "aplicación de regla"
        verbose_name_plural = "aplicaciones de reglas"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["lote"])]

    def __str__(self):
        return f"{self.regla.codigo} → objeto #{self.objeto_id} = {self.valor_nuevo}"
