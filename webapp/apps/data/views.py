from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from apps.katalog.models import Bab, Publikasi, Tabel
from .models import Fakta
from .services import ingest_long_rows
from .exports import export_csv, export_xlsx
from apps.ekstraksi.engine import KECAMATAN, clean_num


def _slug(s):
    import re
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(s)).strip("-").lower()
    return s or "data"


def export_tabel(request, pk):
    tabel = get_object_or_404(Tabel.objects.select_related("bab__publikasi"), pk=pk)
    fmt = request.GET.get("format", "csv")
    qs = Tabel.objects.filter(pk=tabel.pk)
    nama = f"tabel-{_slug(tabel.nomor_tabel)}"
    return export_xlsx(qs, nama) if fmt == "xlsx" else export_csv(qs, nama)


def export_publikasi(request, pk):
    pub = get_object_or_404(Publikasi, pk=pk)
    fmt = request.GET.get("format", "csv")
    qs = Tabel.objects.filter(bab__publikasi=pub)
    nama = f"publikasi-{_slug(pub.judul)}-{pub.tahun_terbit}"
    return export_xlsx(qs, nama) if fmt == "xlsx" else export_csv(qs, nama)


def export_bab(request, pk):
    bab = get_object_or_404(Bab.objects.select_related("publikasi"), pk=pk)
    fmt = request.GET.get("format", "csv")
    qs = Tabel.objects.filter(bab=bab)
    nama = f"bab-{bab.nomor}-{_slug(bab.nama)}"
    return export_xlsx(qs, nama) if fmt == "xlsx" else export_csv(qs, nama)


def _parse_angka(teks):
    """'2.706,82' -> Decimal('2706.82'); '' -> None."""
    s = (teks or "").strip()
    if s == "":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


# ---------- Navigasi berjenjang ----------
def home(request):
    """Selektor Tahun: daftar publikasi (buku per tahun terbit)."""
    pubs = Publikasi.objects.order_by("-tahun_terbit").annotate(
        jml_bab=Count("bab_set", distinct=True)
    )
    crumb = [{"label": "Data", "url": ""}]
    return render(request, "data/home.html", {"pubs": pubs, "breadcrumb": crumb})


def publikasi_detail(request, pk):
    """Selektor Bab dalam satu publikasi."""
    pub = get_object_or_404(Publikasi, pk=pk)
    bab_list = pub.bab_set.annotate(jml_tabel=Count("tabel_set")).order_by("nomor")
    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(pub.tahun_terbit), "url": ""},
    ]
    return render(request, "data/publikasi.html",
                  {"pub": pub, "bab_list": bab_list, "breadcrumb": crumb})


def bab_detail(request, pk):
    """Daftar tabel dalam satu bab (dikelompokkan per sub-bab)."""
    bab = get_object_or_404(Bab.objects.select_related("publikasi"), pk=pk)
    tabel_list = (
        bab.tabel_set.annotate(jml=Count("fakta_set")).order_by("nomor_tabel")
    )
    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(bab.publikasi.tahun_terbit), "url": f"/data/pub/{bab.publikasi_id}/"},
        {"label": bab.nama, "url": ""},
    ]
    return render(request, "data/bab.html",
                  {"bab": bab, "tabel_list": tabel_list, "breadcrumb": crumb})


# ---------- Penampil + CRUD ----------
def tabel_detail(request, pk):
    tabel = get_object_or_404(
        Tabel.objects.select_related("bab__publikasi"), pk=pk
    )
    koloms = list(tabel.kolom_set.select_related("indikator").order_by("urutan"))
    is_kategori = tabel.tipe_baris == Tabel.TipeBaris.KATEGORI

    # ----- simpan (CRUD update/create) -----
    if request.method == "POST":
        diubah = 0
        for f in Fakta.objects.filter(tabel=tabel).select_related("kolom"):
            key = f"f-{f.id}"
            if key not in request.POST:
                continue
            raw = request.POST[key].strip()
            tipe_teks = f.kolom and f.kolom.tipe_nilai == "teks"
            if tipe_teks:
                if f.nilai_teks != raw:
                    f.nilai_teks = raw
                    f.flag = Fakta.Flag.ADA if raw else f.flag
                    f.save(update_fields=["nilai_teks", "flag"])
                    diubah += 1
            else:
                num = _parse_angka(raw)
                if f.nilai_num != num:
                    f.nilai_num = num
                    f.nilai_teks = raw
                    if num is not None:
                        f.flag = Fakta.Flag.ADA
                    f.save(update_fields=["nilai_num", "nilai_teks", "flag"])
                    diubah += 1
        messages.success(request, f"{diubah} nilai diperbarui.")
        return redirect("data:tabel_detail", pk=pk)

    fakta = Fakta.objects.filter(tabel=tabel).select_related("wilayah", "rincian", "kolom")
    fmap, subjek = {}, {}
    for f in fakta:
        ent = f.rincian if is_kategori else f.wilayah
        if ent is None:
            continue
        if ent.id not in subjek:
            if is_kategori:
                is_total = "kabupaten tasikmalaya" in ent.nama.lower()
            else:
                is_total = ent.jenis != "kecamatan"
            subjek[ent.id] = {"nama": ent.nama, "is_total": is_total}
        fmap[(ent.id, f.kolom_id)] = f

    kolom_judul = []
    for k in koloms:
        label = k.indikator.nama
        if k.tahun:
            label += f" ({k.tahun})"
        if k.satuan and k.satuan != "-":
            label += f" — {k.satuan}"
        kolom_judul.append(label)

    edit = request.GET.get("edit") == "1"

    def buat_baris(sid):
        return {"nama": subjek[sid]["nama"], "sel": [fmap.get((sid, k.id)) for k in koloms]}

    ids_reg = sorted((s for s, v in subjek.items() if not v["is_total"]),
                     key=lambda i: subjek[i]["nama"])
    ids_tot = [s for s, v in subjek.items() if v["is_total"]]
    baris = [buat_baris(s) for s in ids_reg]
    baris_total = [buat_baris(s) for s in ids_tot]

    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(tabel.bab.publikasi.tahun_terbit), "url": f"/data/pub/{tabel.bab.publikasi_id}/"},
        {"label": tabel.bab.nama, "url": f"/data/bab/{tabel.bab_id}/"},
        {"label": tabel.nama_tampil, "url": ""},
    ]
    ctx = {
        "tabel": tabel, "kolom_judul": kolom_judul, "baris": baris,
        "baris_total": baris_total,
        "label_baris": "Rincian" if is_kategori else "Kecamatan",
        "edit": edit, "breadcrumb": crumb,
    }
    return render(request, "data/tabel_detail.html", ctx)


