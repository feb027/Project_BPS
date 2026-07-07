from decimal import Decimal

from django.test import TestCase

from apps.data.models import Fakta
from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.pencarian.api_views import _detect_wilayahs, _quick_wilayah_matches, _quick_wilayah_matches_for_wilayahs
from apps.referensi.models import Indikator, Wilayah


class NaturalLanguageWilayahSearchTests(TestCase):
    def test_ra_query_routes_to_raudatul_athfal_school_series(self):
        wilayah = Wilayah.objects.create(nama="Singaparna", jenis="kecamatan")
        publikasi = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
        bab = Bab.objects.create(publikasi=publikasi, nomor=4, nama="Sosial")

        sekolah_jumlah = Indikator.objects.create(nama="Sekolah Jumlah")
        sekolah = Indikator.objects.create(nama="Sekolah")

        sd_table = Tabel.objects.create(
            bab=bab,
            nomor_tabel="4.1.3",
            judul="Jumlah Sekolah Dasar (SD) Menurut Kecamatan, 2025",
        )
        sd_column = KolomTabel.objects.create(tabel=sd_table, urutan=1, indikator=sekolah_jumlah, tahun=2025)
        Fakta.objects.create(
            tabel=sd_table,
            kolom=sd_column,
            wilayah=wilayah,
            nilai_num=Decimal("31"),
            nilai_teks="31",
        )

        ra_table = Tabel.objects.create(
            bab=bab,
            nomor_tabel="4.1.2",
            judul="Jumlah Sekolah, Guru, dan Murid Raudatul Athfal (RA) Menurut Kecamatan, 2025",
        )
        ra_column = KolomTabel.objects.create(tabel=ra_table, urutan=1, indikator=sekolah, tahun=2025)
        Fakta.objects.create(
            tabel=ra_table,
            kolom=ra_column,
            wilayah=wilayah,
            nilai_num=Decimal("20"),
            nilai_teks="20",
        )

        payload = _quick_wilayah_matches("Jumlah Sekolah RA di singaparna", wilayah)

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["indicator_name"], "Jumlah Sekolah Raudatul Athfal (RA)")
        self.assertEqual(payload[0]["observations"][0]["nilai_teks"], "20")
        self.assertIn("Raudatul Athfal", payload[0]["observations"][0]["tabel"]["judul"])

    def test_multi_wilayah_query_reports_all_detected_wilayahs(self):
        cisayong = Wilayah.objects.create(nama="Cisayong", jenis="kecamatan")
        ciawi = Wilayah.objects.create(nama="Ciawi", jenis="kecamatan")
        publikasi = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
        bab = Bab.objects.create(publikasi=publikasi, nomor=1, nama="Geografi")
        indikator = Indikator.objects.create(nama="Luas Wilayah")
        table = Tabel.objects.create(
            bab=bab,
            nomor_tabel="1.1.1",
            judul="Luas Wilayah Menurut Kecamatan, 2025",
        )
        column = KolomTabel.objects.create(tabel=table, urutan=1, indikator=indikator, tahun=2025)
        Fakta.objects.create(tabel=table, kolom=column, wilayah=cisayong, tahun=2024, nilai_num=Decimal("50.1"), nilai_teks="50,1")
        Fakta.objects.create(tabel=table, kolom=column, wilayah=cisayong, tahun=2025, nilai_num=Decimal("59.4"), nilai_teks="59,4")
        Fakta.objects.create(tabel=table, kolom=column, wilayah=ciawi, tahun=2024, nilai_num=Decimal("44.9"), nilai_teks="44,9")
        Fakta.objects.create(tabel=table, kolom=column, wilayah=ciawi, tahun=2025, nilai_num=Decimal("45.2"), nilai_teks="45,2")

        detected = _detect_wilayahs("luas wilayah cisayong + ciaw")
        self.assertEqual([wilayah.nama for wilayah in detected], ["Cisayong", "Ciawi"])

        merged = _quick_wilayah_matches_for_wilayahs("luas wilayah", detected)
        self.assertEqual(merged[0]["subject_name"], "Cisayong + Ciawi")
        self.assertEqual(
            sorted({observation["wilayah_nama"] for observation in merged[0]["observations"]}),
            ["Ciawi", "Cisayong"],
        )
        self.assertEqual(len(merged[0]["observations"]), 4)

        response = self.client.get("/pencarian/api/search/", {"q": "luas wilayah cisayong + ciaw"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([wilayah["nama"] for wilayah in payload["detected_wilayahs"]], ["Cisayong", "Ciawi"])
        self.assertEqual(payload["interpreted_query"], "luas wilayah")
        self.assertEqual(payload["quick_matches"][0]["indicator_name"], "Luas Wilayah")
        self.assertEqual(payload["quick_matches"][0]["subject_name"], "Cisayong + Ciawi")
        self.assertEqual(
            sorted({observation["wilayah_nama"] for observation in payload["quick_matches"][0]["observations"]}),
            ["Ciawi", "Cisayong"],
        )
