from django.urls import path

from . import views

app_name = "data"

urlpatterns = [
    path("", views.home, name="home"),
    path("pub/<int:pk>/", views.publikasi_detail, name="publikasi"),
    path("pub/<int:pk>/export/", views.export_publikasi, name="export_publikasi"),
    path("bab/<int:pk>/", views.bab_detail, name="bab"),
    path("bab/<int:pk>/export/", views.export_bab, name="export_bab"),
    path("tabel/<int:pk>/", views.tabel_detail, name="tabel_detail"),
    path("tabel/<int:pk>/export/", views.export_tabel, name="export_tabel"),
    path("tabel/<int:pk>/isi/", views.tabel_isi, name="tabel_isi"),
    path("tabel/<int:pk>/verifikasi/", views.verifikasi_tabel, name="verifikasi_tabel"),
    path("fakta/<int:pk>/aman/", views.mark_fakta_safe, name="mark_fakta_safe"),
]
