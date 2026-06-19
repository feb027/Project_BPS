"""
Ekspor data Fakta ke CSV / Excel (format LONG, sama dgn skema impor).

Format kolom mengikuti CSV ekstraksi agar bisa di-impor ulang (round-trip):
  bab, nomor_tabel, judul_tabel, wilayah, rincian, indikator, satuan,
  tahun, nilai_num, nilai_teks, flag, sumber
"""
from __future__ import annotations

import csv

from django.http import HttpResponse

from .models import Fakta

KOLOM = [
    "bab", "nomor_tabel", "judul_tabel", "wilayah", "rincian", "indikator",
    "satuan", "tahun", "nilai_num", "nilai_teks", "flag", "sumber",
]


def _fakta_queryset(tabel_qs):
    return (
        Fakta.objects
        .filter(tabel__in=tabel_qs)
        .select_related("tabel__bab", "kolom__indikator", "wilayah", "rincian")
        .order_by("tabel__nomor_tabel", "rincian__nama", "wilayah__nama", "tahun")
    )


def _baris(f: Fakta) -> dict:
    kolom = f.kolom
    indikator = kolom.indikator if kolom else None
    return {
        "bab": f.tabel.bab.nama,
        "nomor_tabel": f.tabel.nomor_tabel,
        "judul_tabel": f.tabel.judul,
        "wilayah": f.wilayah.nama if f.wilayah else "",
        "rincian": f.rincian.nama if f.rincian else "",
        "indikator": indikator.nama if indikator else "",
        "satuan": kolom.satuan if kolom else "",
        "tahun": f.tahun or "",
        "nilai_num": "" if f.nilai_num is None else f.nilai_num,
        "nilai_teks": f.nilai_teks,
        "flag": f.flag,
        "sumber": f.tabel.sumber,
    }


def export_csv(tabel_qs, nama_file: str) -> HttpResponse:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=KOLOM)
    w.writeheader()
    for f in _fakta_queryset(tabel_qs):
        w.writerow(_baris(f))
    # satu BOM saja, encode manual -> Excel membaca UTF-8 dengan benar
    data = ("\ufeff" + buf.getvalue()).encode("utf-8")
    resp = HttpResponse(data, content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{nama_file}.csv"'
    return resp


def export_xlsx(tabel_qs, nama_file: str) -> HttpResponse:
    try:
        from openpyxl import Workbook
    except ImportError:
        # fallback ke CSV bila openpyxl tak tersedia
        return export_csv(tabel_qs, nama_file)

    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    ws.append([k.replace("_", " ").title() for k in KOLOM])
    for f in _fakta_queryset(tabel_qs):
        b = _baris(f)
        ws.append([b[k] for k in KOLOM])
    # lebar kolom sederhana
    for i, k in enumerate(KOLOM, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(12, len(k) + 4)

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{nama_file}.xlsx"'
    wb.save(resp)
    return resp
