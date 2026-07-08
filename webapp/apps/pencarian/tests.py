from decimal import Decimal

from django.test import TestCase

from apps.data.models import Fakta
from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.pencarian.api_views import _detect_wilayahs, _quick_rincian_matches, _quick_wilayah_matches, _quick_wilayah_matches_for_wilayahs
from apps.referensi.models import Indikator, Rincian, Wilayah


class CatalogBrowseAPITests(TestCase):
    def test_catalog_merges_bab_name_case_insensitive(self):
        # "Geografi" and "GEOGRAFI" from different publications collapse into
        # one section, but each table stays its own card (no fact merge).
        lama = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2024", tahun_terbit=2024)
        baru = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
        bab_lama = Bab.objects.create(publikasi=lama, nomor=1, nama="Geografi")
        bab_baru = Bab.objects.create(publikasi=baru, nomor=1, nama="GEOGRAFI")

        tabel_lama = Tabel.objects.create(bab=bab_lama, nomor_tabel="1.1.1", judul="Luas, 2024", tahun_data=2024)
        tabel_baru = Tabel.objects.create(bab=bab_baru, nomor_tabel="1.1.1", judul="Luas, 2026", tahun_data=2026)
        kolom = KolomTabel.objects.create(tabel=tabel_lama, urutan=1, indikator=Indikator.objects.create(nama="Luas 2024"))
        KolomTabel.objects.create(tabel=tabel_baru, urutan=1, indikator=Indikator.objects.create(nama="Luas 2026"))
        w = Wilayah.objects.create(nama="Ciawi", jenis="kecamatan")
        Fakta.objects.create(tabel=tabel_lama, kolom=kolom, wilayah=w, tahun=2024, nilai_num=Decimal("1"), nilai_teks="1")
        Fakta.objects.create(tabel=tabel_baru, kolom=kolom, wilayah=w, tahun=2026, nilai_num=Decimal("2"), nilai_teks="2")

        response = self.client.get("/pencarian/api/catalog/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # No per-publication selector surface.
        self.assertNotIn("publikasi", data)
        self.assertNotIn("publikasi_list", data)

        # One merged section, two separate year cards under it.
        self.assertEqual(len(data["babs"]), 1)
        self.assertEqual(data["babs"][0]["nama"], "Geografi")
        self.assertEqual(len(data["babs"][0]["tabel"]), 2)

        cards = {t["publikasi_tahun"]: t for t in data["babs"][0]["tabel"]}
        self.assertEqual(cards[2024]["jumlah_baris"], 1)
        self.assertEqual(cards[2026]["jumlah_baris"], 1)
        # The browse tree must NOT embed series (avoids multi-MB payload).
        for t in data["babs"][0]["tabel"]:
            self.assertNotIn("series", t)
            self.assertIn("id", t)

    def test_catalog_table_series_is_single_table(self):
        # Clicking a card fetches only that table's rows, not other years.
        lama = Publikasi.objects.create(judul="2024", tahun_terbit=2024)
        baru = Publikasi.objects.create(judul="2026", tahun_terbit=2026)
        bab_lama = Bab.objects.create(publikasi=lama, nomor=1, nama="Geografi")
        bab_baru = Bab.objects.create(publikasi=baru, nomor=1, nama="GEOGRAFI")
        tabel_lama = Tabel.objects.create(bab=bab_lama, nomor_tabel="1.1.1", judul="Luas", tahun_data=2024)
        tabel_baru = Tabel.objects.create(bab=bab_baru, nomor_tabel="1.1.1", judul="Luas", tahun_data=2026)
        kolom = KolomTabel.objects.create(tabel=tabel_lama, urutan=1, indikator=Indikator.objects.create(nama="Luas X"))
        KolomTabel.objects.create(tabel=tabel_baru, urutan=1, indikator=Indikator.objects.create(nama="Luas Y"))
        w = Wilayah.objects.create(nama="Ciawi", jenis="kecamatan")
        Fakta.objects.create(tabel=tabel_lama, kolom=kolom, wilayah=w, tahun=2024, nilai_num=Decimal("1"), nilai_teks="1")
        Fakta.objects.create(tabel=tabel_baru, kolom=kolom, wilayah=w, tahun=2026, nilai_num=Decimal("2"), nilai_teks="2")

        tree = self.client.get("/pencarian/api/catalog/").json()
        # Pick the 2024 card specifically.
        tabel_2024 = next(t for t in tree["babs"][0]["tabel"] if t["publikasi_tahun"] == 2024)

        response = self.client.get(f"/pencarian/api/catalog/?tabel_id={tabel_2024['id']}")
        self.assertEqual(response.status_code, 200)
        series = response.json()["series"]
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["tahun"], 2024)

    def test_catalog_groups_by_normalized_bab_name(self):
        p2024 = Publikasi.objects.create(judul="2024", tahun_terbit=2024)
        p2026 = Publikasi.objects.create(judul="2026", tahun_terbit=2026)
        Bab.objects.create(publikasi=p2024, nomor=2, nama="Pemerintahan")
        Bab.objects.create(publikasi=p2026, nomor=1, nama="Geografi")
        Tabel.objects.create(bab=p2026.bab_set.first(), nomor_tabel="1.1.1", judul="Luas", tahun_data=2026)

        response = self.client.get("/pencarian/api/catalog/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = [b["nama"] for b in data["babs"]]
        self.assertIn("Geografi", names)


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

    def test_rincian_query_routes_aspal_to_left_column_time_series(self):
        publikasi_2025 = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2025", tahun_terbit=2025)
        publikasi_2026 = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
        bab_2025 = Bab.objects.create(publikasi=publikasi_2025, nomor=8, nama="Transportasi")
        bab_2026 = Bab.objects.create(publikasi=publikasi_2026, nomor=8, nama="Transportasi")
        indikator = Indikator.objects.create(nama="Panjang Jalan")
        aspal_legacy = Rincian.objects.create(nama="Aspal/Paved")
        aspal = Rincian.objects.create(nama="Aspal")

        table_2025 = Tabel.objects.create(
            bab=bab_2025,
            nomor_tabel="8.1.2",
            judul="Panjang Jalan Menurut Jenis Permukaan Jalan di Kabupaten Tasikmalaya (km), 2022–2024",
        )
        column_2025 = KolomTabel.objects.create(tabel=table_2025, urutan=1, indikator=indikator, satuan="km")
        Fakta.objects.create(tabel=table_2025, kolom=column_2025, rincian=aspal_legacy, tahun=2022, nilai_num=Decimal("1231.65"), nilai_teks="1231,65")

        table_2026 = Tabel.objects.create(
            bab=bab_2026,
            nomor_tabel="8.1.2",
            judul="Panjang Jalan Menurut Jenis Permukaan Jalan di Kabupaten Tasikmalaya (km), 2023–2025",
        )
        column_2026 = KolomTabel.objects.create(tabel=table_2026, urutan=1, indikator=indikator, satuan="km")
        Fakta.objects.create(tabel=table_2026, kolom=column_2026, rincian=aspal, tahun=2023, nilai_num=Decimal("1221.84"), nilai_teks="1221,84")
        Fakta.objects.create(tabel=table_2026, kolom=column_2026, rincian=aspal, tahun=2024, nilai_num=Decimal("1062.78"), nilai_teks="1062,78")

        payload = _quick_rincian_matches("aspal")

        self.assertEqual(payload[0]["indicator_name"], "Panjang Jalan")
        self.assertEqual(payload[0]["subject_name"], "Aspal")
        self.assertEqual(payload[0]["summary_kind"], "rincian")
        self.assertEqual([row["rincian_nama"] for row in payload[0]["observations"]], ["Aspal", "Aspal", "Aspal"])
        self.assertEqual([row["tahun"] for row in payload[0]["observations"]], [2022, 2023, 2024])

        response = self.client.get("/pencarian/api/search/", {"q": "aspal"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["quick_matches"][0]["subject_name"], "Aspal")
        self.assertEqual(data["indikator"][0]["nama"], "Panjang Jalan")
        self.assertIn("Jenis Permukaan Jalan", data["tabel"][0]["judul"])

    def test_school_level_token_resolves_from_table_title(self):
        wilayah = Wilayah.objects.create(nama="Singaparna", jenis="kecamatan")
        publikasi_2025 = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2025", tahun_terbit=2025)
        publikasi_2026 = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
        bab_2025 = Bab.objects.create(publikasi=publikasi_2025, nomor=4, nama="Sosial")
        bab_2026 = Bab.objects.create(publikasi=publikasi_2026, nomor=4, nama="Sosial")
        indikator = Indikator.objects.create(nama="Sekolah Jumlah")

        sd_table = Tabel.objects.create(
            bab=bab_2025,
            nomor_tabel="4.1.3",
            judul="Jumlah Sekolah Dasar (SD) Menurut Kecamatan, 2018/2019 dan 2019/2020",
        )
        sd_column = KolomTabel.objects.create(tabel=sd_table, urutan=1, indikator=indikator, tahun=2025)
        Fakta.objects.create(tabel=sd_table, kolom=sd_column, wilayah=wilayah, tahun=2018, nilai_num=Decimal("31"), nilai_teks="31")
        Fakta.objects.create(tabel=sd_table, kolom=sd_column, wilayah=wilayah, tahun=2019, nilai_num=Decimal("31"), nilai_teks="31")

        smp_table = Tabel.objects.create(
            bab=bab_2026,
            nomor_tabel="4.1.5",
            judul="Jumlah Sekolah Menengah Pertama (SMP) Menurut Kecamatan, 2018/2019 dan 2019/2020",
        )
        smp_column = KolomTabel.objects.create(tabel=smp_table, urutan=1, indikator=indikator, tahun=2025)
        Fakta.objects.create(tabel=smp_table, kolom=smp_column, wilayah=wilayah, tahun=2018, nilai_num=Decimal("10"), nilai_teks="10")
        Fakta.objects.create(tabel=smp_table, kolom=smp_column, wilayah=wilayah, tahun=2019, nilai_num=Decimal("10"), nilai_teks="10")

        # 'SD' lives only in the table title, not the shared indicator name.
        payload = _quick_wilayah_matches("Jumlah sekolah SD di singaparna", wilayah)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["indicator_name"], "Sekolah Jumlah")
        self.assertEqual([row["tahun"] for row in payload[0]["observations"]], [2018, 2019])
        self.assertEqual(sorted({row["subject_name"] for row in payload[0]["observations"]}), ["SD"])

        # Without a school-level token, all levels appear.
        all_payload = _quick_wilayah_matches("Jumlah sekolah di singaparna", wilayah)
        self.assertIn("SMP", {row["subject_name"] for row in all_payload[0]["observations"]})

    def test_indicator_query_can_compare_rincian_subjects_from_left_column(self):
        publikasi = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
        bab = Bab.objects.create(publikasi=publikasi, nomor=8, nama="Transportasi")
        indikator = Indikator.objects.create(nama="Panjang Jalan")
        table = Tabel.objects.create(
            bab=bab,
            nomor_tabel="8.1.2",
            judul="Panjang Jalan Menurut Jenis Permukaan Jalan di Kabupaten Tasikmalaya (km), 2023–2025",
        )
        column = KolomTabel.objects.create(tabel=table, urutan=1, indikator=indikator, satuan="km")
        for name, value in [("Aspal", "1221.84"), ("Kerikil", "75.63"), ("Tanah", "0"), ("Lainnya", "5.85"), ("Jumlah", "1303.32")]:
            rincian = Rincian.objects.create(nama=name)
            Fakta.objects.create(tabel=table, kolom=column, rincian=rincian, tahun=2023, nilai_num=Decimal(value), nilai_teks=value)

        payload = _quick_rincian_matches("panjang jalan")

        self.assertEqual(payload[0]["indicator_name"], "Panjang Jalan")
        self.assertEqual(payload[0]["summary_kind"], "rincian")
        subjects = {row["rincian_nama"] for row in payload[0]["observations"]}
        self.assertEqual(subjects, {"Aspal", "Kerikil", "Tanah", "Lainnya"})
        self.assertNotIn("Jumlah", subjects)
