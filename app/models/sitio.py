from django.db import models

from .base import TimestampedModel
from .geo import Municipio, SistemaReferencia
from .cobertura import Cobertura, Disturbio, Vegetacion
from .datos import FuenteDatos


class Sitio(TimestampedModel):
    """Sitio de estudio georreferenciado: ubicación, topografía, uso del suelo, cobertura, vegetación y disturbio asociados."""

    PENDIENTE_CHOICES = [
        ("plano", "Plano"),
        ("ondulado_variable", "Ondulado / variable"),
        ("valle_fondo", "Valle / fondo"),
        ("pendiente_suave", "Pendiente suave (<2%)"),
        ("pendiente_media", "Pendiente media (2–5%)"),
        ("pendiente_significativa", "Pendiente significativa (5–10%)"),
        ("pendiente_fuerte", "Pendiente fuerte (>10%)"),
        ("cresta_cima", "Cresta / cima"),
    ]
    TOPOGRAFIA_CHOICES = [
        ("cresta_cima", "Cresta / cima"),
        ("ladera_superior", "Ladera superior"),
        ("ladera_media", "Ladera media"),
        ("ladera_inferior", "Ladera inferior"),
        ("valle_fondo", "Valle / fondo"),
        ("plano", "Plano"),
    ]
    USO_ACTUAL_CHOICES = [
        ("Bosque_primario", "Bosque primario"),
        ("Bosque_secundario", "Bosque secundario"),
        ("Plantacion_forestal", "Plantación forestal"),
        ("Agricultura_intensiva", "Agricultura intensiva"),
        ("Agricultura_tradicional", "Agricultura tradicional"),
        ("Pastura", "Pastura"),
        ("Humedal_natural", "Humedal natural"),
        ("Humedal_intervenido", "Humedal intervenido"),
        ("Area_protegida", "Área protegida"),
        ("Sistema_agroforestal", "Sistema agroforestal"),
        ("Abandonado", "Abandonado"),
        ("Restauracion_activa", "Restauración activa"),
    ]
    PROPIEDAD_CHOICES = [
        ("publica", "Pública"),
        ("privada", "Privada"),
    ]

    codigo_metadatos = models.CharField("código de metadatos", max_length=80, blank=True)
    nombre = models.CharField("nombre", max_length=255)

    latitud = models.DecimalField("latitud", max_digits=10, decimal_places=7)
    longitud = models.DecimalField("longitud", max_digits=10, decimal_places=7)
    sistema_referencia = models.ForeignKey(
        SistemaReferencia, on_delete=models.PROTECT, related_name="sitios",
        null=True, blank=True,
    )
    altitud = models.DecimalField("altitud (m.s.n.m.)", max_digits=8, decimal_places=2, null=True, blank=True)
    pendiente = models.CharField("pendiente", max_length=30, choices=PENDIENTE_CHOICES, blank=True)
    topografia = models.CharField("topografía", max_length=24, choices=TOPOGRAFIA_CHOICES, blank=True)
    uso_actual = models.CharField("uso actual del suelo", max_length=30, choices=USO_ACTUAL_CHOICES, blank=True)
    propiedad_tierra = models.CharField("propiedad de la tierra", max_length=10, choices=PROPIEDAD_CHOICES, blank=True)
    intervenido = models.BooleanField("intervenido", default=False)

    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT, related_name="sitios", null=True, blank=True)
    disturbio = models.ForeignKey(Disturbio, on_delete=models.SET_NULL, related_name="sitios", null=True, blank=True)
    vegetacion = models.ForeignKey(Vegetacion, on_delete=models.SET_NULL, related_name="sitios", null=True, blank=True)
    cobertura = models.ForeignKey(Cobertura, on_delete=models.SET_NULL, related_name="sitios", null=True, blank=True)

    class Meta:
        verbose_name = "sitio"
        verbose_name_plural = "sitios"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class UnidadMuestreoTipo(TimestampedModel):
    """Catálogo de tipos de unidad de muestreo (parcela, transecto, conglomerado, plot)."""

    nombre = models.CharField("nombre", max_length=80, unique=True)

    class Meta:
        verbose_name = "tipo de unidad de muestreo"
        verbose_name_plural = "tipos de unidad de muestreo"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class UnidadExperimental(TimestampedModel):
    """Unidad a la que se asigna/representa un tratamiento independiente.

    Agrupa una o varias unidades de muestreo (p. ej. un transecto dividido en
    puntos/plots, o varias parcelas).
    """

    proyecto = models.ForeignKey(
        "app.Proyecto", on_delete=models.PROTECT,
        related_name="unidades_experimentales", verbose_name="proyecto",
    )
    nombre = models.CharField("nombre", max_length=255)
    tipo = models.ForeignKey(
        UnidadMuestreoTipo, on_delete=models.PROTECT, related_name="unidades_experimentales",
        null=True, blank=True, verbose_name="tipo",
    )
    descripcion = models.TextField("descripción", blank=True)

    class Meta:
        verbose_name = "unidad experimental"
        verbose_name_plural = "unidades experimentales"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["proyecto", "nombre"],
                name="unidad_experimental_unica_por_proyecto",
            ),
        ]

    def __str__(self):
        return self.nombre


