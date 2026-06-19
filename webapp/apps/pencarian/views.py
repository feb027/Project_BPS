from django.shortcuts import render

from apps.data.models import Fakta


def cari(request):
    """Pencarian sederhana (F4 akan diperkaya: filter wilayah/indikator/tahun)."""
    q = (request.GET.get("q") or "").strip()
    hasil = []
    if q:
        hasil = (
            Fakta.objects.select_related("tabel", "wilayah", "rincian")
            .filter(nilai_teks__icontains=q)[:100]
        )
    return render(request, "pencarian/cari.html", {"q": q, "hasil": hasil})
