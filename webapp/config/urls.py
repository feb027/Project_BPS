from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("data/", include("apps.data.urls")),
    path("kelola/", include("apps.katalog.urls")),
    path("pencarian/", include("apps.pencarian.urls")),
    path("ekstraksi/", include("apps.ekstraksi.urls")),
    path("referensi/", include("apps.referensi.urls")),
    path("importer/", include("apps.manual_import.urls")),
    path("health/", health),
]

if settings.DEBUG:
    urlpatterns += static("/media/", document_root=settings.MEDIA_ROOT)
