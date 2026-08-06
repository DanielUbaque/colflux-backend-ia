from django.db import models

from .base import TimestampedModel
from .datos import FuenteDatos
from .sitio import UnidadMuestreo
from .torre import Equipo


class UnidadMedida(TimestampedModel):
    """Catálogo de unidades de medida (configurable, p. ej. co2_flux_micromol_m2_s)."""

    codigo = models.CharField("código", max_length=80, unique=True)
    descripcion = models.CharField("descripción", max_length=255, blank=True)
    magnitud = models.CharField(
        "magnitud", max_length=60, blank=True,
        help_text="flujo, concentración, temperatura, …",
    )

    class Meta:
        verbose_name = "unidad de medida"
        verbose_name_plural = "unidades de medida"
        ordering = ["codigo"]

    def __str__(self):
        return self.codigo


class Camara(TimestampedModel):
    """Cámara/sensor móvil conectado a un equipo (picarro). No pertenece a una parcela."""

    codigo = models.CharField("código", max_length=40)
    equipo = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, related_name="camaras",
        verbose_name="equipo (picarro)",
    )

    class Meta:
        verbose_name = "cámara"
        verbose_name_plural = "cámaras"
        ordering = ["codigo"]

    def __str__(self):
        return f"Cámara {self.codigo}"


