from django.urls import path

from . import views

app_name = "ekstraksi"

urlpatterns = [
    path("", views.index, name="index"),
    path("preview/", views.preview, name="preview"),
    path("simpan/", views.simpan, name="simpan"),
]
