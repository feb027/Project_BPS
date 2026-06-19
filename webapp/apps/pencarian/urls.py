from django.urls import path

from . import views

app_name = "pencarian"

urlpatterns = [
    path("", views.cari, name="cari"),
]