class Anillo(TimestampedModel):
    """Anillo fijo instalado en la unidad de muestreo."""

    unidad_muestreo = models.ForeignKey(
        UnidadMuestreo, on_delete=models.PROTECT, related_name="anillos",
        verbose_name="unidad de muestreo",
    )
    diametro = models.DecimalField("diámetro (cm)", max_digits=8, decimal_places=2, null=True, blank=True)
    volumen = models.DecimalField("volumen (cm³)", max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "anillo"
        verbose_name_plural = "anillos"
        ordering = ["unidad_muestreo", "pk"]

    def __str__(self):
        return f"Anillo {self.pk} — {self.unidad_muestreo}"


class MuestraAmbiental(TimestampedModel):
    """Contexto ambiental (biomet) asociado a una muestra de CO₂."""

    MICROTOPO_CHOICES = [
        ("Hummock", "Hummock (cojines)"),
        ("Hollow", "Hollow (depresiones húmedas)"),
        ("Pool", "Pool (charcos / sobre agua)"),
        ("Lawns", "Lawns (lugares planos)"),
        ("Ditch", "Ditch (zanja / canal)"),
    ]
    MOMENTO_CHOICES = [
        ("inicio", "Inicio"),
        ("final", "Final"),
    ]

    fecha = models.DateField("fecha", null=True, blank=True)
    hora = models.TimeField("hora", null=True, blank=True)
    # Cuando la fuente reporta un rango (p. ej. lectura al inicio y al final
    # de la toma) en vez de un único valor, cada lectura se guarda como su
    # propia muestra ambiental distinguida por este campo. Queda opcional:
    # si la fuente ya trae un único valor, se deja vacío. El agrupado/
    # promedio de inicio+final (cuando se necesite) es un procedimiento aparte.
    momento = models.CharField("momento", max_length=10, choices=MOMENTO_CHOICES, blank=True)
    soil_temp = models.DecimalField("temperatura del suelo (°C)", max_digits=6, decimal_places=2, null=True, blank=True)
    air_temp = models.DecimalField("temperatura del aire (°C)", max_digits=6, decimal_places=2, null=True, blank=True)
    atm_press = models.DecimalField("presión atmosférica (hPa)", max_digits=8, decimal_places=2, null=True, blank=True)
    relat_humid = models.DecimalField("humedad relativa (%)", max_digits=5, decimal_places=2, null=True, blank=True)
    dew_point = models.DecimalField("punto de rocío (°C)", max_digits=6, decimal_places=2, null=True, blank=True)
    # Positivo = agua sobre la superficie (encharcamiento); negativo = nivel
    # freático por debajo de la superficie. Mismo signo que se usa en la
    # literatura de humedales/turberas para el nivel del agua.
    water_level = models.DecimalField("nivel del agua (cm)", max_digits=6, decimal_places=2, null=True, blank=True)
    microtopo = models.CharField("microtopología (microtopography)", max_length=10, choices=MICROTOPO_CHOICES, blank=True)
    # Obligatorio: sin unidad de muestreo no se sabe a qué lugar corresponde
    # la lectura. Permite cargar clima de forma independiente de una
    # MuestraCO2 (p. ej. un archivo de estación meteorológica), pero siempre
    # ubicado en el espacio.
    unidad_muestreo = models.ForeignKey(
        UnidadMuestreo, on_delete=models.PROTECT, related_name="muestras_ambientales",
        verbose_name="unidad de muestreo",
    )
    fuente_datos = models.ForeignKey(
        FuenteDatos, on_delete=models.SET_NULL, related_name="muestras_ambientales",
        null=True, blank=True, verbose_name="fuente de datos",
    )

    class Meta:
        verbose_name = "muestra ambiental"
        verbose_name_plural = "muestras ambientales"
        ordering = ["-fecha", "-hora"]
        constraints = [
            # Nota: con `hora` nula (como es casi todo el dato actual),
            # Postgres no considera dos NULL iguales, así que esta
            # restricción no evita duplicados en filas sin hora -solo
            # protege una vez que la fuente empieza a traer hora real-.
            models.UniqueConstraint(
                fields=["fecha", "hora", "fuente_datos"],
                name="muestra_ambiental_unica_por_fecha_hora_fuente",
            ),
        ]

    def __str__(self):
        return f"Muestra ambiental {self.pk}"


class MuestraCO2(TimestampedModel):
    """Evento de medición de flujo de CO₂: una cámara conectada a un anillo."""

    # Temporalmente opcionales: el ETL todavía no tiene forma de crear/vincular
    # Anillo ni Camara (Camara depende de Equipo, cuya sección "Torre EC y
    # Flujos" está oculta del wizard). Volver a null=False cuando se resuelva.
    anillo = models.ForeignKey(
        Anillo, on_delete=models.PROTECT, related_name="muestras_co2",
        null=True, blank=True, verbose_name="anillo",
    )
    camara = models.ForeignKey(
        Camara, on_delete=models.PROTECT, related_name="muestras_co2",
        null=True, blank=True, verbose_name="cámara",
    )
    # Vínculo directo a UnidadMuestreo: el ETL todavía no crea/vincula Anillo
    # (ver comentario arriba), así que por ahora la unidad de muestreo de una
    # MuestraCO2 se mapea/hereda directo, sin pasar por el anillo. La relación
    # anillo → unidad_muestreo queda pendiente de revisar a futuro.
    unidad_muestreo = models.ForeignKey(
        UnidadMuestreo, on_delete=models.PROTECT, related_name="muestras_co2",
        null=True, blank=True, verbose_name="unidad de muestreo",
    )
    fecha = models.DateField("fecha", null=True, blank=True)
    muestra_ambiental = models.ForeignKey(
        MuestraAmbiental, on_delete=models.SET_NULL, related_name="muestras_co2",
        null=True, blank=True, verbose_name="muestra ambiental",
    )

    class Meta:
        verbose_name = "muestra CO₂"
        verbose_name_plural = "muestras CO₂"
        ordering = ["-fecha", "-created_at"]
        indexes = [models.Index(fields=["anillo"]), models.Index(fields=["camara"])]

    def __str__(self):
        return f"Muestra CO₂ {self.pk} — {self.anillo}"


class SubmuestraCO2(TimestampedModel):
    """Cada una de las tomas (~4, variable) de una muestra. Aquí vive el valor del flujo."""

    MOMENTO_CHOICES = [
        ("inicio", "Inicio"),
        ("final", "Final"),
    ]
    CONDICION_LUZ_CHOICES = [
        ("dia", "Día"),
        ("noche", "Noche"),
        ("noche_simulada", "Noche simulada (cobija)"),
    ]

    muestra = models.ForeignKey(
        MuestraCO2, on_delete=models.CASCADE, related_name="submuestras",
        verbose_name="muestra CO₂",
    )
    n_toma = models.PositiveSmallIntegerField("número de toma", null=True, blank=True)
    hora = models.TimeField("hora de la toma", null=True, blank=True)
    momento = models.CharField("momento", max_length=10, choices=MOMENTO_CHOICES, blank=True)
    condicion_luz = models.CharField("condición de luz", max_length=15, choices=CONDICION_LUZ_CHOICES, blank=True)
    valor = models.DecimalField("valor del flujo", max_digits=14, decimal_places=6, null=True, blank=True)
    unidad_medida = models.ForeignKey(
        UnidadMedida, on_delete=models.PROTECT, related_name="submuestras_co2",
        null=True, blank=True, verbose_name="unidad de medida",
    )

    class Meta:
        verbose_name = "submuestra CO₂"
        verbose_name_plural = "submuestras CO₂"
        ordering = ["muestra", "n_toma"]

    def __str__(self):
        return f"Toma {self.n_toma} — Muestra {self.muestra_id}"
