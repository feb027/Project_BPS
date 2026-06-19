from django.db.models import Count
from django.shortcuts import render

from apps.data.models import Fakta
from apps.katalog.models import Publikasi, Tabel


def dashboard(request):
    """Halaman ringkas: status data & pintasan."""
    ctx = {
        "jml_publikasi": Publikasi.objects.count(),
        "jml_tabel": Tabel.objects.count(),
        "jml_fakta": Fakta.objects.count(),
        "jml_perlu_cek": Fakta.objects.filter(flag=Fakta.Flag.PERLU_CEK).count(),
        "publikasi_terbaru": Publikasi.objects.order_by("-tahun_terbit")[:5],
    }
    return render(request, "core/dashboard.html", ctx)
