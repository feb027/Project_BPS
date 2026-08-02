import json
import os
import re

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from google import genai

from apps.data.models import Fakta
from apps.data.services import _jenis_wilayah
from apps.referensi.models import Indikator, Rincian, Wilayah
from .forms import BabForm, PublikasiForm, TabelForm
from .models import Bab, KolomTabel, Publikasi, Tabel


def index(request):
    """Halaman master: publikasi + bab + tabel, pintasan edit & sync."""
    pubs = Publikasi.objects.order_by("-tahun_terbit").annotate(
        jml_bab=Count("bab_set", distinct=True),
        jml_tabel=Count("bab_set__tabel_set", distinct=True),
    )
    crumb = [{"label": "Katalog & Master", "url": ""}]
    return render(request, "katalog/index.html", {"pubs": pubs, "breadcrumb": crumb})


def _get_default_kabupaten_wilayah():
    wilayah, _ = Wilayah.objects.get_or_create(
        nama="Kabupaten Tasikmalaya",
        jenis=Wilayah.Jenis.KABUPATEN,
        parent=None,
    )
    return wilayah


def _migrate_row_dimension_to_match_tipe(tabel, old_tipe_baris=None):
    """Keep Fakta row references consistent with Tabel.tipe_baris.

    Manual edits in Pengaturan used to only change metadata. If a table's row
    labels were stored as Wilayah but the user changed the type to
    "Per Kategori (rincian)", the detail page/API started reading Fakta.rincian
    and rendered empty. This migrates the existing row labels into the selected
    dimension so the manual setting actually works.
    """
    facts = Fakta.objects.filter(tabel=tabel).select_related("wilayah", "rincian")

    moved = 0
    if tabel.tipe_baris == Tabel.TipeBaris.KATEGORI:
        default_wilayah = _get_default_kabupaten_wilayah()
        cache_rincian = {}
        for fakta in facts:
            # Prefer existing rincian; otherwise convert the current wilayah label
            # into a rincian category (e.g. PDRB / Net Ekspor / konsumsi RT).
            source_name = (fakta.rincian.nama if fakta.rincian_id else (fakta.wilayah.nama if fakta.wilayah_id else "")).strip()
            if not source_name:
                continue
            key = (source_name, "")
            rincian = cache_rincian.get(key)
            if rincian is None:
                rincian, _ = Rincian.objects.get_or_create(nama=source_name, kelompok="")
                cache_rincian[key] = rincian
            updates = []
            if fakta.rincian_id != rincian.id:
                fakta.rincian = rincian
                updates.append("rincian")
            # Category tables are district-level breakdowns by default. Keeping
            # the old fake wilayah label would make bps-hub group by wilayah.
            if fakta.wilayah_id != default_wilayah.id:
                fakta.wilayah = default_wilayah
                updates.append("wilayah")
            if updates:
                fakta.save(update_fields=updates)
                moved += 1
        return moved

    # Non-kategori tables are rendered by Wilayah. If the user changes a table
    # back to Per Kecamatan/Per Kabupaten, move the row labels from rincian to
    # wilayah so data stays visible too.
    cache_wilayah = {}
    for fakta in facts:
        source_name = (fakta.rincian.nama if fakta.rincian_id else (fakta.wilayah.nama if fakta.wilayah_id else "")).strip()
        if not source_name:
            continue
        jenis = _jenis_wilayah(source_name)
        key = (source_name, jenis)
        wilayah = cache_wilayah.get(key)
        if wilayah is None:
            wilayah, _ = Wilayah.objects.get_or_create(nama=source_name, jenis=jenis, parent=None)
            cache_wilayah[key] = wilayah
        updates = []
        if fakta.wilayah_id != wilayah.id:
            fakta.wilayah = wilayah
            updates.append("wilayah")
        if fakta.rincian_id is not None:
            fakta.rincian = None
            updates.append("rincian")
        if updates:
            fakta.save(update_fields=updates)
            moved += 1
    return moved


def publikasi_create(request):
    form = PublikasiForm(request.POST or None)
    if form.is_valid():
        pub = form.save()
        messages.success(request, "Publikasi dibuat.")
        return redirect("data:publikasi", pk=pub.pk)
    crumb = [{"label": "Data", "url": "/data/"}, {"label": "Publikasi baru", "url": ""}]
    return render(request, "katalog/publikasi_form.html", {"form": form, "breadcrumb": crumb})


def publikasi_edit(request, pk):
    pub = get_object_or_404(Publikasi, pk=pk)
    form = PublikasiForm(request.POST or None, instance=pub)
    if form.is_valid():
        form.save()
        messages.success(request, "Publikasi diperbarui.")
        return redirect("data:publikasi", pk=pub.pk)
    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(pub.tahun_terbit), "url": f"/data/pub/{pub.pk}/"},
        {"label": "Edit", "url": ""},
    ]
    return render(request, "katalog/publikasi_form.html",
                  {"form": form, "edit": True, "obj": pub, "breadcrumb": crumb})


