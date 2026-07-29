from django.apps import AppConfig


class ManualImportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.manual_import"
    verbose_name = "Import Manual"
