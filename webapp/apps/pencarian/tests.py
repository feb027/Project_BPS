from decimal import Decimal

from django.test import TestCase

from apps.data.models import Fakta
from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.pencarian.api_views import _quick_wilayah_matches
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
