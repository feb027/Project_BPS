import json
from django.db.models import Count, Q
from django.shortcuts import render

from apps.data.models import Fakta
from apps.katalog.models import Publikasi, Tabel, Bab

def dashboard(request):
    """Halaman ringkas: status data & pintasan."""
    
    # 1. Anomali & Peringatan
    anomali_list = Fakta.objects.filter(
        flag__in=[Fakta.Flag.PERLU_CEK, Fakta.Flag.NIHIL, Fakta.Flag.TIDAK_TERSEDIA]
    ).select_related('tabel__bab__publikasi', 'wilayah', 'rincian', 'kolom__indikator').order_by('-dibuat_pada')[:8]

    # 2. Live Feed
    live_feed = Tabel.objects.exclude(status_verifikasi=Tabel.Status.DRAFT).select_related('bab__publikasi').order_by('-diubah_pada')[:5]

    # 3. Visualisasi Distribusi Bab
    distribusi_bab = list(Fakta.objects.values('tabel__bab__nama').annotate(jumlah=Count('id')).order_by('-jumlah')[:10])
    chart_data = json.dumps({
        "labels": [d["tabel__bab__nama"] or "Lainnya" for d in distribusi_bab],
        "data": [d["jumlah"] for d in distribusi_bab]
    })

    ctx = {
        "jml_publikasi": Publikasi.objects.count(),
        "jml_tabel": Tabel.objects.count(),
        "jml_fakta": Fakta.objects.count(),
        "jml_perlu_cek": Fakta.objects.filter(flag=Fakta.Flag.PERLU_CEK).count(),
        "anomali_list": anomali_list,
        "live_feed": live_feed,
        "chart_data": chart_data,
    }
    return render(request, "core/dashboard.html", ctx)
