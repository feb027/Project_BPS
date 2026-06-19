from django.db import models

from apps.core.models import TimeStampedModel


class Wilayah(TimeStampedModel):
    """Master wilayah, berhierarki: kecamatan -> kabupaten -> provinsi."""

    class Jenis(models.TextChoices):
        KECAMATAN = "kecamatan", "Kecamatan"
        KABUPATEN = "kabupaten", "Kabupaten/Kota"
        PROVINSI = "provinsi", "Provinsi"

    nama = models.CharField(max_length=120)
    jenis = models.CharField(max_length=20, choices=Jenis.choices, default=Jenis.KECAMATAN)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="anak", verbose_name="Induk wilayah",
    )
    kode_bps = models.CharField(max_length=20, blank=True, verbose_name="Kode BPS")

    class Meta:
        verbose_name = "Wilayah"
        verbose_name_plural = "Wilayah"
        ordering = ["jenis", "nama"]
        constraints = [
            models.UniqueConstraint(fields=["nama", "jenis", "parent"], name="uq_wilayah_nama_jenis_parent")
        ]
        indexes = [models.Index(fields=["nama"]), models.Index(fields=["jenis"])]

    def __str__(self):
        return f"{self.nama} ({self.get_jenis_display()})"


class Indikator(TimeStampedModel):
    """Konsep yang diukur (mis. 'Luas Daerah', 'Jumlah Murid'). Dipakai ulang antar tabel."""

    class TipeNilai(models.TextChoices):
        NUMERIK = "numerik", "Numerik"
        TEKS = "teks", "Teks"

    nama = models.CharField(max_length=200, unique=True)
    satuan = models.CharField(max_length=40, blank=True, help_text="mis. km2, jiwa, %, rupiah")
    tipe_nilai = models.CharField(max_length=10, choices=TipeNilai.choices, default=TipeNilai.NUMERIK)

    class Meta:
        verbose_name = "Indikator"
        verbose_name_plural = "Indikator"
        ordering = ["nama"]
        indexes = [models.Index(fields=["nama"])]

    def __str__(self):
        return f"{self.nama}{f' ({self.satuan})' if self.satuan else ''}"


class Rincian(TimeStampedModel):
    """Dimensi baris non-wilayah (partai, jabatan, lapangan usaha, komoditas, dsb)."""

    nama = models.CharField(max_length=255)
    kelompok = models.CharField(
        max_length=80, blank=True,
        help_text="mis. Partai Politik, Jabatan, Lapangan Usaha, Kelompok Komoditas",
    )

    class Meta:
        verbose_name = "Rincian"
        verbose_name_plural = "Rincian"
        ordering = ["kelompok", "nama"]
        constraints = [
            models.UniqueConstraint(fields=["nama", "kelompok"], name="uq_rincian_nama_kelompok")
        ]
        indexes = [models.Index(fields=["kelompok"]), models.Index(fields=["nama"])]

    def __str__(self):
        return f"{self.nama}{f' [{self.kelompok}]' if self.kelompok else ''}"