def tabel_isi(request, pk):
    """Grid isian data. Tabel kecamatan: prefill 39 kecamatan + Total."""
    tabel = get_object_or_404(Tabel.objects.select_related("bab__publikasi"), pk=pk)
    koloms = list(tabel.kolom_set.select_related("indikator").order_by("urutan"))
    is_kategori = tabel.tipe_baris == Tabel.TipeBaris.KATEGORI

    if request.method == "POST":
        n = int(request.POST.get("n_rows") or 0)
        rows = []
        for i in range(n):
            nama = (request.POST.get(f"row-{i}-nama") or "").strip()
            if not nama:
                continue
            for j, k in enumerate(koloms):
                teks = (request.POST.get(f"cell-{i}-{j}") or "").strip()
                num, _, flag = clean_num(teks)
                base = {
                    "bab": tabel.bab.nama, "nomor_tabel": tabel.nomor_tabel,
                    "judul_tabel": tabel.judul, "indikator": k.indikator.nama,
                    "satuan": k.satuan, "tahun": k.tahun or "",
                    "nilai_num": num or "", "nilai_teks": teks, "flag": flag,
                    "sumber": tabel.sumber,
                }
                if is_kategori:
                    base["wilayah"] = "Kabupaten Tasikmalaya"
                    base["rincian"] = nama
                else:
                    base["wilayah"] = nama
                rows.append(base)
        ingest_long_rows(rows, publikasi=tabel.bab.publikasi, user=request.user if request.user.is_authenticated else None)
        messages.success(request, "Data tersimpan.")
        return redirect("data:tabel_detail", pk=pk)

    # ---- prefill ----
    fakta = Fakta.objects.filter(tabel=tabel).select_related("wilayah", "rincian")
    nilai_map = {}  # (nama, kolom_id) -> teks
    nama_ada = []
    for f in fakta:
        ent = f.rincian if is_kategori else f.wilayah
        if ent is None:
            continue
        if ent.nama not in nama_ada:
            nama_ada.append(ent.nama)
        teks = f.nilai_teks or (str(f.nilai_num) if f.nilai_num is not None else "")
        nilai_map[(ent.nama, f.kolom_id)] = teks

    if is_kategori:
        nama_baris = nama_ada  # yang sudah ada; baris baru via tombol
    else:
        nama_baris = list(KECAMATAN) + ["Kabupaten Tasikmalaya"]

    baris = []
    for nama in nama_baris:
        sel = [nilai_map.get((nama, k.id), "") for k in koloms]
        baris.append({"nama": nama, "sel": sel})

    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": tabel.nama_tampil, "url": f"/data/tabel/{tabel.pk}/"},
        {"label": "Isi Data", "url": ""},
    ]
    ctx = {
        "tabel": tabel, "koloms": koloms, "baris": baris,
        "is_kategori": is_kategori, "label_baris": "Rincian" if is_kategori else "Kecamatan",
        "breadcrumb": crumb,
    }
    return render(request, "data/tabel_isi.html", ctx)


def mark_fakta_safe(request, pk):
    """Tandai data anomali menjadi aman (ADA) dari halaman beranda."""
    if request.method == "POST":
        fakta = get_object_or_404(Fakta, pk=pk)
        fakta.flag = Fakta.Flag.ADA
        fakta.save(update_fields=['flag'])
        messages.success(request, f"Data tabel {fakta.tabel.nomor_tabel} berhasil ditandai aman.")
    return redirect("/")
