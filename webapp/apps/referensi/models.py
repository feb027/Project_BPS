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

    nama = models.CharField(max_length=500, unique=True)
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

    nama = models.TextField()
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


class RincianAlias(TimeStampedModel):
    """
    Mapping nama rincian mentah (mis. 'Eselon III.a') ke rincian canonical
    ('Administrator') agar time-series lintas tahun menyambung meski BPS
    mengubah nomenklatur (penyederhanaan birokrasi: Eselon -> Jabatan).

    table_title_pattern membatasi konteks (mis. hanya tabel PNS) supaya alias
    generik tidak salah memetakan tabel lain.
    """

    canonical_rincian = models.ForeignKey(
        Rincian, on_delete=models.CASCADE, related_name="aliases_canonical"
    )
    raw_rincian = models.ForeignKey(
        Rincian, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="alias_sources",
    )
    alias_text = models.TextField(help_text="Nama rincian mentah yang akan dipetakan")
    normalized_alias = models.TextField(
        help_text="alias_text yang dinormalisasi (lower, strip) untuk lookup cepat"
    )
    table_title_pattern = models.CharField(
        max_length=500, blank=True,
        help_text="Konteks judul tabel. Kosong = berlaku semua tabel.",
    )
    is_approved = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Rincian Alias"
        verbose_name_plural = "Rincian Aliases"
        ordering = ["normalized_alias"]
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_alias", "table_title_pattern"],
                name="uq_rincian_alias_context",
            )
        ]
        indexes = [models.Index(fields=["normalized_alias"])]

    def __str__(self):
        ctx = f" @ {self.table_title_pattern}" if self.table_title_pattern else ""
        return f"{self.alias_text}{ctx} -> {self.canonical_rincian.nama}"