def publikasi_delete(request, pk):
    pub = get_object_or_404(Publikasi, pk=pk)
    if request.method == "POST":
        pub.delete()
        messages.success(request, "Publikasi dihapus beserta seluruh bab & tabelnya.")
        return redirect("data:home")
    return render(request, "katalog/konfirmasi_hapus.html", {
        "objek": pub, "judul": "Hapus Publikasi",
        "pesan": f"Menghapus '{pub.judul}' ({pub.tahun_terbit}) akan menghapus semua bab, tabel, dan data di dalamnya.",
        "batal_url": f"/data/pub/{pub.pk}/",
    })


def bab_create(request, pub_pk):
    pub = get_object_or_404(Publikasi, pk=pub_pk)
    form = BabForm(request.POST or None)
    if form.is_valid():
        bab = form.save(commit=False)
        bab.publikasi = pub
        bab.save()
        messages.success(request, "Bab dibuat.")
        return redirect("data:bab", pk=bab.pk)
    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(pub.tahun_terbit), "url": f"/data/pub/{pub.pk}/"},
        {"label": "Bab baru", "url": ""},
    ]
    return render(request, "katalog/bab_form.html", {"form": form, "pub": pub, "breadcrumb": crumb})


def bab_edit(request, pk):
    bab = get_object_or_404(Bab.objects.select_related("publikasi"), pk=pk)
    form = BabForm(request.POST or None, instance=bab)
    if form.is_valid():
        form.save()
        messages.success(request, "Bab diperbarui.")
        return redirect("data:bab", pk=bab.pk)
    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(bab.publikasi.tahun_terbit), "url": f"/data/pub/{bab.publikasi_id}/"},
        {"label": bab.nama, "url": f"/data/bab/{bab.pk}/"},
        {"label": "Edit", "url": ""},
    ]
    return render(request, "katalog/bab_form.html",
                  {"form": form, "pub": bab.publikasi, "edit": True, "breadcrumb": crumb})


def bab_delete(request, pk):
    bab = get_object_or_404(Bab.objects.select_related("publikasi"), pk=pk)
    pub_pk = bab.publikasi_id
    if request.method == "POST":
        bab.delete()
        messages.success(request, "Bab dihapus beserta tabelnya.")
        return redirect("data:publikasi", pk=pub_pk)
    return render(request, "katalog/konfirmasi_hapus.html", {
        "objek": bab, "judul": "Hapus Bab",
        "pesan": f"Menghapus bab '{bab.nama}' akan menghapus semua tabel & data di dalamnya.",
        "batal_url": f"/data/bab/{bab.pk}/",
    })


def tabel_create(request, bab_pk):
    bab = get_object_or_404(Bab.objects.select_related("publikasi"), pk=bab_pk)
    form = TabelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        tabel = form.save(commit=False)
        tabel.bab = bab
        tabel.status_verifikasi = Tabel.Status.DRAFT
        tabel.save()
        # definisi kolom
        n = int(request.POST.get("n_kol") or 0)
        urut = 0
        for i in range(n):
            nama = (request.POST.get(f"kol-{i}-nama") or "").strip()
            if not nama:
                continue
            urut += 1
            satuan = (request.POST.get(f"kol-{i}-satuan") or "").strip()
            tahun = request.POST.get(f"kol-{i}-tahun") or None
            tipe = request.POST.get(f"kol-{i}-tipe") or "numerik"
            ind, _ = Indikator.objects.get_or_create(
                nama=nama, defaults={"satuan": satuan, "tipe_nilai": tipe})
            KolomTabel.objects.create(
                tabel=tabel, urutan=urut, indikator=ind,
                satuan=satuan, tahun=tahun or None, tipe_nilai=tipe)
        messages.success(request, f"Tabel {tabel.nomor_tabel} dibuat. Silakan isi datanya.")
        return redirect("data:tabel_detail", pk=tabel.pk)

    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(bab.publikasi.tahun_terbit), "url": f"/data/pub/{bab.publikasi_id}/"},
        {"label": bab.nama, "url": f"/data/bab/{bab.pk}/"},
        {"label": "Tabel baru", "url": ""},
    ]
    return render(request, "katalog/tabel_form.html",
                  {"form": form, "bab": bab, "breadcrumb": crumb})


