from decimal import Decimal

from django.test import TestCase

from apps.data.models import Fakta
from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.pencarian.api_views import (_detect_wilayahs, _extract_age_signature, _quick_rincian_matches, _quick_topic_matches, _quick_wilayah_matches, _quick_wilayah_matches_for_wilayahs)
from apps.referensi.models import Indikator, Rincian, Wilayah


class CatalogBrowseAPITests(TestCase):
    def test_catalog_merges_bab_name_case_insensitive(self):
        # Create unique publications to avoid IntegrityError
        lama = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2024", tahun_terbit=2024)
        baru = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
        bab_lama = Bab.objects.create(publikasi=lama, nomor=1, nama="Geografi")
        bab_baru = Bab.objects.create(publikasi=baru, nomor=1, nama="GEOGRAFI")

        Tabel.objects.create(bab=bab_lama, nomor_tabel="1.1.1", judul="Luas Wilayah Menurut Kecamatan di Kabupaten Tasikmalaya, 2024", tahun_data=2024)
        Tabel.objects.create(bab=bab_baru, nomor_tabel="1.1.1", judul="Luas Wilayah Menurut Kecamatan di Kabupaten Tasikmalaya, 2026", tahun_data=2026)

        response = self.client.get("/pencarian/api/catalog/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertNotIn("publikasi", data)
        self.assertNotIn("publikasi_list", data)
        self.assertEqual(len(data["babs"]), 1)
        self.assertEqual(data["babs"][0]["nama"], "Geografi")
        self.assertEqual(len(data["babs"][0]["tabel"]), 1)
        node = data["babs"][0]["tabel"][0]
        self.assertEqual(node["nomor_tabel"], "1.1.1")
        self.assertEqual(node["jumlah_publikasi"], 2)
        self.assertNotIn("series", node)
        self.assertNotIn("id", node)

    def test_catalog_table_merges_series_across_publications(self):
        # Create unique publications
        lama = Publikasi.objects.create(judul="2024", tahun_terbit=2024)
        baru = Publikasi.objects.create(judul="2026", tahun_terbit=2026)
        bab_lama = Bab.objects.create(publikasi=lama, nomor=1, nama="Geografi")
        bab_baru = Bab.objects.create(publikasi=baru, nomor=1, nama="GEOGRAFI")
        tabel_lama = Tabel.objects.create(bab=bab_lama, nomor_tabel="1.1.1", judul="Luas", tahun_data=2024)
        tabel_baru = Tabel.objects.create(bab=bab_baru, nomor_tabel="1.1.1", judul="Luas", tahun_data=2026)
        kolom = KolomTabel.objects.create(tabel=tabel_lama, urutan=1, indikator=Indikator.objects.create(nama="Luas X"))
        KolomTabel.objects.create(tabel=tabel_baru, urutan=1, indikator=Indikator.objects.create(nama="Luas Y"))
        w = Wilayah.objects.create(nama="Ciawi", jenis="kecamatan")
        Fakta.objects.create(tabel=tabel_lama, kolom=kolom, wilayah=w, nilai_num=Decimal("1"), nilai_teks="1")
        Fakta.objects.create(tabel=tabel_baru, kolom=kolom, wilayah=w, nilai_num=Decimal("2"), nilai_teks="2")

        response = self.client.get("/pencarian/api/catalog/?nomor_tabel=1.1.1")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["nomor_tabel"], "1.1.1")
        series = body["series"]
        self.assertEqual(len(series), 2)
        for row in series:
            self.assertIn("tahun", row)
            self.assertIn("unit", row)
            self.assertIn("subject_name", row)

    def test_catalog_groups_by_normalized_bab_name(self):
        # Create unique publications
        p2024 = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2024", tahun_terbit=2024)
        p2026 = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2026", tahun_terbit=2026)
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


