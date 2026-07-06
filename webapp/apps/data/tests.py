from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from apps.data.harmonization import has_conflicting_label_tokens, score_cross_table_column_match, table_title_similarity, title_pattern
from apps.data.models import CanonicalIndicator, CanonicalUnit, Fakta, IndicatorAlias, UnitAlias
from apps.data.timeseries import get_canonical_time_series
from apps.data.utils import normalize_numeric, normalize_text
from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.referensi.models import Indikator, Wilayah


class NormalizeNumericTests(SimpleTestCase):
    def test_integer_unit_treats_comma_as_thousands_separator(self):
        value, status = normalize_numeric("60,126", "jiwa")
        self.assertEqual(value, Decimal("60126"))
        self.assertEqual(status, "normalized")

    def test_integer_unit_treats_dot_as_thousands_separator(self):
        value, status = normalize_numeric("2.623", "jiwa")
        self.assertEqual(value, Decimal("2623"))
        self.assertEqual(status, "normalized")

    def test_percent_unit_treats_comma_as_decimal_separator(self):
        value, status = normalize_numeric("3,23", "persen")
        self.assertEqual(value, Decimal("3.23"))
        self.assertEqual(status, "normalized")

    def test_percent_unit_keeps_dot_decimal(self):
        value, status = normalize_numeric("3.23", "persen")
        self.assertEqual(value, Decimal("3.23"))
        self.assertEqual(status, "normalized")

    def test_decimal_unit_repairs_dot_only_centesimal_area_values(self):
        value, status = normalize_numeric("24.667", "km2")
        self.assertEqual(value, Decimal("246.67"))
        self.assertEqual(status, "normalized")

        total, _ = normalize_numeric("270.882", "km2")
        self.assertEqual(total, Decimal("2708.82"))

    def test_indonesian_mixed_locale_number(self):
        value, status = normalize_numeric("1.234,56", "rupiah")
        self.assertEqual(value, Decimal("1234.56"))
        self.assertEqual(status, "normalized")

    def test_english_mixed_locale_number(self):
        value, status = normalize_numeric("1,234.56", "rupiah")
        self.assertEqual(value, Decimal("1234.56"))
        self.assertEqual(status, "normalized")

    def test_missing_markers(self):
        value, status = normalize_numeric("...", "jiwa")
        self.assertIsNone(value)
        self.assertEqual(status, "missing")

    def test_normalize_text_keeps_context_matching_stable(self):
        self.assertEqual(normalize_text("Laki-laki / Perempuan"), "laki laki perempuan")

    def test_conflicting_label_tokens_catches_near_match_with_different_meaning(self):
        self.assertTrue(has_conflicting_label_tokens("Pasar Tradisional Bangunan Permanen", "Pasar Tradisional Bangunan Semi Permanen"))
        self.assertTrue(has_conflicting_label_tokens("Murid Negeri", "Murid Swasta"))
        self.assertFalse(has_conflicting_label_tokens("Luas Wilayah", "Luas Wilayah"))

    def test_table_title_similarity_uses_title_context(self):
        close = table_title_similarity(
            "Jumlah Penduduk Menurut Kecamatan dan Jenis Kelamin",
            "Jumlah Penduduk Laki-laki Menurut Kecamatan",
        )
        far = table_title_similarity(
            "Jumlah Penduduk Menurut Kecamatan dan Jenis Kelamin",
            "Jumlah Sarana Perdagangan Menurut Jenisnya",
        )
        self.assertGreater(close, far)
        self.assertGreater(close, 0.35)

    def test_title_pattern_keeps_distinguishing_pns_dimension_token(self):
        self.assertIn(
            "pendidikan",
            title_pattern("Jumlah Pegawai Negeri Sipil Menurut Tingkat Pendidikan dan Jenis Kelamin Tahun 2025"),
        )
        self.assertIn(
            "kepangkatan",
            title_pattern("Jumlah Pegawai Negeri Sipil Menurut Tingkat Kepangkatan dan Jenis Kelamin Tahun 2025"),
        )

    def test_title_pattern_keeps_secondary_school_level_token(self):
        self.assertIn(
            "pertama",
            title_pattern("Jumlah Sekolah, Guru, dan Murid Sekolah Menengah Pertama (SMP) di Bawah Kementerian Pendidikan"),
        )
        self.assertIn(
            "atas",
            title_pattern("Jumlah Sekolah, Guru, dan Murid Sekolah Menengah Atas (SMA) di Bawah Kementerian Pendidikan"),
        )
        self.assertIn(
            "kejuruan",
            title_pattern("Jumlah Sekolah, Guru, dan Murid Sekolah Menengah Kejuruan (SMK) di Bawah Kementerian Pendidikan"),
        )


