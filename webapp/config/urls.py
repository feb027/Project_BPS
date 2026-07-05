"""Routing utama proyek."""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("data/", include("apps.data.urls")),
    path("kelola/", include("apps.katalog.urls")),
    path("pencarian/", include("apps.pencarian.urls")),
    path("ekstraksi/", include("apps.ekstraksi.urls")),
    path("referensi/", include("apps.referensi.urls")),
]

# Explicitly serve media bypassing DEBUG for LAN deployments
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
