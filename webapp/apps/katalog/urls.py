from django.urls import path

from . import views
from . import sync_views

app_name = "katalog"

urlpatterns = [
    path("", views.index, name="index"),
    path("publikasi/baru/", views.publikasi_create, name="publikasi_create"),
    path("pub/<int:pk>/edit/", views.publikasi_edit, name="publikasi_edit"),
    path("pub/<int:pk>/hapus/", views.publikasi_delete, name="publikasi_delete"),
    path("pub/<int:pub_pk>/bab/baru/", views.bab_create, name="bab_create"),
    path("bab/<int:pk>/edit/", views.bab_edit, name="bab_edit"),
    path("bab/<int:pk>/hapus/", views.bab_delete, name="bab_delete"),
    path("bab/<int:bab_pk>/tabel/baru/", views.tabel_create, name="tabel_create"),
    path("tabel/<int:pk>/edit/", views.tabel_edit, name="tabel_edit"),
    path("tabel/<int:pk>/hapus/", views.tabel_delete, name="tabel_delete"),
    path("api/search-indicator/", views.api_search_indicator, name="api_search_indicator"),
    path("api/suggest-indicator/", views.api_suggest_indicator, name="api_suggest_indicator"),
    path("sync/", sync_views.SyncDashboardView.as_view(), name="sync_dashboard"),
]
