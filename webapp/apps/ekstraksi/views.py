import os
import uuid

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from apps.data.services import ingest_long_rows
from apps.katalog.models import Publikasi
from .engine import ekstrak


def index(request):
    return render(request, "ekstraksi/index.html", {
        "pubs": Publikasi.objects.order_by("-tahun_terbit"),
    })


def preview(request):
    if request.method != "POST" or "pdf" not in request.FILES:
        return redirect("ekstraksi:index")

    f = request.FILES["pdf"]
    mode = request.POST.get("mode", "kecamatan")
    try:
        hal_awal = int(request.POST.get("hal_awal"))
        hal_akhir = int(request.POST.get("hal_akhir"))
    except (TypeError, ValueError):
        messages.error(request, "Halaman dari/sampai harus angka.")
        return redirect("ekstraksi:index")

    # simpan sementara lalu ekstrak
    tmp_dir = os.path.join(settings.MEDIA_ROOT, "tmp_ekstraksi")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.pdf")
    with open(tmp_path, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)
    try:
        hasil = ekstrak(tmp_path, hal_awal, hal_akhir, mode=mode)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if not hasil["rows"]:
        messages.error(request, "Tidak ada baris terdeteksi pada rentang itu. Cek nomor halaman / mode.")
        return redirect("ekstraksi:index")

    ctx = {
        "hasil": hasil,
        "kolom_range": range(hasil["n_kolom"]),
        "kolom_data": list(zip(range(hasil["n_kolom"]), hasil["headers"])),
        "pub_id": request.POST.get("pub_id", ""),
        "judul_baru": request.POST.get("judul_baru", ""),
        "tahun_baru": request.POST.get("tahun_baru", ""),
        "hal_awal": hal_awal, "hal_akhir": hal_akhir, "mode": mode,
    }
    return render(request, "ekstraksi/preview.html", ctx)


def simpan(request):
    if request.method != "POST":
        return redirect("ekstraksi:index")

    # ---- publikasi ----
    pub_id = request.POST.get("pub_id")
    judul_baru = (request.POST.get("judul_baru") or "").strip()
    if pub_id:
        publikasi = Publikasi.objects.get(pk=pub_id)
    elif judul_baru:
        publikasi, _ = Publikasi.objects.get_or_create(
            judul=judul_baru, tahun_terbit=int(request.POST.get("tahun_baru") or 0),
        )
    else:
        messages.error(request, "Pilih publikasi atau isi judul baru.")
        return redirect("ekstraksi:index")

    nomor_tabel = (request.POST.get("nomor_tabel") or "").strip()
    judul = (request.POST.get("judul") or "").strip()
    bab_nama = (request.POST.get("bab_nama") or "").strip()
    sumber = (request.POST.get("sumber") or "").strip()
    mode = request.POST.get("mode", "kecamatan")
    n_rows = int(request.POST.get("n_rows") or 0)
    n_kol = int(request.POST.get("n_kol") or 0)

    # ---- definisi kolom ----
    kolom_def = []
    for j in range(n_kol):
        kolom_def.append({
            "nama": (request.POST.get(f"kol-{j}-nama") or f"Kolom {j+1}").strip(),
            "satuan": (request.POST.get(f"kol-{j}-satuan") or "").strip(),
            "tahun": (request.POST.get(f"kol-{j}-tahun") or "").strip(),
        })

    # ---- bangun baris format long ----
    rows = []

    def tambah(nama, prefix):
        for j in range(n_kol):
            teks = (request.POST.get(f"{prefix}-{j}") or "").strip()
            r = {
                "bab": bab_nama, "nomor_tabel": nomor_tabel, "judul_tabel": judul,
                "indikator": kolom_def[j]["nama"],
                "satuan": kolom_def[j]["satuan"], "tahun": kolom_def[j]["tahun"],
                "nilai_teks": teks, "nilai_num": "", "flag": "ada", "sumber": sumber,
            }
            if mode == "kategori":
                r["wilayah"] = "Kabupaten Tasikmalaya"
                r["rincian"] = nama
            else:
                r["wilayah"] = nama
            rows.append(r)

    for i in range(n_rows):
        nm = (request.POST.get(f"row-{i}-nama") or "").strip()
        if nm:
            tambah(nm, f"cell-{i}")
    if request.POST.get("ada_total") == "1":
        tambah("Kabupaten Tasikmalaya", "total")

    # bersihkan angka (nilai_teks -> nilai_num + flag) memakai engine
    from .engine import clean_num
    for r in rows:
        num, _, flag = clean_num(r["nilai_teks"])
        r["nilai_num"] = num or ""
        r["flag"] = flag

    hasil = ingest_long_rows(rows, publikasi=publikasi)
    messages.success(request, f"Tersimpan: {hasil.fakta_baru} nilai baru untuk tabel {nomor_tabel}.")

    from apps.katalog.models import Tabel
    t = Tabel.objects.filter(bab__publikasi=publikasi, nomor_tabel=nomor_tabel).first()
    return redirect("data:tabel_detail", pk=t.pk) if t else redirect("data:home")
