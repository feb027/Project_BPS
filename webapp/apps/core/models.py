from django.db import models


class TimeStampedModel(models.Model):
    """Basis abstrak: catat waktu dibuat & diubah untuk semua entitas."""

    dibuat_pada = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat pada")
    diubah_pada = models.DateTimeField(auto_now=True, verbose_name="Diubah pada")

    class Meta:
        abstract = True
