from decimal import Decimal

from django.test import TestCase

from apps.data.models import Fakta
from apps.data.services import ingest_long_rows
from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.referensi.models import Indikator


class ColumnPerYearTest(TestCase):
    def setUp(self):
        self.pub = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Dalam Angka", tahun_terbit=2021)
        self.bab = Bab.objects.create(publikasi=self.pub, nomor=8, nama="Penanganan Jalan")
        self.ind = Indikator.objects.create(nama="Panjang Jalan", satuan="km", tipe_nilai=Indikator.TipeNilai.NUMERIK)

    def _rows(self, tahun_list):
        """Satu indikator, beberapa tahun -> harus jadi kolom terpisah per tahun."""
        rows = []
        for th in tahun_list:
            for kec in ["Ciawi", "Singaparna"]:
                rows.append({
                    "bab": "Penanganan Jalan", "nomor_tabel": "8.1.1",
                    "judul_tabel": "Panjang Jalan", "indikator": "Panjang Jalan",
                    "satuan": "km", "tahun": str(th), "nilai_num": "10.5",
                    "nilai_teks": "10,5", "flag": "ada", "sumber": "BPS",
                    "wilayah": kec,
                })
        return rows

    def test_two_years_make_two_columns(self):
        ingest_long_rows(self._rows([2019, 2020]), publikasi=self.pub)
        t = Tabel.objects.get(nomor_tabel="8.1.1")
        self.assertEqual(t.kolom_set.count(), 2)
        self.assertSetEqual({k.tahun for k in t.kolom_set.all()}, {2019, 2020})
        # tiap fakta menempel ke kolom dgn tahun yg sama
        for f in Fakta.objects.filter(tabel=t):
            self.assertEqual(f.kolom.tahun, f.tahun)

    def test_same_indicator_different_year_no_column_clash(self):
        # ekstrak 2019 dulu, lalu 2020 (inkremental) -> tetap 2 kolom
        ingest_long_rows(self._rows([2019]), publikasi=self.pub)
        ingest_long_rows(self._rows([2020]), publikasi=self.pub)
        t = Tabel.objects.get(nomor_tabel="8.1.1")
        self.assertEqual(t.kolom_set.count(), 2)
        self.assertSetEqual({k.tahun for k in t.kolom_set.all()}, {2019, 2020})
