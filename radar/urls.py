from django.contrib import admin
from django.urls import include, path

from api.views import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("", include("web.urls")),
]
