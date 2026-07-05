from django.conf import settings
from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

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
    nilai_teks = models.CharField(max_length=500, blank=True, help_text="Tulisan asli dari sumber (audit)")
    flag = models.CharField(max_length=15, choices=Flag.choices, default=Flag.ADA)

    dibuat_oleh = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fakta_dibuat",
    )
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        verbose_name = "Fakta"
        verbose_name_plural = "Fakta"
        ordering = ["tabel", "wilayah", "rincian", "tahun"]
        indexes = [
            models.Index(fields=["tabel", "tahun"]),
            models.Index(fields=["wilayah", "tahun"]),
            models.Index(fields=["flag"]),
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        subjek = self.wilayah or self.rincian or "-"
        return f"{self.tabel.nomor_tabel} | {subjek} | {self.tahun}: {self.nilai_num or self.nilai_teks}"

    @property
    def tahun_lengkap(self):
        if self.tahun is not None:
            return self.tahun
        if self.kolom_id and getattr(self, 'kolom', None) and self.kolom.tahun is not None:
            return self.kolom.tahun
        if self.tabel_id and self.tabel.tahun_data is not None:
            return self.tabel.tahun_data
        
        # Ekstrak dari judul tabel
        if self.tabel_id and self.tabel.judul:
            import re
            matches = re.findall(r'\b(?:19|20)\d{2}\b', self.tabel.judul)
            if matches:
                return int(matches[-1])
        
        # Fallback ke tahun_terbit
        try:
            if self.tabel_id and self.tabel.bab and self.tabel.bab.publikasi:
                return self.tabel.bab.publikasi.tahun_terbit - 1
        except Exception:
            pass
            
        return None

    @property
    def nilai_tampil(self):
        if self.nilai_num is not None:
            from django.utils.formats import number_format
            # .normalize() membuang trailing zero pada Decimal
            return number_format(self.nilai_num.normalize(), force_grouping=True, use_l10n=True)
        return self.nilai_teks
