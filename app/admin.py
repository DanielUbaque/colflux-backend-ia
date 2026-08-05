from django.contrib import admin

from .models import (
    Autor, CaracterizacionMuestreoSuelo, Cobertura,
    FuenteDatos, Institucion, RolUsuario, Usuario, UsuarioRol,
    ConfiguracionSensorGas, Departamento, Disturbio, Equipo,
    MonitoreoParcela, MonitoreoSuelo, Municipio,
    Parcela, Proyecto, ProyectoInstitucion, ProyectoUsuario, Publicacion, PublicacionAutor,
    PublicacionSitio, Region, ResultadoPublicacion, Sitio,
    SistemaReferencia, TorreEc, TorreFuenteEnergia, Transecto,
    UnidadExperimental, UnidadMuestreo, UnidadMuestreoTipo, Vegetacion,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("nombre",)


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "region")
    list_filter = ("region",)


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "departamento")
    list_filter = ("departamento",)
    search_fields = ("nombre",)


@admin.register(SistemaReferencia)
class SistemaReferenciaAdmin(admin.ModelAdmin):
    list_display = ("nombre",)


@admin.register(Cobertura)
class CoberturaAdmin(admin.ModelAdmin):
    list_display = ("cobertura_nombre_comun", "cobertura_clc", "clima_koeppen")
    list_filter = ("clima_koeppen",)
    search_fields = ("cobertura_nombre_comun", "cobertura_clc")


@admin.register(Vegetacion)
class VegetacionAdmin(admin.ModelAdmin):
    list_display = ("tipo_cobertura", "estado_sucesional", "altura_dosel", "porcentaje_cobertura")
    list_filter = ("tipo_cobertura",)


@admin.register(Disturbio)
class DisturbioAdmin(admin.ModelAdmin):
    list_display = ("tipo", "estado_actual", "fecha_inicio", "fecha_fin")
    list_filter = ("tipo", "estado_actual")


@admin.register(Sitio)
class SitioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "municipio", "latitud", "longitud", "uso_actual", "intervenido")
    list_filter = ("uso_actual", "propiedad_tierra", "pendiente")
    search_fields = ("nombre", "codigo_metadatos")
    raw_id_fields = ("municipio", "disturbio", "vegetacion", "cobertura", "sistema_referencia")


@admin.register(UnidadMuestreoTipo)
class UnidadMuestreoTipoAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(UnidadExperimental)
class UnidadExperimentalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "proyecto")
    list_filter = ("tipo",)
    search_fields = ("nombre",)
    raw_id_fields = ("proyecto",)


@admin.register(UnidadMuestreo)
class UnidadMuestreoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "unidad_experimental")
    list_filter = ("tipo",)
    search_fields = ("nombre",)
    raw_id_fields = ("unidad_experimental",)


@admin.register(Parcela)
class ParcelaAdmin(admin.ModelAdmin):
    list_display = ("pk", "unidad_muestreo", "forma", "medida_largo", "medida_ancho", "distancia", "diametro", "area")
    list_filter = ("forma",)
    readonly_fields = ("area",)
    raw_id_fields = ("unidad_muestreo",)


@admin.register(Transecto)
class TransectoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "unidad_muestreo", "longitud", "separacion_muestreo")
    search_fields = ("nombre",)
    raw_id_fields = ("unidad_muestreo",)


@admin.register(MonitoreoParcela)
class MonitoreoParcelaAdmin(admin.ModelAdmin):
    list_display = ("unidad_muestreo", "tipo_monitoreo", "activo", "protocolo")
    list_filter = ("tipo_monitoreo", "activo")
    raw_id_fields = ("unidad_muestreo",)


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "correo")
    search_fields = ("nombre",)


@admin.register(ProyectoInstitucion)
class ProyectoInstitucionAdmin(admin.ModelAdmin):
    list_display = ("proyecto", "institucion")
    raw_id_fields = ("proyecto", "institucion")


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "coordinador", "escala_espacial", "fecha_inicio", "fecha_fin")
    list_filter = ("escala_espacial",)
    search_fields = ("nombre", "coordinador")
    raw_id_fields = ("sitio_principal",)


@admin.register(ProyectoUsuario)
class ProyectoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("proyecto", "usuario", "rol")
    raw_id_fields = ("proyecto", "usuario", "rol")


@admin.register(TorreEc)
class TorreEcAdmin(admin.ModelAdmin):
    list_display = ("pk", "sitio", "fecha_instalacion", "altura_torre", "altura_anemometro")
    raw_id_fields = ("sitio",)


@admin.register(TorreFuenteEnergia)
class TorreFuenteEnergiaAdmin(admin.ModelAdmin):
    list_display = ("torre", "tipo_fuente", "sistema_puesta_tierra")
    list_filter = ("tipo_fuente",)


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ("tipo_equipo", "modelo", "serial", "torre")
    list_filter = ("tipo_equipo",)
    search_fields = ("modelo", "serial")


@admin.register(ConfiguracionSensorGas)
class ConfiguracionSensorGasAdmin(admin.ModelAdmin):
    list_display = ("torre", "gas", "longitud_tubo", "diametro_tubo")
    list_filter = ("gas",)


@admin.register(CaracterizacionMuestreoSuelo)
class CaracterizacionMuestreoSueloAdmin(admin.ModelAdmin):
    list_display = ("muestreo_id", "sitio", "tipo_de_suelo", "profundidad_perfil")
    list_filter = ("tipo_de_suelo",)
    raw_id_fields = ("sitio",)


@admin.register(MonitoreoSuelo)
class MonitoreoSueloAdmin(admin.ModelAdmin):
    list_display = ("caracterizacion", "tipo_monitoreo", "activo")
    list_filter = ("tipo_monitoreo", "activo")


@admin.register(Publicacion)
class PublicacionAdmin(admin.ModelAdmin):
    list_display = ("titulo", "anio", "journal", "validacion_campo", "datos_disponibles_repositorio")
    list_filter = ("anio", "validacion_campo", "datos_disponibles_repositorio")
    search_fields = ("titulo", "doi", "isbn", "keywords")


@admin.register(Autor)
class AutorAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)


@admin.register(RolUsuario)
class RolUsuarioAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")
    search_fields = ("codigo", "nombre")


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cargo", "correo_institucional", "correo", "institucion")
    search_fields = ("nombre", "correo_institucional", "institucion__nombre")
    list_filter = ("institucion", "roles")
    raw_id_fields = ("institucion",)


@admin.register(UsuarioRol)
class UsuarioRolAdmin(admin.ModelAdmin):
    list_display = ("usuario", "rol")
    raw_id_fields = ("usuario", "rol")


@admin.register(FuenteDatos)
class FuenteDatosAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "estado", "proyecto", "reportador", "fecha_recepcion")
    list_filter = ("tipo", "estado", "proyecto")
    search_fields = ("nombre", "descripcion")
    raw_id_fields = ("proyecto", "reportador")


@admin.register(ResultadoPublicacion)
class ResultadoPublicacionAdmin(admin.ModelAdmin):
    list_display = ("publicacion", "variable", "valor", "unidad")
    list_filter = ("variable",)
