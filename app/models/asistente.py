from django.db import models
from pgvector.django import VectorField

from .base import TimestampedModel
from .sitio import Sitio


class DocumentoConocimiento(TimestampedModel):
    """Fuente de conocimiento cualitativo tal como llego: transcripcion de una
    entrevista, informe, notas de campo o el Excel del diccionario de paramo.
    Se guarda el texto completo sin estructurar; la estructura (si la hay) se
    deriva despues."""

    TIPO_CHOICES = [
        ("entrevista", "Entrevista transcrita"),
        ("diccionario", "Diccionario de terminos"),
        ("informe", "Informe o documento tecnico"),
        ("nota_campo", "Nota de campo"),
        ("otro", "Otro"),
    ]

    titulo = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="otro")
    texto_completo = models.TextField(
        blank=True,
        help_text="Contenido crudo. Para entrevistas, la transcripcion completa.",
    )
    fecha = models.DateField(null=True, blank=True)
    sitio = models.ForeignKey(
        Sitio, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="documentos_conocimiento",
        help_text="Sitio al que se refiere el documento, si aplica.",
    )
    autor = models.CharField(max_length=180, blank=True)
    archivo_origen = models.CharField(max_length=255, blank=True)
    metadatos = models.JSONField(null=True, blank=True)
    procesado = models.BooleanField(
        default=False,
        help_text="True cuando ya se generaron sus fragmentos y embeddings.",
    )

    class Meta:
        verbose_name = "documento de conocimiento"
        verbose_name_plural = "documentos de conocimiento"
        ordering = ["-fecha", "-created_at"]

    def __str__(self):
        return self.titulo


class FragmentoConocimiento(TimestampedModel):
    """Un pedazo del texto de un DocumentoConocimiento, con su vector de
    embedding. Es la unidad que realmente busca el asistente: permite citar un
    parrafo concreto de una entrevista sin que nadie lo haya estructurado."""

    documento = models.ForeignKey(
        DocumentoConocimiento, on_delete=models.CASCADE, related_name="fragmentos"
    )
    orden = models.PositiveIntegerField(default=0)
    texto = models.TextField()
    embedding = VectorField(dimensions=768, null=True, blank=True)
    metadatos = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "fragmento de conocimiento"
        verbose_name_plural = "fragmentos de conocimiento"
        ordering = ["documento_id", "orden"]
        unique_together = [("documento", "orden")]

    def __str__(self):
        return f"{self.documento_id}#{self.orden}"


class TerminoCampo(TimestampedModel):
    """Conocimiento ya destilado: traduce una observacion cualitativa de campo
    (olor, color, textura del suelo, sensacion ambiental) a variables
    cuantitativas y reglas de umbral. Puede venir del Excel del diccionario o
    ser propuesto por la IA a partir de una entrevista; en ese segundo caso
    queda como no confirmado hasta que una persona lo valide."""

    ORIGEN_CHOICES = [
        ("manual", "Cargado o editado a mano"),
        ("excel", "Importado del Excel del diccionario"),
        ("extraido_ia", "Propuesto por la IA desde un documento"),
    ]

    categoria = models.CharField(max_length=60, blank=True, help_text="P. ej. Olor, Color, Suelo al pisar/tocar.")
    observacion_campo = models.CharField(max_length=255)
    definicion_ecologica = models.TextField(blank=True)
    variable_asociada = models.CharField(max_length=120, blank=True)
    variable_secundaria = models.CharField(max_length=255, blank=True)
    regla_cuantitativa = models.TextField(blank=True)
    interpretacion = models.TextField(blank=True)
    embedding = VectorField(dimensions=768, null=True, blank=True)

    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default="excel")
    documento_origen = models.ForeignKey(
        DocumentoConocimiento, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="terminos_extraidos",
    )
    confirmado = models.BooleanField(
        default=True,
        help_text="False mientras sea una propuesta de la IA sin validar.",
    )

    class Meta:
        verbose_name = "termino de campo"
        verbose_name_plural = "terminos de campo"
        ordering = ["categoria", "observacion_campo"]

    def __str__(self):
        return self.observacion_campo

    def texto_para_embedding(self):
        partes = [self.categoria, self.observacion_campo, self.definicion_ecologica, self.interpretacion]
        return " - ".join(p for p in partes if p)


class RegistroChatIA(TimestampedModel):
    """Auditoria de cada interaccion con el asistente de IA: pregunta, respuesta,
    que herramienta uso para responder, y si la interaccion implicaba escribir
    algo, el detalle de lo que quedo pendiente de confirmar."""

    ORIGEN_CHOICES = [
        ("web", "Panel web"),
        ("telegram", "Telegram"),
        ("api", "API directa"),
    ]

    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, default="api")
    usuario_externo_id = models.CharField(
        max_length=120, blank=True,
        help_text="Identificador del usuario en el canal de origen (p. ej. chat_id de Telegram).",
    )
    pregunta = models.TextField()
    respuesta = models.TextField(blank=True)
    herramienta_usada = models.CharField(max_length=60, blank=True)
    datos_pendientes_confirmar = models.JSONField(null=True, blank=True)
    confirmado = models.BooleanField(default=False)

    class Meta:
        verbose_name = "registro de chat IA"
        verbose_name_plural = "registros de chat IA"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.origen} - {self.pregunta[:50]}"


class MedicionRapidaChat(TimestampedModel):
    """Observacion cuantitativa registrada rapidamente via el asistente de IA
    (chat/Telegram), ya confirmada por la persona. Separada de las tablas del
    ETL formal (MuestraGEI/SubmuestraGEI) para no forzar esa jerarquia completa
    desde un mensaje de chat; queda igualmente ligada a un Sitio y una fecha
    real, por lo que es consultable como cualquier otro dato."""

    VARIABLE_CHOICES = [
        ("CO2", "Flujo de CO2"),
        ("CH4", "Flujo de CH4"),
        ("N2O", "Flujo de N2O"),
        ("temperatura_aire", "Temperatura del aire"),
        ("temperatura_suelo", "Temperatura del suelo"),
        ("humedad_relativa", "Humedad relativa"),
        ("nivel_agua", "Nivel del agua"),
        ("otro", "Otra variable"),
    ]

    sitio = models.ForeignKey(Sitio, on_delete=models.PROTECT, related_name="mediciones_rapidas_chat")
    fecha = models.DateField()
    variable = models.CharField(max_length=30, choices=VARIABLE_CHOICES)
    variable_otro = models.CharField(max_length=120, blank=True, help_text="Si 'variable' es 'otro', el nombre real.")
    valor = models.DecimalField(max_digits=12, decimal_places=4)
    unidad = models.CharField(max_length=30, blank=True)
    observacion_texto = models.TextField(help_text="El mensaje original tal como lo escribio la persona.")
    registro_chat = models.ForeignKey(
        RegistroChatIA, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="mediciones_generadas",
    )

    class Meta:
        verbose_name = "medicion rapida (chat IA)"
        verbose_name_plural = "mediciones rapidas (chat IA)"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.sitio} - {self.get_variable_display()} - {self.fecha}"
