from decimal import Decimal, InvalidOperation
import re

from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404, redirect, render

from apps.katalog.models import Bab, Publikasi, Tabel, KolomTabel
from .models import Fakta
from .services import ingest_long_rows
from .exports import export_csv, export_xlsx


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
    """Parses standard numbers (e.g. '2018', '2.5'). Handles comma as decimal fallback."""
    s = (teks or "").strip()
    if s == "":
        return None
    # If there are multiple dots (e.g. 1.234.567) or dot is followed by exactly 3 digits and no other separators,
    # it's highly ambiguous. But if we instruct the user to avoid thousand separators, 
    # we can just replace comma with dot (for Indonesian decimal typos) and parse.
    s = s.replace(",", ".")
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
        from apps.referensi.models import Indikator, Wilayah, Rincian
        from apps.data.services import _jenis_wilayah
        
        # 1. Update Kolom Tahun dan Satuan
        for k in koloms:
            yr_str = request.POST.get(f"kol-{k.id}-tahun")
            sat_str = request.POST.get(f"kol-{k.id}-satuan")
            
            needs_save = False
            
            if yr_str is not None:
                yr_val = yr_str.strip()
                yr = None
                if yr_val:
                    m = re.search(r"\d{4}", yr_val)
                    if m: yr = int(m.group(0))
                if k.tahun != yr:
                    k.tahun = yr
                    needs_save = True
                    
            if sat_str is not None:
                sat = sat_str.strip() or "-"
                if k.satuan != sat:
                    k.satuan = sat
                    needs_save = True
                    
            if needs_save:
                k.save(update_fields=['tahun', 'satuan'])
                diubah += 1

        # 2. Hapus & Ganti Nama Baris
        for key, val in request.POST.items():
            if key.startswith("del-") and val == "1":
                sid = int(key.split("-")[1])
                if is_kategori:
                    Fakta.objects.filter(tabel=tabel, rincian_id=sid).delete()
                else:
                    Fakta.objects.filter(tabel=tabel, wilayah_id=sid).delete()
                diubah += 1
            elif key.startswith("row-") and key.endswith("-nama"):
                sid = int(key.split("-")[1])
                new_nama = val.strip()
                if not new_nama: continue
                if is_kategori:
                    r_old = Rincian.objects.filter(id=sid).first()
                    if r_old and r_old.nama != new_nama:
                        r_new, _ = Rincian.objects.get_or_create(nama=new_nama, defaults={'kelompok': r_old.kelompok})
                        Fakta.objects.filter(tabel=tabel, rincian_id=sid).update(rincian=r_new)
                        diubah += 1
                else:
                    w_old = Wilayah.objects.filter(id=sid).first()
                    if w_old and w_old.nama != new_nama:
                        w_new, _ = Wilayah.objects.get_or_create(nama=new_nama, defaults={'jenis': _jenis_wilayah(new_nama)})
                        Fakta.objects.filter(tabel=tabel, wilayah_id=sid).update(wilayah=w_new)
                        diubah += 1

        # 2b. Hapus Kolom (dan seluruh fakta di kolom tersebut)
        hapus_kolom_ids = [
            int(key.split("delkol-")[1])
            for key in request.POST
            if key.startswith("delkol-") and request.POST[key] == "1"
        ]
        if hapus_kolom_ids:
            KolomTabel.objects.filter(tabel=tabel, id__in=hapus_kolom_ids).delete()
            # Reindex urutan kolom agar tetap rapat (1,2,3,...)
            for i, k in enumerate(
                KolomTabel.objects.filter(tabel=tabel).order_by("urutan"), start=1
            ):
                if k.urutan != i:
                    k.urutan = i
                    k.save(update_fields=["urutan"])
            # Muat ulang daftar kolom agar loop di bawah memakai data terbaru
            koloms = list(tabel.kolom_set.select_related("indikator").order_by("urutan"))
            diubah += len(hapus_kolom_ids)

        # 2c. Tambah Kolom Baru ("Tambah Kolom" di Edit Nilai)
        # Setiap kolom baru dikirim sebagai kolnew-<nk>-nama / -satuan / -tahun,
        # dan nilainya sebagai cellnew-<subject>-NK<nk>.
        kolom_baru_by_nk = {}
        for key, val in request.POST.items():
            m = re.match(r"^kolnew-(\d+)-nama$", key)
            if not m:
                continue
            nama = val.strip()
            if not nama:
                continue
            nk = int(m.group(1))
            satuan = request.POST.get(f"kolnew-{nk}-satuan", "").strip()
            tahun_raw = request.POST.get(f"kolnew-{nk}-tahun", "").strip()
            tahun = None
            if tahun_raw:
                tm = re.search(r"\d{4}", tahun_raw)
                if tm:
                    tahun = int(tm.group(0))
            ind, _ = Indikator.objects.get_or_create(
                nama=nama, defaults={"satuan": satuan, "tipe_nilai": "numerik"}
            )
            urut = (KolomTabel.objects.filter(tabel=tabel).aggregate(m=Max("urutan"))["m"] or 0) + 1
            kbaru = KolomTabel.objects.create(
                tabel=tabel, urutan=urut, indikator=ind, satuan=satuan,
                tahun=tahun, tipe_nilai="numerik",
            )
            kolom_baru_by_nk[nk] = kbaru
            diubah += 1
        if kolom_baru_by_nk:
            koloms = list(tabel.kolom_set.select_related("indikator").order_by("urutan"))

        # 2d. Tambah Baris Baru ("Tambah Baris" di Edit Nilai)
        # Setiap baris baru dikirim sebagai rownew-<n>-nama; nilainya sebagai
        # cellnew-<n>-<kolom_id> (kolom existing) atau cellnew-<n>-NK<nk>.
        baris_baru_by_n = {}
        for key, val in request.POST.items():
            m = re.match(r"^rownew-(\d+)-nama$", key)
            if not m:
                continue
            nama = val.strip()
            if not nama:
                continue
            n = int(m.group(1))
            if is_kategori:
                ent, _ = Rincian.objects.get_or_create(nama=nama)
            else:
                ent, _ = Wilayah.objects.get_or_create(
                    nama=nama, defaults={"jenis": _jenis_wilayah(nama)}
                )
            baris_baru_by_n[n] = ent
            diubah += 1

        # 2e. Isi nilai sel baris/kolom baru
        # Format: cellnew-<n>-<kolom_id>  (baris baru, kolom existing)
        #         cellnew-<n>-NK<nk>       (baris baru, kolom baru)
        #         cellnew-<sid>-NK<nk>      (baris existing, kolom baru)
        for key, val in request.POST.items():
            if not key.startswith("cellnew-"):
                continue
            raw = val.strip()
            if raw == "":
                continue
            rest = key[len("cellnew-"):]
            sid_str, _, col_str = rest.rpartition("-")
            if not sid_str or not col_str:
                continue
            # Tentukan kolom target
            if col_str.startswith("NK"):
                nk = int(col_str[2:])
                kol = kolom_baru_by_nk.get(nk)
                if kol is None:
                    continue
            else:
                try:
                    kol = KolomTabel.objects.filter(tabel=tabel, id=int(col_str)).first()
                except ValueError:
                    continue
                if kol is None:
                    continue
            # Tentukan subjek (baris)
            try:
                sid = int(sid_str)
            except ValueError:
                continue
            ent = baris_baru_by_n.get(sid)  # baris baru memakai index rownew
            if ent is None:
                # baris existing → sid adalah id wilayah/rincian
                if is_kategori:
                    ent = Rincian.objects.filter(id=sid).first()
                else:
                    ent = Wilayah.objects.filter(id=sid).first()
                if ent is None:
                    continue
            tipe_teks = kol.tipe_nilai == "teks"
            defaults = {}
            if tipe_teks:
                defaults = {"nilai_teks": raw, "flag": Fakta.Flag.ADA}
            else:
                num = _parse_angka(raw)
                defaults = {
                    "nilai_num": num,
                    "nilai_teks": raw,
                    "flag": Fakta.Flag.ADA if num is not None else Fakta.Flag.PERLU_CEK,
                }
            lookup = {"tabel": tabel, "kolom": kol, "tahun": kol.tahun}
            if is_kategori:
                lookup["rincian"] = ent
            else:
                lookup["wilayah"] = ent
            Fakta.objects.update_or_create(**lookup, defaults=defaults)
            diubah += 1

        # 3. Update Nilai Sel Fakta
        for f in Fakta.objects.filter(tabel=tabel).select_related("kolom"):
            key = f"f-{f.id}"
            if key not in request.POST:
                continue
            # jika sel di baris yang sudah dihapus, request.POST[key] tetap ada tapi f mungkin masih di memory query
            # tapi tidak apa-apa karena save() akan gagal atau tidak merusak data.
            raw = request.POST[key].strip()
            tipe_teks = f.kolom and f.kolom.tipe_nilai == "teks"
            if tipe_teks:
                if f.nilai_teks != raw:
                    f.nilai_teks = raw
                    f.flag = Fakta.Flag.ADA if raw else f.flag
                    try:
                        f.save(update_fields=["nilai_teks", "flag"])
                        diubah += 1
                    except Exception: pass
            else:
                num = _parse_angka(raw)
                if f.nilai_num != num:
                    f.nilai_num = num
                    f.nilai_teks = raw
                    if num is not None:
                        f.flag = Fakta.Flag.ADA
                    try:
                        f.save(update_fields=["nilai_num", "nilai_teks", "flag"])
                        diubah += 1
                    except Exception: pass
        
        messages.success(request, f"{diubah} perubahan disimpan.")
        cache.clear()
        return redirect("data:tabel_detail", pk=pk)

    fakta = Fakta.objects.filter(tabel=tabel).select_related("wilayah", "rincian", "kolom")
    fmap, subjek = {}, {}
    for f in fakta:
        ent = f.rincian if is_kategori else f.wilayah
        if ent is None:
            continue
        if ent.id not in subjek:
            if is_kategori:
                is_total = "kabupaten tasikmalaya" in ent.nama.lower() or ent.nama.lower().strip() in ["total", "jumlah", "tasikmalaya"]
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
        return {"id": sid, "nama": subjek[sid]["nama"], "sel": [fmap.get((sid, k.id)) for k in koloms]}

    ids_reg = sorted((s for s, v in subjek.items() if not v["is_total"]),
                     key=lambda i: subjek[i]["nama"])
    ids_tot = [s for s, v in subjek.items() if v["is_total"]]
    # Tabel level kabupaten/provinsi (1 wilayah, tidak ada baris kecamatan):
    # tampilkan baris total sebagai satu-satunya baris agar tidak kosong.
    if not ids_reg and ids_tot:
        ids_reg, ids_tot = ids_tot, []
    baris = [buat_baris(s) for s in ids_reg]
    baris_total = [buat_baris(s) for s in ids_tot]

    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(tabel.bab.publikasi.tahun_terbit), "url": f"/data/pub/{tabel.bab.publikasi_id}/"},
        {"label": tabel.bab.nama, "url": f"/data/bab/{tabel.bab_id}/"},
        {"label": tabel.nama_tampil, "url": ""},
    ]
    ctx = {
        "tabel": tabel, "kolom_judul": kolom_judul, "koloms": koloms, "baris": baris,
        "baris_total": baris_total,
        "label_baris": "Rincian" if is_kategori else "Kecamatan",
        "edit": edit, "breadcrumb": crumb,
    }
    return render(request, "data/tabel_detail.html", ctx)