class QuickTopicAnswerTests(TestCase):
    def test_topic_answer_uses_parent_row_not_sum_of_subregions(self):
        # Table 1.1.1 "Luas Wilayah Menurut Kecamatan" carries BOTH the
        # per-kecamatan rows AND a "Kabupaten Tasikmalaya" parent total row
        # (which already sums the districts). The direct-answer card must use
        # the parent row alone (2708.82), NOT the double-counted sum of
        # parent + districts (~5417.64).
        publikasi = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2025", tahun_terbit=2025)
        bab = Bab.objects.create(publikasi=publikasi, nomor=1, nama="Geografi")
        indikator = Indikator.objects.create(nama="Luas Wilayah")
        table = Tabel.objects.create(
            bab=bab,
            nomor_tabel="1.1.1",
            judul="Luas Wilayah Menurut Kecamatan, 2025",
            tahun_data=2025,
        )
        column = KolomTabel.objects.create(tabel=table, urutan=1, indikator=indikator, tahun=2025)
        regency = Wilayah.objects.create(nama="Kabupaten Tasikmalaya", jenis="kabupaten")
        districts = [
            Wilayah.objects.create(nama=f"Kecamatan {i}", jenis="kecamatan") for i in range(3)
        ]
        # parent total row
        Fakta.objects.create(
            tabel=table, kolom=column, wilayah=regency, tahun=2025,
            nilai_num=Decimal("2708.82"), nilai_teks="2708,82",
        )
        # three districts summing to the same total
        for i, d in enumerate(districts):
            Fakta.objects.create(
                tabel=table, kolom=column, wilayah=d, tahun=2025,
                nilai_num=Decimal(str(900 + i)), nilai_teks=str(900 + i),
            )

        groups = _quick_topic_matches("luas wilayah")
        self.assertTrue(groups, "expected a direct-answer card for 'luas wilayah'")
        card = groups[0]
        self.assertEqual(card["subject_name"], "Kabupaten Tasikmalaya")
        obs = {o["tahun"]: o["nilai"] for o in card["observations"]}
        self.assertEqual(obs.get(2025), 2708.82)
        self.assertNotEqual(obs.get(2025), 2708.82 + 900 + 901 + 902)


class AgeScopedQueryTests(TestCase):
    def _make_age_table(self, nomor, judul, indicator_nama, rincian_names):
        pub, _ = Publikasi.objects.get_or_create(
            judul="Kabupaten Tasikmalaya Angka 2022", tahun_terbit=2022)
        bab, _ = Bab.objects.get_or_create(publikasi=pub, nomor=3, nama="Penduduk")
        tabel = Tabel.objects.create(bab=bab, nomor_tabel=nomor, judul=judul, tahun_data=2022)
        ind = Indikator.objects.create(nama=indicator_nama)
        kolom = KolomTabel.objects.create(tabel=tabel, urutan=1, indikator=ind, tahun=2022)
        regency = Wilayah.objects.create(nama="Kabupaten Tasikmalaya", jenis="kabupaten")
        Fakta.objects.create(tabel=tabel, kolom=kolom, wilayah=regency, rincian=None, tahun=2022, nilai_num=Decimal("1000"), nilai_teks="1000")
        for nama in rincian_names:
            r = Rincian.objects.create(nama=nama)
            Fakta.objects.create(tabel=tabel, kolom=kolom, wilayah=regency, rincian=r, tahun=2022, nilai_num=Decimal("100"), nilai_teks="100")

    def test_age_signature_parsing(self):
        self.assertEqual(_extract_age_signature("jumlah penduduk umur 15 tahun"), "berumur 15 tahun")
        self.assertEqual(_extract_age_signature("penduduk umur 7-24 tahun"), "berumur 7-24 tahun")
        self.assertEqual(_extract_age_signature("jumlah penduduk"), "")

    def test_age_query_uses_scoped_table_not_all_ages_total(self):
        # All-ages total population (3.1.1) vs age-15+ weekly-activity (3.2.1).
        self._make_age_table(
            "3.1.1",
            "Jumlah Penduduk Menurut Kecamatan di Kabupaten Tasikmalaya, 2017",
            "Penduduk - Jumlah",
            ["Laki-Laki", "Perempuan"],
        )
        self._make_age_table(
            "3.2.1",
            "Jumlah Penduduk Berumur 15 Tahun Keatas Menurut Jenis Kegiatan Selama Seminggu yang Lalu di Kabupaten Tasikmalaya, 2022",
            "Penduduk Berumur 15 Keatas - Jumlah",
            ["Bekerja", "Sekolah", "Mengurus Rumah Tangga"],
        )

        cards = _quick_rincian_matches("jumlah penduduk umur 15 tahun")
        self.assertTrue(cards, "expected a direct-answer card")
        # The card must come from the age-15+ table (3.2.1), never the
        # all-ages population total (3.1.1).
        card = cards[0]
        self.assertEqual(card["subject_name"], "Bekerja + Mengurus Rumah Tangga + Sekolah")
        for obs in card["observations"]:
            self.assertEqual(obs["tabel"]["nomor_tabel"], "3.2.1")


