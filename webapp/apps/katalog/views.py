from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.referensi.models import Indikator
from .forms import BabForm, PublikasiForm, TabelForm
from .models import Bab, KolomTabel, Publikasi, Tabel


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
        return redirect("data:tabel_isi", pk=tabel.pk)

    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": str(bab.publikasi.tahun_terbit), "url": f"/data/pub/{bab.publikasi_id}/"},
        {"label": bab.nama, "url": f"/data/bab/{bab.pk}/"},
        {"label": "Tabel baru", "url": ""},
    ]
    indikator_ada = list(Indikator.objects.order_by("nama").values_list("nama", flat=True))
    return render(request, "katalog/tabel_form.html",
                  {"form": form, "bab": bab, "indikator_ada": indikator_ada, "breadcrumb": crumb})


def tabel_edit(request, pk):
    tabel = get_object_or_404(Tabel.objects.select_related("bab__publikasi"), pk=pk)
    koloms = list(tabel.kolom_set.select_related("indikator").order_by("urutan"))
    form = TabelForm(request.POST or None, instance=tabel)
    if request.method == "POST" and form.is_valid():
        form.save()
        # update definisi kolom yang sudah ada
        for k in koloms:
            nama = (request.POST.get(f"kolom-{k.id}-nama") or "").strip()
            satuan = (request.POST.get(f"kolom-{k.id}-satuan") or "").strip()
            tahun = request.POST.get(f"kolom-{k.id}-tahun") or None
            tipe = request.POST.get(f"kolom-{k.id}-tipe") or k.tipe_nilai
            if nama and nama != k.indikator.nama:
                ind, _ = Indikator.objects.get_or_create(
                    nama=nama, defaults={"satuan": satuan, "tipe_nilai": tipe})
                k.indikator = ind
            k.satuan = satuan
            k.tahun = tahun or None
            k.tipe_nilai = tipe
            k.save()
        messages.success(request, "Tabel & kolom diperbarui.")
        return redirect("data:tabel_detail", pk=tabel.pk)
    crumb = [
        {"label": "Data", "url": "/data/"},
        {"label": tabel.nama_tampil, "url": f"/data/tabel/{tabel.pk}/"},
        {"label": "Edit", "url": ""},
    ]
    return render(request, "katalog/tabel_form.html",
                  {"form": form, "bab": tabel.bab, "edit": True,
                   "koloms": koloms, "breadcrumb": crumb})


def tabel_delete(request, pk):
    tabel = get_object_or_404(Tabel.objects.select_related("bab"), pk=pk)
    bab_pk = tabel.bab_id
    if request.method == "POST":
        tabel.delete()
        messages.success(request, "Tabel dihapus.")
        return redirect("data:bab", pk=bab_pk)
    return render(request, "katalog/konfirmasi_hapus.html", {
        "objek": tabel, "judul": "Hapus Tabel",
        "pesan": f"Menghapus tabel {tabel.nomor_tabel} akan menghapus seluruh datanya.",
        "batal_url": f"/data/tabel/{tabel.pk}/",
    })