def tabel_edit(request, pk):
    tabel = get_object_or_404(Tabel.objects.select_related("bab__publikasi"), pk=pk)
    koloms = list(tabel.kolom_set.select_related("indikator").order_by("urutan"))
    old_tipe_baris = tabel.tipe_baris
    form = TabelForm(request.POST or None, instance=tabel)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            tabel = form.save()
            needs_dimension_sync = old_tipe_baris != tabel.tipe_baris
            if not needs_dimension_sync and tabel.tipe_baris == Tabel.TipeBaris.KATEGORI:
                needs_dimension_sync = Fakta.objects.filter(tabel=tabel, rincian__isnull=True, wilayah__isnull=False).exists()
            if not needs_dimension_sync and tabel.tipe_baris != Tabel.TipeBaris.KATEGORI:
                needs_dimension_sync = Fakta.objects.filter(tabel=tabel, wilayah__isnull=True, rincian__isnull=False).exists()
            moved_rows = _migrate_row_dimension_to_match_tipe(tabel, old_tipe_baris) if needs_dimension_sync else 0
            # update definisi kolom yang sudah ada
            for k in koloms:
                nama = (request.POST.get(f"kolom-{k.id}-nama") or "").strip()
                satuan = (request.POST.get(f"kolom-{k.id}-satuan") or "").strip()
                tahun_str = request.POST.get(f"kolom-{k.id}-tahun")
                tahun = None
                if tahun_str:
                    m = re.search(r"\d{4}", tahun_str.strip())
                    if m: tahun = int(m.group(0))
                tipe = request.POST.get(f"kolom-{k.id}-tipe") or k.tipe_nilai
                if nama and nama != k.indikator.nama:
                    ind, _ = Indikator.objects.get_or_create(
                        nama=nama, defaults={"satuan": satuan, "tipe_nilai": tipe})
                    k.indikator = ind
                k.satuan = satuan
                k.tahun = tahun or None
                k.tipe_nilai = tipe
                k.save()
        if moved_rows:
            messages.success(request, f"Tabel & kolom diperbarui. {moved_rows} baris data disesuaikan ke tipe baris baru.")
        else:
            messages.success(request, "Tabel & kolom diperbarui.")
        cache.clear()
        return redirect("data:tabel_detail", pk=tabel.pk)
    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": tabel.nama_tampil, "url": f"/data/tabel/{tabel.pk}/"},
        {"label": "Edit", "url": ""},
    ]
    return render(request, "katalog/tabel_form.html",
                  {"form": form, "bab": tabel.bab, "edit": True, "tabel": tabel,
                   "koloms": koloms, "breadcrumb": crumb})


def tabel_delete(request, pk):
    tabel = get_object_or_404(Tabel.objects.select_related("bab"), pk=pk)
    bab_pk = tabel.bab_id
    if request.method == "POST":
        tabel.delete()
        cache.clear()
        messages.success(request, "Tabel dihapus.")
        return redirect("data:bab", pk=bab_pk)
    return render(request, "katalog/konfirmasi_hapus.html", {
        "objek": tabel, "judul": "Hapus Tabel",
        "pesan": f"Menghapus tabel {tabel.nomor_tabel} akan menghapus seluruh datanya.",
        "batal_url": f"/data/tabel/{tabel.pk}/",
    })

def api_search_indicator(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    
    # Cari indikator yang mengandung teks pencarian (case-insensitive)
    results = list(Indikator.objects.filter(nama__icontains=q).order_by('nama')[:15].values_list('nama', flat=True))
    return JsonResponse({'results': results})

def api_suggest_indicator(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            judul_tabel = data.get('judul', '').strip()
            nama_kolom = data.get('nama_kolom', '').strip()
            
            if not judul_tabel:
                return JsonResponse({'error': 'Judul tabel tidak boleh kosong.'}, status=400)
                
            api_key = getattr(settings, 'GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY'))
            if not api_key:
                return JsonResponse({'error': 'API Key Gemini belum diatur.'}, status=500)
                
            client = genai.Client(api_key=api_key)
            model_name = getattr(settings, 'GEMINI_MODEL', os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash'))
            
            konteks_kolom = f'\nNama Kolom Asli/Saat ini: "{nama_kolom}"' if nama_kolom else ""
            
            prompt = f"""Anda adalah ahli data statistik BPS.
Diberikan informasi tentang sebuah tabel publikasi:
Judul Tabel: "{judul_tabel}"{konteks_kolom}

Tugas: Berikan 1 nama INDIKATOR STATISTIK (Measure/Variabel) yang paling tepat untuk kolom tersebut.
Berdasarkan konteks judul tabel, perbaiki atau standarisasi nama kolom tersebut agar menjadi indikator yang utuh dan baku.

ATURAN KETAT:
1. JANGAN sertakan elemen waktu (tahun, bulan).
2. JANGAN sertakan elemen wilayah (Kabupaten, Provinsi).
3. JANGAN sertakan elemen sumber data.
4. JANGAN gunakan kalimat penjelasan, HANYA teks nama indikatornya.
5. Maksimal 7 kata.

Contoh Kasus 1:
Judul Tabel: "Jumlah Pegawai Negeri Sipil Menurut Tingkat Kepangkatan dan Jenis Kelamin Tahun 2025"
Nama Kolom Asli: "Laki-laki"
Hasil: Anggota PNS - Laki-laki

Contoh Kasus 2:
Judul Tabel: "Produksi Buah-Buahan dan Sayuran Tahunan di Kabupaten Tasikmalaya (kuintal), 2024-2025"
Nama Kolom Asli: "Produksi Buah"
Hasil: Produksi Buah-Buahan dan Sayuran

Berikan Hasil:"""
            
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            
            suggestion = response.text.strip()
            # Bersihkan tanda kutip jika Gemini menambahkannya
            suggestion = suggestion.strip('"').strip("'")
            
            return JsonResponse({'suggestion': suggestion})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Hanya menerima POST request.'}, status=405)
