import json
from collections import defaultdict

from django.db.models import Count
from django.shortcuts import render
from django.core.cache import cache

from apps.data.models import Fakta
from apps.katalog.models import Publikasi, Tabel, Bab


def _chart_distribusi():
    """Distribusi jumlah fakta per bab, dikelompokkan per publikasi.

    Group by bab_id (bukan nama) karena nama bab bisa sama di banyak
    publikasi — label dibuat unik: "Bab {nomor} · {nama}".
    """
    publikasis = list(Publikasi.objects.order_by("-tahun_terbit"))
    rows = (
        Fakta.objects.values(
            "tabel__bab_id",
            "tabel__bab__nomor",
            "tabel__bab__nama",
            "tabel__bab__publikasi_id",
        )
        .annotate(jumlah=Count("id"))
        .order_by("tabel__bab__publikasi__tahun_terbit", "tabel__bab__nomor")
    )
    by_pub = defaultdict(list)
    for r in rows:
        by_pub[r["tabel__bab__publikasi_id"]].append(r)

    data = []
    for p in publikasis:
        babs = by_pub.get(p.id, [])
        data.append(
            {
                "tahun": p.tahun_terbit,
                "judul": p.judul,
                "total": sum(b["jumlah"] for b in babs),
                "bab": [
                    {
                        "nomor": b["tabel__bab__nomor"],
                        "nama": b["tabel__bab__nama"],
                        "jumlah": b["jumlah"],
                    }
                    for b in babs
                ],
            }
        )
    return {
        "publikasi": data,
        "default_tahun": publikasis[0].tahun_terbit if publikasis else None,
    }


def dashboard(request):
    """Halaman ringkas: status data & pintasan."""

    # 1. Anomali & Peringatan (Realtime)
    anomali_list = Fakta.objects.filter(
        flag=Fakta.Flag.PERLU_CEK
    ).select_related("tabel__bab__publikasi", "wilayah", "rincian", "kolom__indikator").order_by("-dibuat_pada")[:10]

    # 2. Live Feed (Realtime)
    live_feed = Tabel.objects.exclude(status_verifikasi=Tabel.Status.DRAFT).select_related("bab__publikasi").order_by("-diubah_pada")[:5]

    # 3. Visualisasi Distribusi Bab & Stats (Cached for 1 hour)
    chart = cache.get("dashboard_chart_v2")
    if not chart:
        chart = _chart_distribusi()
        cache.set("dashboard_chart_v2", chart, 3600)

    jml_publikasi = cache.get("dashboard_jml_publikasi")
    if jml_publikasi is None:
        jml_publikasi = Publikasi.objects.count()
        cache.set("dashboard_jml_publikasi", jml_publikasi, 3600)

    jml_tabel = cache.get("dashboard_jml_tabel")
    if jml_tabel is None:
        jml_tabel = Tabel.objects.count()
        cache.set("dashboard_jml_tabel", jml_tabel, 3600)

    jml_fakta = cache.get("dashboard_jml_fakta")
    if jml_fakta is None:
        jml_fakta = Fakta.objects.count()
        cache.set("dashboard_jml_fakta", jml_fakta, 3600)

    jml_perlu_cek = cache.get("dashboard_jml_perlu_cek")
    if jml_perlu_cek is None:
        jml_perlu_cek = Fakta.objects.filter(flag=Fakta.Flag.PERLU_CEK).count()
        cache.set("dashboard_jml_perlu_cek", jml_perlu_cek, 60)

    ctx = {
        "jml_publikasi": jml_publikasi,
        "jml_tabel": jml_tabel,
        "jml_fakta": jml_fakta,
        "jml_perlu_cek": jml_perlu_cek,
        "anomali_list": anomali_list,
        "live_feed": live_feed,
        "chart_data": json.dumps(chart),
    }
    return render(request, "core/dashboard.html", ctx)
