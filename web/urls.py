from django.urls import path

from . import views

app_name = "web"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/informe/", views.panel_informe, name="panel_informe"),
    path("panel/buscar/", views.panel_buscar, name="panel_buscar"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="sw"),
    path("offline/", views.offline, name="offline"),
    path("panel/leyenda/", views.leyenda, name="leyenda"),
]
