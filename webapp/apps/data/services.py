"""
Layanan ingest: menelan baris format LONG (dari CSV ekstraksi atau, nanti,
dari engine PDF) lalu meng-upsert ke Katalog + Referensi + Fakta.

Satu sumber kebenaran untuk SEMUA cara input data -> relasi dirangkai otomatis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from apps.katalog.models import Bab, KolomTabel, Publikasi, Tabel
from apps.referensi.models import Indikator, Rincian, Wilayah
from .models import Fakta


@dataclass
class HasilIngest:
    fakta_baru: int = 0
    fakta_diperbarui: int = 0
    tabel: int = 0
    indikator: int = 0
    wilayah: int = 0
    rincian: int = 0
    catatan: list[str] = field(default_factory=list)


def _to_decimal(nilai) -> Decimal | None:
    if nilai is None:
        return None
    s = str(nilai).strip()
    if s == "":
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_int(nilai) -> int | None:
    if nilai is None:
        return None
    s = str(nilai).strip()
    if not s:
        return None
    m = re.search(r"\d{4}", s)
    return int(m.group()) if m else None


def _jenis_wilayah(nama: str) -> str:
    low = nama.lower()
    if "kabupaten" in low or "kota" in low:
        return Wilayah.Jenis.KABUPATEN
    if "provinsi" in low:
        return Wilayah.Jenis.PROVINSI
    return Wilayah.Jenis.KECAMATAN


def normalisasi_indikator(nama: str) -> str:
    """
    Kunci-samakan nama indikator agar varian sepele tidak terpecah jadi banyak.
    Konservatif: hanya menyamakan beda huruf besar/kecil, spasi, tanda hubung,
    dan spasi di sekitar '/'. (mis. 'Laki-laki' == 'Laki-Laki').
    """
    s = (nama or "").lower().strip()
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+", " ", s)
    return s


@transaction.atomic
def ingest_long_rows(rows, publikasi: Publikasi, user=None) -> HasilIngest:
    """
    rows: iterable of dict dengan kunci minimal:
      bab, nomor_tabel, judul_tabel, wilayah, indikator, satuan,
      nilai_num, nilai_teks, flag, sumber
    Opsional: rincian, tahun.
    """
    hasil = HasilIngest()
    cache_indikator: dict[str, Indikator] = {}
    cache_wilayah: dict[str, Wilayah] = {}
    cache_rincian: dict[str, Rincian] = {}
    cache_tabel: dict[str, Tabel] = {}
    urutan_kolom: dict[int, int] = {}  # tabel_id -> counter

    # indeks indikator yang sudah ada, dikunci dgn nama ter-normalisasi
    # -> ingest menyatukan varian sepele ke indikator yang sudah ada
    idx_indikator: dict[str, Indikator] = {}
    for ind in Indikator.objects.all():
        idx_indikator.setdefault(normalisasi_indikator(ind.nama), ind)

    for row in rows:
        nomor_tabel = (row.get("nomor_tabel") or "").strip()
        if not nomor_tabel:
            continue

        # --- Katalog: Bab + Tabel ---
        if nomor_tabel not in cache_tabel:
            nomor_bab = _to_int(nomor_tabel.split(".")[0]) or int(nomor_tabel.split(".")[0])
            bab, _ = Bab.objects.get_or_create(
                publikasi=publikasi, nomor=nomor_bab,
                defaults={"nama": (row.get("bab") or f"Bab {nomor_bab}").strip()},
            )
            punya_rincian = bool((row.get("rincian") or "").strip())
            tipe_baris = Tabel.TipeBaris.KATEGORI if punya_rincian else Tabel.TipeBaris.KECAMATAN
            tabel, dibuat = Tabel.objects.get_or_create(
                bab=bab, nomor_tabel=nomor_tabel,
                defaults={
                    "judul": (row.get("judul_tabel") or "").strip()[:400],
                    "judul_en": (row.get("judul_en") or "").strip()[:400],
                    "sumber": (row.get("sumber") or "").strip()[:300],
                    "tipe_baris": tipe_baris,
                    "status_verifikasi": Tabel.Status.EKSTRAK,
                },
            )
            cache_tabel[nomor_tabel] = tabel
            if dibuat:
                hasil.tabel += 1
        tabel = cache_tabel[nomor_tabel]

        # --- Referensi: Indikator (dengan penyatuan varian via normalisasi) ---
        nama_ind = (row.get("indikator") or "").strip()
        satuan = (row.get("satuan") or "").strip()
        nilai_num = _to_decimal(row.get("nilai_num"))
        tipe_nilai = Indikator.TipeNilai.NUMERIK if nilai_num is not None else Indikator.TipeNilai.TEKS
        if nama_ind not in cache_indikator:
            kunci = normalisasi_indikator(nama_ind)
            ind = idx_indikator.get(kunci)
            if ind is None:
                ind = Indikator.objects.create(
                    nama=nama_ind, satuan=satuan, tipe_nilai=tipe_nilai,
                )
                idx_indikator[kunci] = ind
                hasil.indikator += 1
            cache_indikator[nama_ind] = ind
        indikator = cache_indikator[nama_ind]
        # bila sebelumnya tertebak 'teks' tapi ada angka, naikkan ke numerik
        if nilai_num is not None and indikator.tipe_nilai == Indikator.TipeNilai.TEKS:
            indikator.tipe_nilai = Indikator.TipeNilai.NUMERIK
            indikator.save(update_fields=["tipe_nilai"])

        # --- Katalog: KolomTabel (tautan tabel<->indikator) ---
        tahun = _to_int(row.get("tahun"))
        if tabel.id not in urutan_kolom:
            # mulai dari urutan tertinggi yang sudah ada di DB (ingest inkremental)
            maks = tabel.kolom_set.aggregate(m=Max("urutan"))["m"] or 0
            urutan_kolom[tabel.id] = maks
        kolom, kolom_baru = KolomTabel.objects.get_or_create(
            tabel=tabel, indikator=indikator, tahun=tahun,
            defaults={
                "urutan": urutan_kolom[tabel.id] + 1,
                "satuan": satuan,
                "tipe_nilai": tipe_nilai,
            },
        )
        if kolom_baru:
            urutan_kolom[tabel.id] += 1

        # --- Referensi: Wilayah & Rincian ---
        wilayah = None
        nama_wil = (row.get("wilayah") or "").strip()
        if nama_wil:
            if nama_wil not in cache_wilayah:
                w, dibuat = Wilayah.objects.get_or_create(
                    nama=nama_wil, jenis=_jenis_wilayah(nama_wil), parent=None,
                )
                cache_wilayah[nama_wil] = w
                if dibuat:
                    hasil.wilayah += 1
            wilayah = cache_wilayah[nama_wil]

        rincian = None
        nama_rin = (row.get("rincian") or "").strip()
        if nama_rin:
            kelompok = (row.get("rincian_dim") or "").strip()
            key = f"{nama_rin}|{kelompok}"
            if key not in cache_rincian:
                r, dibuat = Rincian.objects.get_or_create(nama=nama_rin, kelompok=kelompok)
                cache_rincian[key] = r
                if dibuat:
                    hasil.rincian += 1
            rincian = cache_rincian[key]

        # --- Data: Fakta (idempoten by kunci) ---
        flag = (row.get("flag") or Fakta.Flag.ADA).strip()
        nilai_teks = (row.get("nilai_teks") or "").strip()[:255]
        _, dibuat = Fakta.objects.update_or_create(
            tabel=tabel, kolom=kolom, wilayah=wilayah, rincian=rincian, tahun=tahun,
            defaults={
                "nilai_num": nilai_num,
                "nilai_teks": nilai_teks,
                "flag": flag,
                "dibuat_oleh": user,
            },
        )
        if dibuat:
            hasil.fakta_baru += 1
        else:
            hasil.fakta_diperbarui += 1

    return hasil
