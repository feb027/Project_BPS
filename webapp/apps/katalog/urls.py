from django.urls import path

from . import views

app_name = "katalog"

urlpatterns = [
    path("publikasi/baru/", views.publikasi_create, name="publikasi_create"),
    path("pub/<int:pub_pk>/bab/baru/", views.bab_create, name="bab_create"),
    path("bab/<int:bab_pk>/tabel/baru/", views.tabel_create, name="tabel_create"),
    path("tabel/<int:pk>/edit/", views.tabel_edit, name="tabel_edit"),
    path("tabel/<int:pk>/hapus/", views.tabel_delete, name="tabel_delete"),
]
