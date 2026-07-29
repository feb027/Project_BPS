from django.contrib import admin
from .models import ImportLog, ImportUpload


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "publication_year",
        "master_source_year",
        "tables_affected",
        "faktas_inserted",
        "created_at",
    )
    list_filter = ("publication_year", "master_source_year", "created_at")
    search_fields = ("user__username", "notes")


@admin.register(ImportUpload)
class ImportUploadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "publication_year",
        "status",
        "created_at",
        "processed_at",
    )
    list_filter = ("status", "publication_year", "created_at")
    search_fields = ("user__username", "original_filename")