class UnidadMuestreo(TimestampedModel):
    """Lugar/objeto desde el cual se toma la muestra. Su tipo sale del catálogo."""

    # Indexado: es el identificador natural de la unidad (p. ej. "3"), usado
    # para encontrar/crear la unidad correspondiente en cada fila del ETL.
    nombre = models.CharField("nombre", max_length=255, db_index=True)
    tipo = models.ForeignKey(
        UnidadMuestreoTipo, on_delete=models.PROTECT, related_name="unidades_muestreo",
        verbose_name="tipo",
    )
    unidad_experimental = models.ForeignKey(
        UnidadExperimental, on_delete=models.CASCADE, related_name="unidades_muestreo",
        null=True, blank=True, verbose_name="unidad experimental",
    )
    sitio = models.ForeignKey(
        Sitio, on_delete=models.SET_NULL, related_name="unidades_muestreo",
        null=True, blank=True, verbose_name="sitio",
    )
    fuente_datos = models.ForeignKey(
        FuenteDatos, on_delete=models.SET_NULL, related_name="unidades_muestreo",
        null=True, blank=True, verbose_name="fuente de datos",
    )
    fecha_instalacion = models.DateField(
        "fecha instalación unidad de muestreo", null=True, blank=True,
    )

    class Meta:
        verbose_name = "unidad de muestreo"
        verbose_name_plural = "unidades de muestreo"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Parcela(TimestampedModel):
    """Detalle de una unidad de muestreo cuando su tipo es 'parcela' (forma y dimensiones)."""

    FORMA_CUADRADA = "Cuadrada"
    FORMA_RECTANGULAR = "Rectangular"
    FORMA_CIRCULAR = "Circular"
    FORMA_CHOICES = [
        (FORMA_CUADRADA, "Cuadrada"),
        (FORMA_RECTANGULAR, "Rectangular"),
        (FORMA_CIRCULAR, "Circular"),
    ]
    # Qué campo(s) de medida exige cada forma, para validar y calcular el área.
    CAMPOS_MEDIDA_POR_FORMA = {
        FORMA_CUADRADA: ("distancia",),
        FORMA_RECTANGULAR: ("medida_largo", "medida_ancho"),
        FORMA_CIRCULAR: ("diametro",),
    }

    unidad_muestreo = models.OneToOneField(
        UnidadMuestreo, on_delete=models.CASCADE, related_name="parcela",
        null=True, blank=True, verbose_name="unidad de muestreo",
    )
    forma = models.CharField("forma", max_length=15, choices=FORMA_CHOICES, blank=True)
    medida_largo = models.DecimalField("medida largo (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    medida_ancho = models.DecimalField("medida ancho (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    distancia = models.DecimalField("distancia / lado (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    diametro = models.DecimalField("diámetro (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    area = models.DecimalField(
        "área (m²)", max_digits=10, decimal_places=2, null=True, blank=True, editable=False,
    )
    descripcion = models.TextField("descripción", blank=True, default="")

    class Meta:
        verbose_name = "parcela"
        verbose_name_plural = "parcelas"
        ordering = ["pk"]

    def __str__(self):
        return f"Parcela {self.pk}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.forma:
            return

        campos_forma = self.CAMPOS_MEDIDA_POR_FORMA[self.forma]
        faltantes = [c for c in campos_forma if getattr(self, c) is None]
        if faltantes:
            raise ValidationError(
                f"Para una parcela {self.forma.lower()} se requiere: {', '.join(faltantes)}."
            )

        otros_campos = [
            c for c in ("medida_largo", "medida_ancho", "distancia", "diametro")
            if c not in campos_forma
        ]
        con_valor = [c for c in otros_campos if getattr(self, c) is not None]
        if con_valor:
            raise ValidationError(
                f"Una parcela {self.forma.lower()} no debe tener: {', '.join(con_valor)}."
            )

    def _calcular_area(self):
        if self.forma == self.FORMA_CUADRADA and self.distancia is not None:
            return self.distancia ** 2
        if self.forma == self.FORMA_RECTANGULAR and self.medida_largo is not None and self.medida_ancho is not None:
            return self.medida_largo * self.medida_ancho
        if self.forma == self.FORMA_CIRCULAR and self.diametro is not None:
            from decimal import Decimal

            radio = self.diametro / 2
            return (Decimal("3.14159265") * radio * radio).quantize(Decimal("0.01"))
        return None

    def save(self, *args, **kwargs):
        self.clean()
        self.area = self._calcular_area()
        super().save(*args, **kwargs)


class Transecto(TimestampedModel):
    """Detalle de una unidad de muestreo cuando su tipo es 'transecto' (línea y subdivisiones)."""

    unidad_muestreo = models.OneToOneField(
        UnidadMuestreo, on_delete=models.CASCADE, related_name="transecto",
        null=True, blank=True, verbose_name="unidad de muestreo",
    )
    nombre = models.CharField("nombre", max_length=255, blank=True, default="")
    longitud = models.DecimalField("longitud (m)", max_digits=10, decimal_places=2, null=True, blank=True)
    separacion_muestreo = models.DecimalField("separación de muestreo (m)", max_digits=8, decimal_places=2, null=True, blank=True)
    descripcion = models.CharField("descripción", max_length=255, blank=True)

    class Meta:
        verbose_name = "transecto"
        verbose_name_plural = "transectos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre or f"Transecto {self.pk}"


class MonitoreoParcela(TimestampedModel):
    """Tipo de monitoreo realizado en una parcela (biomasa, flora, rasgos funcionales) y su protocolo."""

    TIPO_CHOICES = [
        ("Biomasa_Aerea", "Biomasa aérea"),
        ("Biomasa_Subterranea", "Biomasa subterránea"),
        ("Flora", "Flora"),
        ("Rasgos_Funcionales", "Rasgos funcionales"),
    ]
    PROTOCOLO_CHOICES = [
        ("Alometria_destructiva", "Alometría destructiva"),
        ("Alometria_no_destructiva", "Alometría no destructiva"),
        ("LiDAR_terrestre", "LiDAR terrestre"),
        ("LiDAR_aerotransportado", "LiDAR aerotransportado"),
    ]

    unidad_muestreo = models.ForeignKey(
        UnidadMuestreo, on_delete=models.PROTECT, related_name="monitoreos",
        null=True, blank=True, verbose_name="unidad de muestreo",
    )
    tipo_monitoreo = models.CharField("tipo de monitoreo", max_length=30, choices=TIPO_CHOICES)
    activo = models.BooleanField("activo", default=True)
    protocolo = models.CharField("protocolo", max_length=40, choices=PROTOCOLO_CHOICES, blank=True)

    class Meta:
        verbose_name = "monitoreo de unidad de muestreo"
        verbose_name_plural = "monitoreos de unidad de muestreo"
        unique_together = [("unidad_muestreo", "tipo_monitoreo")]

    def __str__(self):
        return f"{self.get_tipo_monitoreo_display()} — {self.unidad_muestreo}"
