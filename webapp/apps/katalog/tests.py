from decimal import Decimal

from django.test import TestCase

from apps.data.models import Fakta
from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.referensi.models import Indikator, Wilayah
from apps.katalog.views import _migrate_row_dimension_to_match_tipe


class RowDimensionMigrationTests(TestCase):
    def setUp(self):
        self.pub = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Dalam Angka", tahun_terbit=2024)
        self.bab = Bab.objects.create(publikasi=self.pub, nomor=12, nama="Sistem Neraca Regional")
        self.ind = Indikator.objects.create(nama="PDRB ADHB", satuan="miliar rupiah")

    def _make_table_with_fake_wilayah_rows(self):
        tabel = Tabel.objects.create(
            bab=self.bab,
            nomor_tabel="12.1.1",
            judul="Produk Domestik Regional Bruto Atas Dasar Harga Berlaku",
            tipe_baris=Tabel.TipeBaris.KECAMATAN,
        )
        kolom = KolomTabel.objects.create(tabel=tabel, urutan=1, indikator=self.ind, satuan="miliar rupiah", tahun=2023)
        for name, value in [("PDRB", "42.5"), ("Net Ekspor", "-5.5")]:
            wilayah = Wilayah.objects.create(nama=name, jenis=Wilayah.Jenis.KECAMATAN)
            Fakta.objects.create(tabel=tabel, kolom=kolom, wilayah=wilayah, nilai_num=Decimal(value), nilai_teks=value, flag=Fakta.Flag.ADA)
        return tabel

    def test_switch_to_kategori_moves_fake_wilayah_labels_to_rincian(self):
        tabel = self._make_table_with_fake_wilayah_rows()
        tabel.tipe_baris = Tabel.TipeBaris.KATEGORI
        tabel.save(update_fields=["tipe_baris"])

        moved = _migrate_row_dimension_to_match_tipe(tabel, old_tipe_baris=Tabel.TipeBaris.KECAMATAN)

        self.assertEqual(moved, 2)
        rows = list(Fakta.objects.filter(tabel=tabel).select_related("wilayah", "rincian").order_by("rincian__nama"))
        self.assertEqual([row.rincian.nama for row in rows], ["Net Ekspor", "PDRB"])
        self.assertEqual({row.wilayah.nama for row in rows}, {"Kabupaten Tasikmalaya"})

    def test_switch_back_to_kecamatan_moves_rincian_labels_to_wilayah(self):
        tabel = self._make_table_with_fake_wilayah_rows()
        tabel.tipe_baris = Tabel.TipeBaris.KATEGORI
        tabel.save(update_fields=["tipe_baris"])
        _migrate_row_dimension_to_match_tipe(tabel, old_tipe_baris=Tabel.TipeBaris.KECAMATAN)

        tabel.tipe_baris = Tabel.TipeBaris.KECAMATAN
        tabel.save(update_fields=["tipe_baris"])
        moved = _migrate_row_dimension_to_match_tipe(tabel, old_tipe_baris=Tabel.TipeBaris.KATEGORI)

        self.assertEqual(moved, 2)
        rows = list(Fakta.objects.filter(tabel=tabel).select_related("wilayah", "rincian").order_by("wilayah__nama"))
        self.assertEqual([row.wilayah.nama for row in rows], ["Net Ekspor", "PDRB"])
        self.assertTrue(all(row.rincian_id is None for row in rows))