class CanonicalTimeSeriesTests(TestCase):
    def setUp(self):
        unit, _ = CanonicalUnit.objects.get_or_create(
            code="jiwa",
            defaults={"name": "Jiwa", "symbol": "jiwa"},
        )
        unit_alias, _ = UnitAlias.objects.get_or_create(
            normalized_alias="jiwa",
            defaults={"canonical_unit": unit, "alias_text": "jiwa", "multiplier": Decimal("1")},
        )
        indicator, _ = CanonicalIndicator.objects.get_or_create(
            code="jumlah_penduduk_laki_laki",
            defaults={"name": "Jumlah Penduduk Laki-laki", "topic": "Kependudukan", "default_unit": unit},
        )
        raw_laki, _ = Indikator.objects.get_or_create(nama="Laki-Laki", defaults={"satuan": "jiwa"})
        IndicatorAlias.objects.update_or_create(
            normalized_alias=normalize_text("Laki-Laki"),
            table_title_pattern=normalize_text("penduduk"),
            topic_hint="",
            defaults={
                "canonical_indicator": indicator,
                "raw_indicator": raw_laki,
                "alias_text": "Laki-Laki",
                "unit_alias": unit_alias,
                "match_type": "contextual",
                "confidence": Decimal("0.85"),
                "is_approved": True,
            },
        )

        publikasi = Publikasi.objects.create(judul="Kabupaten Dalam Angka", tahun_terbit=2025)
        bab = Bab.objects.create(publikasi=publikasi, nomor=1, nama="Kependudukan")
        wilayah = Wilayah.objects.create(nama="Kecamatan A", jenis=Wilayah.Jenis.KECAMATAN)

        penduduk_table = Tabel.objects.create(
            bab=bab,
            nomor_tabel="1.1",
            judul="Jumlah Penduduk Menurut Kecamatan dan Jenis Kelamin",
            tahun_data=2024,
        )
        pns_table = Tabel.objects.create(
            bab=bab,
            nomor_tabel="1.2",
            judul="Jumlah Pegawai Negeri Sipil Menurut Jenis Kelamin",
            tahun_data=2024,
        )
        self.penduduk_col = KolomTabel.objects.create(tabel=penduduk_table, urutan=1, indikator=raw_laki, satuan="jiwa")
        self.pns_col = KolomTabel.objects.create(tabel=pns_table, urutan=1, indikator=raw_laki, satuan="jiwa")
        Fakta.objects.create(tabel=penduduk_table, kolom=self.penduduk_col, wilayah=wilayah, tahun=2024, nilai_num=100, nilai_teks="100")
        Fakta.objects.create(tabel=pns_table, kolom=self.pns_col, wilayah=wilayah, tahun=2024, nilai_num=20, nilai_teks="20")

    def test_contextual_alias_uses_table_title_to_disambiguate_same_column_name(self):
        payload = get_canonical_time_series(indicator_code="jumlah_penduduk_laki_laki")

        self.assertEqual(payload["meta"]["row_count"], 1)
        self.assertEqual(payload["observations"][0]["nilai"], 100.0)
        self.assertIn("Penduduk", payload["observations"][0]["source"]["judul_tabel"])

    def test_cross_table_column_score_uses_table_context_without_table_number(self):
        score, reasons = score_cross_table_column_match(self.penduduk_col, self.pns_col, table_confidence=0.20)

        self.assertLess(score, 0.70)
        self.assertIn("table_context:0.20", reasons)

    def test_alias_matches_normalized_indicator_name_variants(self):
        variant_indicator = Indikator.objects.create(nama="Laki  Laki", satuan="jiwa")
        variant_table = Tabel.objects.create(
            bab=self.penduduk_col.tabel.bab,
            nomor_tabel="1.3",
            judul="Jumlah Penduduk Menurut Kecamatan dan Jenis Kelamin",
            tahun_data=2023,
        )
        variant_col = KolomTabel.objects.create(
            tabel=variant_table,
            urutan=1,
            indikator=variant_indicator,
            satuan="jiwa",
        )
        Fakta.objects.create(
            tabel=variant_table,
            kolom=variant_col,
            wilayah=self.penduduk_col.tabel.fakta_set.first().wilayah,
            tahun=2023,
            nilai_num=90,
            nilai_teks="90",
        )

        payload = get_canonical_time_series(indicator_code="jumlah_penduduk_laki_laki")

        self.assertEqual(payload["meta"]["row_count"], 2)
        self.assertEqual([item["tahun"] for item in payload["observations"]], [2023, 2024])
        self.assertEqual([item["nilai"] for item in payload["observations"]], [90.0, 100.0])

    def test_duplicate_canonical_grain_prefers_latest_publication_source(self):
        newer_pub = Publikasi.objects.create(judul="Kabupaten Dalam Angka Revisi", tahun_terbit=2026)
        newer_bab = Bab.objects.create(publikasi=newer_pub, nomor=1, nama="Kependudukan")
        newer_table = Tabel.objects.create(
            bab=newer_bab,
            nomor_tabel="1.1",
            judul="Jumlah Penduduk Menurut Kecamatan dan Jenis Kelamin",
            tahun_data=2024,
        )
        newer_col = KolomTabel.objects.create(
            tabel=newer_table,
            urutan=1,
            indikator=self.penduduk_col.indikator,
            satuan="jiwa",
        )
        Fakta.objects.create(
            tabel=newer_table,
            kolom=newer_col,
            wilayah=self.penduduk_col.tabel.fakta_set.first().wilayah,
            tahun=2024,
            nilai_num=110,
            nilai_teks="110",
        )

        payload = get_canonical_time_series(indicator_code="jumlah_penduduk_laki_laki")

        self.assertEqual(payload["meta"]["row_count"], 1)
        self.assertEqual(payload["meta"]["duplicate_grain_count"], 1)
        self.assertEqual(payload["observations"][0]["nilai"], 110.0)
        self.assertIn("Revisi", payload["observations"][0]["source"]["publikasi"])
