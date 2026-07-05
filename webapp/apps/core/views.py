import json
from django.db.models import Count, Q
from django.shortcuts import render
from django.core.cache import cache

from apps.data.models import Fakta
from apps.katalog.models import Publikasi, Tabel, Bab

def dashboard(request):
    """Halaman ringkas: status data & pintasan."""
    
    # 1. Anomali & Peringatan (Realtime)
    anomali_list = Fakta.objects.filter(
        flag=Fakta.Flag.PERLU_CEK
    ).select_related('tabel__bab__publikasi', 'wilayah', 'rincian', 'kolom__indikator').order_by('-dibuat_pada')[:10]

    # 2. Live Feed (Realtime)
    live_feed = Tabel.objects.exclude(status_verifikasi=Tabel.Status.DRAFT).select_related('bab__publikasi').order_by('-diubah_pada')[:5]

    # 3. Visualisasi Distribusi Bab & Stats (Cached for 1 hour)
    chart_data = cache.get('dashboard_chart_data')
    if not chart_data:
        distribusi_bab = list(Fakta.objects.values('tabel__bab__nama').annotate(jumlah=Count('id')).order_by('-jumlah')[:10])
        chart_data = json.dumps({
            "labels": [d["tabel__bab__nama"] or "Lainnya" for d in distribusi_bab],
            "data": [d["jumlah"] for d in distribusi_bab]
        })
        cache.set('dashboard_chart_data', chart_data, 3600)

    jml_publikasi = cache.get('dashboard_jml_publikasi')
    if jml_publikasi is None:
        jml_publikasi = Publikasi.objects.count()
        cache.set('dashboard_jml_publikasi', jml_publikasi, 3600)

    jml_tabel = cache.get('dashboard_jml_tabel')
    if jml_tabel is None:
        jml_tabel = Tabel.objects.count()
        cache.set('dashboard_jml_tabel', jml_tabel, 3600)

    jml_fakta = cache.get('dashboard_jml_fakta')
    if jml_fakta is None:
        jml_fakta = Fakta.objects.count()
        cache.set('dashboard_jml_fakta', jml_fakta, 3600)

    ctx = {
        "jml_publikasi": jml_publikasi,
        "jml_tabel": jml_tabel,
        "jml_fakta": jml_fakta,
        "jml_perlu_cek": Fakta.objects.filter(flag=Fakta.Flag.PERLU_CEK).count(),
        "anomali_list": anomali_list,
        "live_feed": live_feed,
        "chart_data": chart_data,
    }
    return render(request, "core/dashboard.html", ctx)
