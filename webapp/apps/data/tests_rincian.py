from django.test import TestCase

from apps.data.services import normalisasi_rincian


class NormalisasiRincianTest(TestCase):
    def test_hapus_spasi_di_sekitar_tanda_hubung(self):
        self.assertEqual(normalisasi_rincian("1.000.000 - 1.499.999"),
                         "1.000.000-1.499.999")
        self.assertEqual(normalisasi_rincian("150.000 - 199.999"),
                         "150.000-199.999")

    def test_normalisasi_batas_atas(self):
        self.assertEqual(normalisasi_rincian("1.500.000+"), ">1.500.000")
        self.assertEqual(normalisasi_rincian("> 1.500.000"), ">1.500.000")

    def test_normalisasi_batas_bawah(self):
        self.assertEqual(normalisasi_rincian("< 150.000"), "<150.000")

    def test_idempoten(self):
        # sudah rapi harus tetap rapi
        self.assertEqual(normalisasi_rincian("1.000.000-1.499.999"),
                         "1.000.000-1.499.999")
        self.assertEqual(normalisasi_rincian(">1.500.000"), ">1.500.000")

    def test_tidak_mengubah_nama_bukan_range(self):
        self.assertEqual(normalisasi_rincian("Kabupaten Tasikmalaya"),
                         "Kabupaten Tasikmalaya")
        self.assertEqual(normalisasi_rincian("Kurang dari 300.000"),
                         "Kurang dari 300.000")
