import os
import uuid

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from apps.data.services import ingest_long_rows
from apps.katalog.models import Publikasi, Tabel
from .engine import clean_num, ekstrak_range, cek_total


def index(request):
    return render(request, "ekstraksi/index.html", {
        "pubs": Publikasi.objects.order_by("-tahun_terbit"),
    })


def preview(request):
    if request.method != "POST" or "pdf" not in request.FILES:
        return redirect("ekstraksi:index")

    f = request.FILES["pdf"]
    try:
        hal_awal = int(request.POST.get("hal_awal"))
        hal_akhir = int(request.POST.get("hal_akhir"))
    except (TypeError, ValueError):
        messages.error(request, "Halaman dari/sampai harus angka.")
        return redirect("ekstraksi:index")
    if hal_akhir < hal_awal:
        hal_awal, hal_akhir = hal_akhir, hal_awal

    pakai_ocr = request.POST.get("ocr", "auto")
    if pakai_ocr not in ("auto", "paksa", "tidak"):
        pakai_ocr = "auto"

    # batasi jumlah halaman agar tidak membebani (OCR berat)
    if (hal_akhir - hal_awal) > 80:
        messages.error(request, "Rentang terlalu besar (maks 80 halaman sekali ekstrak).")
        return redirect("ekstraksi:index")

    # simpan sementara lalu ekstrak
    tmp_dir = os.path.join(settings.MEDIA_ROOT, "tmp_ekstraksi")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.pdf")
    with open(tmp_path, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)
    try:
        daftar = ekstrak_range(tmp_path, hal_awal, hal_akhir, pakai_ocr=pakai_ocr)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    info_ocr = daftar[0]["info_ocr"] if daftar else {"dipakai": False, "tersedia": False, "pesan": ""}

    # buang tabel kosong, siapkan struktur siap-render
    pub_id = request.POST.get("pub_id", "")
    pub_existing = None
    if pub_id:
        pub_existing = Publikasi.objects.filter(pk=pub_id).first()

    tabel_view = []
    for t in daftar:
        if not t["rows"]:
            continue
        t["kolom_data"] = list(zip(range(t["n_kolom"]), t["headers"]))
        # validasi total: jumlah baris vs baris TOTAL per kolom
        t["cek_total"] = cek_total(t)
        # peringatan bila tabel dengan nomor sama sudah ada di publikasi ini
        t["sudah_ada"] = False
        if pub_existing and t["nomor"]:
            t["sudah_ada"] = Tabel.objects.filter(
                bab__publikasi=pub_existing, nomor_tabel=t["nomor"]
            ).exists()
        tabel_view.append(t)

    if not tabel_view:
        pesan = "Tidak ada tabel terdeteksi pada rentang itu. Cek nomor halaman."
        if info_ocr.get("pesan") and not info_ocr.get("tersedia"):
            pesan += " Bila ini PDF hasil scan, OCR belum aktif: " + info_ocr["pesan"]
        messages.error(request, pesan)
        return redirect("ekstraksi:index")

    if info_ocr.get("dipakai"):
        messages.info(request, "Sebagian halaman dibaca via OCR (PDF hasil scan). "
                               "Hasil OCR rawan salah baca — mohon periksa angka dengan teliti.")
    elif info_ocr.get("pesan") and not info_ocr.get("tersedia") and pakai_ocr != "tidak":
        messages.warning(request, "Ada halaman yang sepertinya hasil scan tetapi OCR belum aktif. "
                                  + info_ocr["pesan"])

    ctx = {
        "tabel_list": tabel_view,
        "n_tabel": len(tabel_view),
        "pub_id": pub_id,
        "judul_baru": request.POST.get("judul_baru", ""),
        "tahun_baru": request.POST.get("tahun_baru", ""),
        "hal_awal": hal_awal, "hal_akhir": hal_akhir,
        "info_ocr": info_ocr,
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
            judul=judul_baru,
            defaults={"tahun_terbit": int(request.POST.get("tahun_baru") or 0)},
        )
    else:
        messages.error(request, "Pilih publikasi atau isi judul baru.")
        return redirect("ekstraksi:index")

    n_tabel = int(request.POST.get("n_tabel") or 0)
    pilih = request.POST.getlist("pilih")  # indeks tabel yang dicentang utk disimpan

    rows = []
    nomor_disimpan = []
    for ti in range(n_tabel):
        if str(ti) not in pilih:
            continue
        nomor_tabel = (request.POST.get(f"t{ti}-nomor_tabel") or "").strip()
        if not nomor_tabel:
            continue
        judul = (request.POST.get(f"t{ti}-judul") or "").strip()
        judul_en = (request.POST.get(f"t{ti}-judul_en") or "").strip()
        bab_nama = (request.POST.get(f"t{ti}-bab_nama") or "").strip()
        sumber = (request.POST.get(f"t{ti}-sumber") or "").strip()
        mode = request.POST.get(f"t{ti}-mode", "kecamatan")
        n_rows = int(request.POST.get(f"t{ti}-n_rows") or 0)
        n_kol = int(request.POST.get(f"t{ti}-n_kol") or 0)

        kolom_def = []
        for j in range(n_kol):
            kolom_def.append({
                "nama": (request.POST.get(f"t{ti}-kol-{j}-nama") or f"Kolom {j+1}").strip(),
                "satuan": (request.POST.get(f"t{ti}-kol-{j}-satuan") or "").strip(),
                "tahun": (request.POST.get(f"t{ti}-kol-{j}-tahun") or "").strip(),
            })

        def tambah(nama, prefix):
            for j in range(n_kol):
                teks = (request.POST.get(f"{prefix}-{j}") or "").strip()
                num, _, flag = clean_num(teks)
                r = {
                    "bab": bab_nama, "nomor_tabel": nomor_tabel, "judul_tabel": judul,
                    "judul_en": judul_en,
                    "indikator": kolom_def[j]["nama"],
                    "satuan": kolom_def[j]["satuan"], "tahun": kolom_def[j]["tahun"],
                    "nilai_teks": teks, "nilai_num": num or "", "flag": flag,
                    "sumber": sumber,
                }
                if mode == "kategori":
                    r["wilayah"] = "Kabupaten Tasikmalaya"
                    r["rincian"] = nama
                else:
                    r["wilayah"] = nama
                rows.append(r)

        for i in range(n_rows):
            nm = (request.POST.get(f"t{ti}-row-{i}-nama") or "").strip()
            if nm:
                tambah(nm, f"t{ti}-cell-{i}")
        if request.POST.get(f"t{ti}-ada_total") == "1":
            tambah("Kabupaten Tasikmalaya", f"t{ti}-total")
        nomor_disimpan.append(nomor_tabel)

    if not rows:
        messages.error(request, "Tidak ada tabel yang dipilih untuk disimpan.")
        return redirect("ekstraksi:index")

    hasil = ingest_long_rows(rows, publikasi=publikasi,
                             user=request.user if request.user.is_authenticated else None)
    messages.success(
        request,
        f"Tersimpan {len(nomor_disimpan)} tabel ({', '.join(nomor_disimpan)}): "
        f"{hasil.fakta_baru} nilai baru, {hasil.fakta_diperbarui} diperbarui.",
    )

    if len(nomor_disimpan) == 1:
        t = Tabel.objects.filter(
            bab__publikasi=publikasi, nomor_tabel=nomor_disimpan[0]
        ).first()
        if t:
            return redirect("data:tabel_detail", pk=t.pk)
    return redirect("data:publikasi", pk=publikasi.pk)
