from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from app.api.dashboard.views import DashboardView, DataModelView, VisualizerView, chart_data
from app.api.datos.views import FuenteDatosViewSet, fuentes_datos_api
from app.api.etl.views import (
    archivo_fuente, campos_destino, datos_carga, datos_proyecto, exportar_carga, importar_carga, mapeo_carga,
    previsualizar_carga, upload_archivo, validar_carga,
)
from app.api.geo.views import sitios_geojson
from app.api.institucion.views import InstitucionViewSet
from app.api.proyecto.views import ProyectoViewSet
from app.api.reglas.views import (
    aplicar_regla_autollenado, deshacer_lote_autollenado, detalle_regla_autollenado,
    parametros_regla_autollenado, previsualizar_regla_autollenado, reglas_autollenado,
)
from app.api.reportador.views import ReportadorViewSet
from app.api.usuario.views import RolUsuarioViewSet, UsuarioViewSet

router = DefaultRouter()
router.register("api/fuentes-datos-crud", FuenteDatosViewSet, basename="fuentes-datos-crud")
router.register("api/proyectos", ProyectoViewSet, basename="proyectos")
router.register("api/usuarios", UsuarioViewSet, basename="usuarios")
router.register("api/roles-usuario", RolUsuarioViewSet, basename="roles-usuario")
router.register("api/responsables", ReportadorViewSet, basename="responsables")
router.register("api/instituciones", InstitucionViewSet, basename="instituciones")

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("emisiones/", RedirectView.as_view(url="/docs/pages/data.html", permanent=False), name="emission-list"),
    path("emisiones/crear/", RedirectView.as_view(url="/docs/pages/etl-upload.html", permanent=False), name="emission-create"),
    path("visualizador/", VisualizerView.as_view(), name="visualizer"),
    path("modelo-datos/", DataModelView.as_view(), name="data-model"),
    path("chart-data/", chart_data, name="chart-data"),
    path("api/fuentes-datos/", fuentes_datos_api, name="fuentes-datos-api"),
    path("api/fuentes-datos/crear/", FuenteDatosViewSet.as_view({"post": "create"}), name="fuentes-datos-crear"),
    path("api/fuentes-datos/<int:fuente_id>/upload/", upload_archivo, name="fuentes-datos-upload"),
    path("api/fuentes-datos/<int:fuente_id>/archivo/", archivo_fuente, name="fuentes-datos-archivo"),
    path("api/proyectos/crear/", ProyectoViewSet.as_view({"post": "create"}), name="proyectos-crear"),
    path("api/responsables/crear/", ReportadorViewSet.as_view({"post": "create"}), name="responsables-crear"),
    path("api/etl/campos-destino/", campos_destino, name="etl-campos-destino"),
    path("api/fuentes-datos/<int:fuente_id>/carga/<int:carga_id>/mapeo/", mapeo_carga, name="mapeo-carga"),
    path("api/fuentes-datos/<int:fuente_id>/carga/<int:carga_id>/validar/", validar_carga, name="validar-carga"),
    path("api/fuentes-datos/<int:fuente_id>/carga/<int:carga_id>/previsualizar/", previsualizar_carga, name="previsualizar-carga"),
    path("api/fuentes-datos/<int:fuente_id>/carga/<int:carga_id>/importar/", importar_carga, name="importar-carga"),
    path("api/fuentes-datos/<int:fuente_id>/carga/<int:carga_id>/datos/", datos_carga, name="datos-carga"),
    path("api/fuentes-datos/<int:fuente_id>/carga/<int:carga_id>/exportar/", exportar_carga, name="exportar-carga"),
    path("api/proyectos/<int:proyecto_id>/datos/", datos_proyecto, name="datos-proyecto"),
    path("api/reglas-autollenado/", reglas_autollenado, name="reglas-autollenado"),
    path("api/reglas-autollenado/<str:codigo>/", detalle_regla_autollenado, name="reglas-autollenado-detalle"),
    path("api/reglas-autollenado/<str:codigo>/parametros/", parametros_regla_autollenado, name="reglas-autollenado-parametros"),
    path("api/reglas-autollenado/<str:codigo>/previsualizar/", previsualizar_regla_autollenado, name="reglas-autollenado-previsualizar"),
    path("api/reglas-autollenado/<str:codigo>/aplicar/", aplicar_regla_autollenado, name="reglas-autollenado-aplicar"),
    path("api/reglas-autollenado/lotes/<uuid:lote_id>/deshacer/", deshacer_lote_autollenado, name="reglas-autollenado-deshacer"),
    path("api/geo/sitios/", sitios_geojson, name="geo-sitios"),
    path("", include(router.urls)),
]
