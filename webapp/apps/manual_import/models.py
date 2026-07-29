import uuid
from pathlib import Path
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


def _default_master_source_year():
    return 2026


def _default_zero():
    return 0


class ImportUpload(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        VALIDATED = "validated", "Validated"
        COMMITTED = "committed", "Committed"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    publication_year = models.IntegerField()
    master_source_year = models.IntegerField(default=_default_master_source_year)
    mode = models.CharField(max_length=20, default="strict")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to="manual_import/uploads/%Y/%m/%d/")
    validation_report = models.JSONField(default=dict, blank=True)
    preview_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.publication_year} :: {self.status} :: {self.original_filename}"


class ImportLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARSED = "parsed", "Parsed"
        COMMITTED = "committed", "Committed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload = models.ForeignKey(ImportUpload, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    publication_year = models.IntegerField()
    master_source_year = models.IntegerField(default=_default_master_source_year)
    mode = models.CharField(max_length=20, default="strict")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PARSED)
    raw_filename = models.CharField(max_length=255)
    validation_report = models.JSONField(default=dict, blank=True)
    preview_summary = models.JSONField(default=dict, blank=True)
    tables_affected = models.JSONField(default=list, blank=True)
    faktas_inserted = models.IntegerField(default=_default_zero)
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.publication_year} :: {self.status} :: {self.raw_filename}"
