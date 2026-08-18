from django.contrib.gis.db import models as gis_models
from django.db import models

from .base import TimestampedModel


class Region(TimestampedModel):
    """Región natural de Colombia (Andes, Orinoquía, Amazonas, Caribe, Pacífico, Insular)."""

    ANDES = "Andes"
    ORINOQUIA = "Orinoquia"
    AMAZONAS = "Amazonas"
    CARIBE = "Caribe"
    PACIFICO = "Pacifico"
    INSULAR = "Insular"
    REGION_NATURAL_CHOICES = [
        (ANDES, "Andes"),
        (ORINOQUIA, "Orinoquía"),
        (AMAZONAS, "Amazonas"),
        (CARIBE, "Caribe"),
        (PACIFICO, "Pacífico"),
        (INSULAR, "Insular"),
    ]

    nombre = models.CharField(max_length=24, choices=REGION_NATURAL_CHOICES, unique=True)

    class Meta:
        verbose_name = "región"
        verbose_name_plural = "regiones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Departamento(TimestampedModel):
    """Departamento de Colombia, asociado a su región natural."""

    DEPARTAMENTO_CHOICES = [
        ("Amazonas", "Amazonas"), ("Antioquia", "Antioquia"), ("Arauca", "Arauca"),
        ("Atlantico", "Atlántico"), ("Bogota_DC", "Bogotá, D.C."), ("Bolivar", "Bolívar"),
        ("Boyaca", "Boyacá"),
        ("Caldas", "Caldas"), ("Caqueta", "Caquetá"), ("Casanare", "Casanare"),
        ("Cauca", "Cauca"), ("Cesar", "Cesar"), ("Choco", "Chocó"),
        ("Cordoba", "Córdoba"), ("Cundinamarca", "Cundinamarca"), ("Guainia", "Guainía"),
        ("Guaviare", "Guaviare"), ("Huila", "Huila"), ("La_Guajira", "La Guajira"),
        ("Magdalena", "Magdalena"), ("Meta", "Meta"), ("Narinio", "Nariño"),
        ("Norte_de_Santander", "Norte de Santander"), ("Putumayo", "Putumayo"),
        ("Quindio", "Quindío"), ("Risaralda", "Risaralda"),
        ("San_Andres", "San Andrés, Providencia y Santa Catalina"),
        ("Santander", "Santander"), ("Sucre", "Sucre"), ("Tolima", "Tolima"),
        ("Valle_del_Cauca", "Valle del Cauca"), ("Vaupes", "Vaupés"), ("Vichada", "Vichada"),
    ]

    nombre = models.CharField(max_length=40, choices=DEPARTAMENTO_CHOICES, unique=True)
    codigo_dane = models.CharField(
        "código DANE", max_length=2, unique=True, null=True, blank=True
    )
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="departamentos")
    geom = gis_models.MultiPolygonField("geometría", srid=4326, null=True, blank=True)

    class Meta:
        verbose_name = "departamento"
        verbose_name_plural = "departamentos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Municipio(TimestampedModel):
    """Municipio de Colombia, perteneciente a un departamento."""

    nombre = models.CharField(max_length=160)
    codigo_dane = models.CharField(
        "código DANE", max_length=5, unique=True, null=True, blank=True
    )
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, related_name="municipios")
    geom = gis_models.MultiPolygonField("geometría", srid=4326, null=True, blank=True)

    class Meta:
        verbose_name = "municipio"
        verbose_name_plural = "municipios"
        ordering = ["departamento__nombre", "nombre"]
        unique_together = [("nombre", "departamento")]

    def __str__(self):
        return f"{self.nombre}, {self.departamento}"


class Vereda(TimestampedModel):
    """Subdivisión rural (vereda) o urbana (manzana censal) de un municipio, según el MGN del DANE."""

    VEREDA = "vereda"
    MANZANA = "manzana"
    TIPO_CHOICES = [
        (VEREDA, "Vereda"),
        (MANZANA, "Manzana censal"),
    ]

    nombre = models.CharField(max_length=160, blank=True)
    codigo_dane = models.CharField("código DANE", max_length=25, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT, related_name="veredas")
    geom = gis_models.MultiPolygonField("geometría", srid=4326, null=True, blank=True)

    class Meta:
        verbose_name = "vereda"
        verbose_name_plural = "veredas"
        ordering = ["municipio__nombre", "nombre"]

    def __str__(self):
        return f"{self.nombre or self.codigo_dane} ({self.get_tipo_display()}), {self.municipio}"


class SistemaReferencia(TimestampedModel):
    """Sistema de referencia de coordenadas usado para georreferenciar sitios (WGS84, MAGNA-SIRGAS, …)."""

    EPSG_4326 = "EPSG_4326"
    EPSG_4686 = "EPSG_4686"
    EPSG_4674 = "EPSG_4674"
    OTRO = "Otro"
    SISTEMA_CHOICES = [
        (EPSG_4326, "EPSG:4326 — WGS84"),
        (EPSG_4686, "EPSG:4686 — MAGNA-SIRGAS"),
        (EPSG_4674, "EPSG:4674 — SIRGAS2000"),
        (OTRO, "Otro"),
    ]

    nombre = models.CharField(max_length=20, choices=SISTEMA_CHOICES, unique=True)

    class Meta:
        verbose_name = "sistema de referencia"
        verbose_name_plural = "sistemas de referencia"

    def __str__(self):
        return self.get_nombre_display()
