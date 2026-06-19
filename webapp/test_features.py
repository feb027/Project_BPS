"""Tes fitur: normalisasi indikator, cek total, dan ekspor CSV/Excel."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()

from apps.data.services import normalisasi_indikator, ingest_long_rows
from apps.data.exports import export_csv, KOLOM
from apps.katalog.models import Publikasi, Tabel
from apps.referensi.models import Indikator
from apps.ekstraksi.engine import cek_total


def test_normalisasi():
    assert normalisasi_indikator("Laki-laki") == normalisasi_indikator("Laki-Laki")
    assert normalisasi_indikator("Jumlah Desa / Kelurahan") == normalisasi_indikator("Jumlah Desa/Kelurahan")
    assert normalisasi_indikator("  Luas   Daerah ") == "luas daerah"
    print("OK test_normalisasi")


def test_cek_total_cocok():
    tabel = {
        "n_kolom": 2,
        "rows": [
            {"wilayah": "A", "sel": [{"teks": "10"}, {"teks": "5"}]},
            {"wilayah": "B", "sel": [{"teks": "20"}, {"teks": "15"}]},
        ],
        "total": {"wilayah": "Total", "sel": [{"teks": "30"}, {"teks": "20"}]},
    }
    r = cek_total(tabel)
    assert r["ada_total"] and r["semua_cocok"], r
    print("OK test_cek_total_cocok")


def test_cek_total_mismatch():
    tabel = {
        "n_kolom": 1,
        "rows": [
            {"wilayah": "A", "sel": [{"teks": "10"}]},
            {"wilayah": "B", "sel": [{"teks": "20"}]},
        ],
        "total": {"wilayah": "Total", "sel": [{"teks": "99"}]},  # salah
    }
    r = cek_total(tabel)
    assert r["ada_total"] and not r["semua_cocok"], r
    assert r["per_kolom"][0]["cocok"] is False
    print("OK test_cek_total_mismatch:", r["per_kolom"][0])


def test_cek_total_ribuan():
    # format Indonesia '1.946.197' harus terbaca sbg 1946197
    tabel = {
        "n_kolom": 1,
        "rows": [
            {"wilayah": "A", "sel": [{"teks": "983.509"}]},
            {"wilayah": "B", "sel": [{"teks": "962.688"}]},
        ],
        "total": {"wilayah": "Total", "sel": [{"teks": "1.946.197"}]},
    }
    r = cek_total(tabel)
    assert r["semua_cocok"], r["per_kolom"]
    print("OK test_cek_total_ribuan")


def test_ingest_dedup_indikator():
    # bersihkan sisa run sebelumnya agar tes idempoten
    Indikator.objects.filter(nama__icontains="Zzq").delete()
    pub, _ = Publikasi.objects.get_or_create(judul="__TEST_DEDUP__", defaults={"tahun_terbit": 2099})
    n_awal = Indikator.objects.count()
    rows = []
    for nm in ["Zzq Indikator Unik", "Zzq Indikator  Unik", "zzq indikator unik"]:
        rows.append({
            "bab": "Tes", "nomor_tabel": "99.9.9", "judul_tabel": "Tes Dedup",
            "wilayah": "Kabupaten Tasikmalaya", "rincian": "X-" + nm,
            "indikator": nm, "satuan": "orang", "tahun": "2025",
            "nilai_num": "1", "nilai_teks": "1", "flag": "ada",
        })
    ingest_long_rows(rows, publikasi=pub)
    # ketiga varian -> 1 indikator
    dibuat = Indikator.objects.count() - n_awal
    assert dibuat == 1, f"harus 1 indikator baru, dapat {dibuat}"
    print("OK test_ingest_dedup_indikator")
    pub.delete()
    Indikator.objects.filter(nama__icontains="Zzq").delete()


def test_export_csv():
    pub, _ = Publikasi.objects.get_or_create(judul="__TEST_EXPORT__", defaults={"tahun_terbit": 2098})
    rows = [{
        "bab": "Tes", "nomor_tabel": "98.1.1", "judul_tabel": "Tes Ekspor",
        "wilayah": "Cipatujah", "indikator": "Luas Daerah", "satuan": "km2",
        "tahun": "2025", "nilai_num": "241", "nilai_teks": "241", "flag": "ada",
        "sumber": "BPS",
    }]
    ingest_long_rows(rows, publikasi=pub)
    qs = Tabel.objects.filter(bab__publikasi=pub)
    resp = export_csv(qs, "tes")
    body = resp.content.decode("utf-8-sig")
    assert resp.status_code == 200
    assert "Content-Disposition" in resp
    assert all(k in body.splitlines()[0] for k in ("nomor_tabel", "indikator", "nilai_num"))
    assert "98.1.1" in body and "Cipatujah" in body and "Luas Daerah" in body
    print("OK test_export_csv")
    pub.delete()


if __name__ == "__main__":
    test_normalisasi()
    test_cek_total_cocok()
    test_cek_total_mismatch()
    test_cek_total_ribuan()
    test_ingest_dedup_indikator()
    test_export_csv()
    print("\nSEMUA TES FITUR LULUS")
