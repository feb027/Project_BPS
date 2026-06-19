from django.urls import path

from . import views

app_name = "data"

urlpatterns = [
    path("", views.home, name="home"),
    path("pub/<int:pk>/", views.publikasi_detail, name="publikasi"),
    path("bab/<int:pk>/", views.bab_detail, name="bab"),
    path("tabel/<int:pk>/", views.tabel_detail, name="tabel_detail"),
    path("tabel/<int:pk>/isi/", views.tabel_isi, name="tabel_isi"),
]
