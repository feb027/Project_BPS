"""Routing utama proyek."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("data/", include("apps.data.urls")),
    path("kelola/", include("apps.katalog.urls")),
    path("pencarian/", include("apps.pencarian.urls")),
    path("ekstraksi/", include("apps.ekstraksi.urls")),
]
