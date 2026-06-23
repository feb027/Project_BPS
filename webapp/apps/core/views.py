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
    ).select_related('tabel', 'wilayah', 'rincian').order_by('-dibuat_pada')[:8]

    # 2. Progress Publikasi
    pubs = Publikasi.objects.annotate(
        total_tabel=Count('bab_set__tabel_set', distinct=True),
        tabel_selesai=Count('bab_set__tabel_set', filter=Q(bab_set__tabel_set__status_verifikasi__in=[Tabel.Status.EKSTRAK, Tabel.Status.VERIFIKASI]), distinct=True)
    ).order_by("-tahun_terbit")[:5]
    
    for p in pubs:
        p.progress_pct = int((p.tabel_selesai / p.total_tabel * 100)) if p.total_tabel > 0 else 0

    # 3. Live Feed
    live_feed = Tabel.objects.exclude(status_verifikasi=Tabel.Status.DRAFT).select_related('bab__publikasi').order_by('-diubah_pada')[:5]

    # 4. Quick Jump
    quick_jump_bab = None
    latest_pub = pubs[0] if pubs else Publikasi.objects.first()
    if latest_pub:
        quick_jump_bab = Bab.objects.filter(publikasi=latest_pub).annotate(num_tabel=Count('tabel_set')).filter(num_tabel=0).first()

    # 5. Visualisasi Distribusi Bab
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
        "publikasi_terbaru": pubs,
        "anomali_list": anomali_list,
        "live_feed": live_feed,
        "quick_jump_bab": quick_jump_bab,
        "chart_data": chart_data,
        "latest_pub": latest_pub,
    }
    return render(request, "core/dashboard.html", ctx)
