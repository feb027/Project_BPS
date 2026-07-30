from django.urls import path
from . import views

app_name = "manual_import"

urlpatterns = [
    path("generate-template/", views.generate_template, name="generate_template"),
    path("upload/", views.upload, name="upload"),
    path("preview/<uuid:pk>/", views.preview, name="preview"),
    path("commit/<uuid:pk>/", views.commit, name="commit"),
    path("", views.page, name="page"),
]
