from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Fakta(TimeStampedModel):
    """Inti database: satu nilai per baris (format long/tidy)."""

    class Flag(models.TextChoices):
        ADA = "ada", "Ada"
        NIHIL = "nihil", "Nihil (-)"
        TIDAK_TERSEDIA = "tidak_tersedia", "Tidak tersedia (...)"
        PERLU_CEK = "perlu_cek", "Perlu dicek"

    tabel = models.ForeignKey("katalog.Tabel", on_delete=models.CASCADE, related_name="fakta_set")
    kolom = models.ForeignKey(
        "katalog.KolomTabel", on_delete=models.CASCADE, related_name="fakta_set",
        null=True, blank=True,
    )
    wilayah = models.ForeignKey(
        "referensi.Wilayah", on_delete=models.PROTECT, related_name="fakta_set",
        null=True, blank=True,
    )
    rincian = models.ForeignKey(
        "referensi.Rincian", on_delete=models.PROTECT, related_name="fakta_set",
        null=True, blank=True,
    )
    tahun = models.PositiveIntegerField(null=True, blank=True)
    nilai_num = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    nilai_teks = models.CharField(max_length=255, blank=True, help_text="Tulisan asli dari sumber (audit)")
    flag = models.CharField(max_length=15, choices=Flag.choices, default=Flag.ADA)

    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fakta_dibuat",
    )

    class Meta:
        verbose_name = "Fakta"
        verbose_name_plural = "Fakta"
        ordering = ["tabel", "wilayah", "rincian", "tahun"]
        indexes = [
            models.Index(fields=["tabel", "tahun"]),
            models.Index(fields=["wilayah", "tahun"]),
            models.Index(fields=["flag"]),
        ]

    def __str__(self):
        subjek = self.wilayah or self.rincian or "-"
        return f"{self.tabel.nomor_tabel} | {subjek} | {self.tahun}: {self.nilai_num or self.nilai_teks}"
