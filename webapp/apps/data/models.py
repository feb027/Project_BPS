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
        if self.kolom_id and getattr(self, "kolom", None) and self.kolom.tahun is not None:
            return self.kolom.tahun
        if self.tabel_id and self.tabel.tahun_data is not None:
            return self.tabel.tahun_data

        # Ekstrak dari judul tabel
        if self.tabel_id and self.tabel.judul:
            import re

            matches = re.findall(r"\b(?:19|20)\d{2}\b", self.tabel.judul)
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


class CanonicalUnit(TimeStampedModel):
    """Satuan baku untuk layer harmonisasi time-series."""

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Canonical Unit"
        verbose_name_plural = "Canonical Units"
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} ({self.name})"


class UnitAlias(TimeStampedModel):
    """Alias satuan mentah dan faktor konversinya ke satuan baku."""

    canonical_unit = models.ForeignKey(CanonicalUnit, on_delete=models.CASCADE, related_name="aliases")
    alias_text = models.CharField(max_length=100)
    normalized_alias = models.CharField(max_length=100)
    multiplier = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=1,
        help_text="Kalikan nilai mentah dengan faktor ini untuk mendapat nilai canonical.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Unit Alias"
        verbose_name_plural = "Unit Aliases"
        ordering = ["canonical_unit", "alias_text"]
        constraints = [
            models.UniqueConstraint(fields=["normalized_alias"], name="uq_unit_alias_normalized")
        ]
        indexes = [models.Index(fields=["normalized_alias"])]

    def __str__(self):
        return f"{self.alias_text} → {self.canonical_unit.code} (x{self.multiplier})"


class CanonicalIndicator(TimeStampedModel):
    """Indikator baku lintas publikasi untuk query time-series."""

    class Direction(models.TextChoices):
        UP = "up", "Naik lebih baik"
        DOWN = "down", "Turun lebih baik"
        NEUTRAL = "neutral", "Netral"

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    topic = models.CharField(max_length=100, blank=True, help_text="Contoh: Kependudukan, Pendidikan, Ekonomi")
    default_unit = models.ForeignKey(
        CanonicalUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="canonical_indicators",
    )
    preferred_direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        default=Direction.NEUTRAL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Canonical Indicator"
        verbose_name_plural = "Canonical Indicators"
        ordering = ["topic", "name"]
        indexes = [models.Index(fields=["topic", "is_active"])]

    def __str__(self):
        return f"{self.code}: {self.name}"


class IndicatorAlias(TimeStampedModel):
    """
    Mapping indikator mentah ke indikator canonical.

    Context fields penting karena kolom sama seperti "Laki-laki" bisa berarti
    penduduk laki-laki, murid laki-laki, pekerja laki-laki, dll tergantung judul tabel.
    """

    class MatchType(models.TextChoices):
        EXACT = "exact", "Exact"
        CONTEXTUAL = "contextual", "Contextual"
        FUZZY = "fuzzy", "Fuzzy"
        MANUAL = "manual", "Manual"
        IMPORTED = "imported", "Imported"

    canonical_indicator = models.ForeignKey(CanonicalIndicator, on_delete=models.CASCADE, related_name="aliases")
    raw_indicator = models.ForeignKey(
        "referensi.Indikator",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="canonical_aliases",
    )
    alias_text = models.CharField(max_length=500)
    normalized_alias = models.CharField(max_length=500)
    table_title_pattern = models.CharField(
        max_length=500,
        blank=True,
        help_text="Konteks judul tabel. Wajib diisi untuk alias generik seperti Laki-laki/Perempuan/Jumlah.",
    )
    topic_hint = models.CharField(max_length=120, blank=True, help_text="Konteks bab/topik bila tersedia")
    unit_alias = models.ForeignKey(UnitAlias, on_delete=models.SET_NULL, null=True, blank=True, related_name="indicator_aliases")
    match_type = models.CharField(max_length=20, choices=MatchType.choices, default=MatchType.MANUAL)
    confidence = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    is_approved = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Indicator Alias"
        verbose_name_plural = "Indicator Aliases"
        ordering = ["canonical_indicator", "alias_text"]
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_alias", "table_title_pattern", "topic_hint"],
                name="uq_indicator_alias_context",
            )
        ]
        indexes = [
            models.Index(fields=["normalized_alias"]),
            models.Index(fields=["table_title_pattern"]),
            models.Index(fields=["is_approved", "match_type"]),
        ]

    def __str__(self):
        context = f" @ {self.table_title_pattern}" if self.table_title_pattern else ""
        return f"{self.alias_text}{context} → {self.canonical_indicator.code}"


class HarmonizationReview(TimeStampedModel):
    """Antrian review untuk mapping/normalisasi yang ambigu."""

    class ObjectType(models.TextChoices):
        INDICATOR = "indicator", "Indikator"
        UNIT = "unit", "Unit"
        VALUE = "value", "Value"
        REGION = "region", "Wilayah"
        PERIOD = "period", "Periode"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CORRECTED = "corrected", "Corrected"

    object_type = models.CharField(max_length=20, choices=ObjectType.choices)
    raw_indicator = models.ForeignKey(
        "referensi.Indikator",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="harmonization_reviews",
    )
    raw_table = models.ForeignKey(
        "katalog.Tabel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="harmonization_reviews",
    )
    raw_value = models.CharField(max_length=500)
    suggested_indicator = models.ForeignKey(
        CanonicalIndicator,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_suggestions",
    )
    suggested_unit = models.ForeignKey(
        CanonicalUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_suggestions",
    )
    suggested_value = models.CharField(max_length=500, blank=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="harmonization_reviews",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Harmonization Review"
        verbose_name_plural = "Harmonization Reviews"
        ordering = ["-diubah_pada"]
        indexes = [
            models.Index(fields=["object_type", "status"]),
            models.Index(fields=["confidence"]),
        ]

    def __str__(self):
        target = self.suggested_indicator or self.suggested_unit or self.suggested_value or "-"
        return f"{self.object_type}: {self.raw_value} → {target} ({self.status})"