class MultiConceptSearchTests(TestCase):
    def test_plus_query_returns_per_concept_matches(self):
        pub = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2025", tahun_terbit=2025)
        bab = Bab.objects.create(publikasi=pub, nomor=5, nama="Pertanian")
        regency = Wilayah.objects.create(nama="Kabupaten Tasikmalaya", jenis="kabupaten")

        ind_a = Indikator.objects.create(nama="Produksi Alpukat", satuan="kuintal")
        ind_b = Indikator.objects.create(nama="Produksi Mangga", satuan="kuintal")
        t_a = Tabel.objects.create(bab=bab, nomor_tabel="5.1.1", judul="Produksi Alpukat Menurut Kecamatan")
        t_b = Tabel.objects.create(bab=bab, nomor_tabel="5.1.2", judul="Produksi Mangga Menurut Kecamatan")
        k_a = KolomTabel.objects.create(tabel=t_a, urutan=1, indikator=ind_a)
        k_b = KolomTabel.objects.create(tabel=t_b, urutan=1, indikator=ind_b)
        for tahun in (2023, 2024):
            Fakta.objects.create(tabel=t_a, kolom=k_a, wilayah=regency, tahun=tahun, nilai_num=Decimal("10"), nilai_teks="10")
            Fakta.objects.create(tabel=t_b, kolom=k_b, wilayah=regency, tahun=tahun, nilai_num=Decimal("20"), nilai_teks="20")

        response = self.client.get("/pencarian/api/search/", {"q": "produksi alpukat + produksi mangga"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        concepts = data.get("multi_concepts") or []
        self.assertGreaterEqual(len(concepts), 2, "query '+': harus ada match per konsep")
        nomor_tabels = []
        for m in concepts:
            obs = m.get("observations") or []
            self.assertTrue(obs, "setiap konsep harus punya observasi")
            nomor_tabels.append(obs[0]["tabel"]["nomor_tabel"])
        self.assertEqual(
            len(set(nomor_tabels)), len(nomor_tabels),
            f"konsep harus menunjuk tabel berbeda: {nomor_tabels}",
        )

    def test_single_concept_query_has_empty_multi_concepts(self):
        pub = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2025", tahun_terbit=2025)
        bab = Bab.objects.create(publikasi=pub, nomor=5, nama="Pertanian")
        regency = Wilayah.objects.create(nama="Kabupaten Tasikmalaya", jenis="kabupaten")
        ind = Indikator.objects.create(nama="Produksi Alpukat", satuan="kuintal")
        t = Tabel.objects.create(bab=bab, nomor_tabel="5.1.1", judul="Produksi Alpukat Menurut Kecamatan")
        k = KolomTabel.objects.create(tabel=t, urutan=1, indikator=ind)
        Fakta.objects.create(tabel=t, kolom=k, wilayah=regency, tahun=2024, nilai_num=Decimal("10"), nilai_teks="10")

        response = self.client.get("/pencarian/api/search/", {"q": "produksi alpukat"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("multi_concepts") or [], [])

    def test_dan_separator_returns_per_concept_matches(self):
        pub = Publikasi.objects.create(judul="Kabupaten Tasikmalaya Angka 2025", tahun_terbit=2025)
        bab = Bab.objects.create(publikasi=pub, nomor=5, nama="Pertanian")
        regency = Wilayah.objects.create(nama="Kabupaten Tasikmalaya", jenis="kabupaten")

        ind_a = Indikator.objects.create(nama="Produksi Alpukat", satuan="kuintal")
        ind_b = Indikator.objects.create(nama="Produksi Mangga", satuan="kuintal")
        t_a = Tabel.objects.create(bab=bab, nomor_tabel="5.1.1", judul="Produksi Alpukat Menurut Kecamatan")
        t_b = Tabel.objects.create(bab=bab, nomor_tabel="5.1.2", judul="Produksi Mangga Menurut Kecamatan")
        k_a = KolomTabel.objects.create(tabel=t_a, urutan=1, indikator=ind_a)
        k_b = KolomTabel.objects.create(tabel=t_b, urutan=1, indikator=ind_b)
        for tahun in (2023, 2024):
            Fakta.objects.create(tabel=t_a, kolom=k_a, wilayah=regency, tahun=tahun, nilai_num=Decimal("10"), nilai_teks="10")
            Fakta.objects.create(tabel=t_b, kolom=k_b, wilayah=regency, tahun=tahun, nilai_num=Decimal("20"), nilai_teks="20")

        response = self.client.get("/pencarian/api/search/", {"q": "produksi alpukat dan produksi mangga"})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        concepts = data.get("multi_concepts") or []
        self.assertGreaterEqual(len(concepts), 2, "query 'dan': harus ada match per konsep")
        nomor_tabels = [m["observations"][0]["tabel"]["nomor_tabel"] for m in concepts if m.get("observations")]
        self.assertEqual(
            len(set(nomor_tabels)), len(nomor_tabels),
            f"konsep harus menunjuk tabel berbeda: {nomor_tabels}",
        )