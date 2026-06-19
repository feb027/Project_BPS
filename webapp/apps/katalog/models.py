from django.db import models

from apps.core.models import TimeStampedModel


class Publikasi(TimeStampedModel):
    """Satu terbitan, mis. 'Kabupaten Tasikmalaya Dalam Angka 2026'."""

    class Jenis(models.TextChoices):
        DIGITAL = "digital", "PDF Digital"
        SCAN = "scan", "Hasil Scan"

    judul = models.CharField(max_length=255)
    tahun_terbit = models.PositiveIntegerField()
    wilayah_cakupan = models.CharField(max_length=120, default="Kabupaten Tasikmalaya")
    jenis = models.CharField(max_length=10, choices=Jenis.choices, default=Jenis.DIGITAL)
    file_pdf = models.FileField(upload_to="publikasi/", null=True, blank=True)
    catatan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Publikasi"
        verbose_name_plural = "Publikasi"
        ordering = ["-tahun_terbit", "judul"]
        constraints = [
            models.UniqueConstraint(fields=["judul", "tahun_terbit"], name="uq_publikasi_judul_tahun")
        ]

    def __str__(self):
        return self.judul


class Bab(TimeStampedModel):
    """Bab/kategori dalam satu publikasi (13 sheet di Excel)."""

    publikasi = models.ForeignKey(Publikasi, on_delete=models.CASCADE, related_name="bab_set")
    nomor = models.PositiveIntegerField()
    nama = models.CharField(max_length=150)

    class Meta:
        verbose_name = "Bab"
        verbose_name_plural = "Bab"
        ordering = ["publikasi", "nomor"]
        constraints = [
            models.UniqueConstraint(fields=["publikasi", "nomor"], name="uq_bab_publikasi_nomor")
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama}"


class Tabel(TimeStampedModel):
    """Satu tabel dalam publikasi. Menyimpan juga info halaman utk fitur ekstraksi."""

    class TipeBaris(models.TextChoices):
        KECAMATAN = "kecamatan", "Per Kecamatan"
        KABUPATEN = "kabupaten", "Per Kabupaten/Kota"
        KATEGORI = "kategori", "Per Kategori (rincian)"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        EKSTRAK = "ekstrak", "Hasil Ekstraksi"
        VERIFIKASI = "verifikasi", "Sudah Diverifikasi"

    bab = models.ForeignKey(Bab, on_delete=models.CASCADE, related_name="tabel_set")
    nomor_tabel = models.CharField(max_length=20, help_text="mis. 1.1.1")
    nama_ringkas = models.CharField(
        max_length=120, blank=True,
        help_text="Nama mudah dibaca, mis. 'Luas Daerah & Jumlah Pulau'",
    )
    judul = models.CharField(max_length=400)
    judul_en = models.CharField(max_length=400, blank=True)
    sumber = models.CharField(max_length=300, blank=True)
    tahun_data = models.PositiveIntegerField(null=True, blank=True)
    halaman_awal = models.PositiveIntegerField(null=True, blank=True)
    halaman_akhir = models.PositiveIntegerField(null=True, blank=True)
    tipe_baris = models.CharField(max_length=15, choices=TipeBaris.choices, default=TipeBaris.KECAMATAN)
    status_verifikasi = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        verbose_name = "Tabel"
        verbose_name_plural = "Tabel"
        ordering = ["bab", "nomor_tabel"]
        constraints = [
            models.UniqueConstraint(fields=["bab", "nomor_tabel"], name="uq_tabel_bab_nomor")
        ]
        indexes = [models.Index(fields=["nomor_tabel"])]

    def __str__(self):
        return f"{self.nomor_tabel} {self.judul[:60]}"

    @property
    def nama_tampil(self):
        return self.nama_ringkas or self.judul


class KolomTabel(TimeStampedModel):
    """Definisi kolom (= header dari Excel). Bisa diedit & menggerakkan ekstraksi."""

    tabel = models.ForeignKey(Tabel, on_delete=models.CASCADE, related_name="kolom_set")
    urutan = models.PositiveIntegerField(help_text="Posisi kolom (1 = kolom angka pertama setelah label)")
    indikator = models.ForeignKey(
        "referensi.Indikator", on_delete=models.PROTECT, related_name="kolom_set",
    )
    satuan = models.CharField(max_length=40, blank=True)
    tahun = models.PositiveIntegerField(null=True, blank=True)
    tipe_nilai = models.CharField(
        max_length=10, choices=[("numerik", "Numerik"), ("teks", "Teks")], default="numerik",
    )

    class Meta:
        verbose_name = "Kolom Tabel"
        verbose_name_plural = "Kolom Tabel"
        ordering = ["tabel", "urutan"]
        constraints = [
            models.UniqueConstraint(fields=["tabel", "urutan"], name="uq_kolom_tabel_urutan")
        ]

    def __str__(self):
        return f"{self.tabel.nomor_tabel} kol#{self.urutan}: {self.indikator.nama}"
