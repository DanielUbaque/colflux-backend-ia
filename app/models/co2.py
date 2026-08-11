from django.db import models

from .base import TimestampedModel
from .datos import FuenteDatos
from .sitio import UnidadMuestreo


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


class Equipo(TimestampedModel):
    """Equipo analizador (picarro, EGM, Licor, …) con modelo y serial."""

    modelo = models.CharField("modelo", max_length=120, blank=True)
    serial = models.CharField("serial", max_length=120, blank=True)
    descripcion = models.CharField("descripción", max_length=255, blank=True)

    class Meta:
        verbose_name = "equipo"
        verbose_name_plural = "equipos"
        ordering = ["modelo"]

    def __str__(self):
        return f"{self.modelo} ({self.serial})" if self.serial else self.modelo


class TipoMuestra(TimestampedModel):
    """Qué gas puede medir un equipo y en qué unidad (p. ej. Picarro G4301 → CO₂ en µmol m⁻² s⁻¹)."""

    GAS_CHOICES = [
        ("CO2", "CO₂"),
        ("CH4", "CH₄"),
        ("N2O", "N₂O"),
    ]

    equipo = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name="tipos_muestra",
        verbose_name="equipo",
    )
    gas = models.CharField("gas", max_length=4, choices=GAS_CHOICES)
    unidad_medida = models.ForeignKey(
        UnidadMedida, on_delete=models.PROTECT, related_name="tipos_muestra",
        verbose_name="unidad de medida",
    )

    class Meta:
        verbose_name = "tipo de muestra"
        verbose_name_plural = "tipos de muestra"
        ordering = ["equipo", "gas"]
        unique_together = [("equipo", "gas")]

    def __str__(self):
        return f"{self.equipo} — {self.get_gas_display()} ({self.unidad_medida})"


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
    """Evento de medición de flujo de CO₂: un equipo analizador conectado a un tubo."""

    tubo = models.CharField("tubo", max_length=80, blank=True)
    analizador = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, related_name="muestras_co2",
        null=True, blank=True, verbose_name="analizador",
    )
    unidad_muestreo = models.ForeignKey(
        UnidadMuestreo, on_delete=models.PROTECT, related_name="muestras_co2",
        null=True, blank=True, verbose_name="unidad de muestreo",
    )
    # Unidad reportada por la fuente para esta muestra (todas sus submuestras
    # la comparten, vienen del mismo equipo/carga). No se asume del equipo:
    # TipoMuestra solo indica la unidad *habitual* de un equipo/gas, pero la
    # fuente puede reportar en otra — por eso se guarda explícita aquí.
    unidad_medida = models.ForeignKey(
        UnidadMedida, on_delete=models.PROTECT, related_name="muestras_co2",
        null=True, blank=True, verbose_name="unidad de medida",
    )

    class Meta:
        verbose_name = "muestra CO₂"
        verbose_name_plural = "muestras CO₂"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["analizador"])]

    def __str__(self):
        return f"Muestra CO₂ {self.pk} — {self.tubo}"


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
    fecha = models.DateField("fecha de la toma", null=True, blank=True)
    hora = models.TimeField("hora de la toma", null=True, blank=True)
    momento = models.CharField("momento", max_length=10, choices=MOMENTO_CHOICES, blank=True)
    condicion_luz = models.CharField("condición de luz", max_length=15, choices=CONDICION_LUZ_CHOICES, blank=True)
    valor = models.DecimalField("valor del flujo", max_digits=14, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name = "submuestra CO₂"
        verbose_name_plural = "submuestras CO₂"
        ordering = ["muestra", "n_toma"]

    def __str__(self):
        return f"Toma {self.n_toma} — Muestra {self.muestra_id}"

    @property
    def unidad_medida(self):
        """No se guarda por toma: todas las tomas de una muestra comparten la
        misma unidad, reportada por la fuente en MuestraCO2.unidad_medida."""
        return self.muestra.unidad_medida