def tabel_isi(request, pk):
    """Grid isian data. Tabel kecamatan: prefill 39 kecamatan + Total."""
    # Fitur ini digantikan oleh "Edit Nilai" (?edit=1 di tabel_detail).
    # Pertahankan agar URL lama tidak 404; arahkan ke halaman tabel.
    return redirect("data:tabel_detail", pk=pk)


def mark_fakta_safe(request, pk):
    """Tandai data anomali menjadi aman (ADA) dari halaman beranda."""
    if request.method == "POST":
        fakta = get_object_or_404(Fakta, pk=pk)
        fakta.flag = Fakta.Flag.ADA
        fakta.save(update_fields=['flag'])
        cache.delete("dashboard_jml_perlu_cek")
        messages.success(request, f"Data tabel {fakta.tabel.nomor_tabel} berhasil ditandai aman.")
    return redirect("/")


def verifikasi_tabel(request, pk):
    """Mengunci tabel dengan mengubah statusnya menjadi VERIFIKASI."""
    if request.method == "POST":
        tabel = get_object_or_404(Tabel, pk=pk)
        tabel.status_verifikasi = Tabel.Status.VERIFIKASI
        tabel.save(update_fields=['status_verifikasi'])
        messages.success(request, "Tabel berhasil dikunci dan ditandai terverifikasi.")
    return redirect("data:tabel_detail", pk=pk)
