from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.postgres.search import TrigramSimilarity
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from apps.katalog.models import Tabel
from apps.referensi.models import Indikator
from apps.data.models import CanonicalIndicator, Fakta
from apps.data.timeseries import get_canonical_time_series
from .serializers import TabelSerializer, IndikatorSerializer, FaktaTimeSeriesSerializer

from django.db import connection
from django.db.models import Q

class FacetedSearchAPIView(APIView):
    """
    API untuk mencari Tabel dan Indikator.
    Menggunakan Trigram Similarity untuk PostgreSQL, dan fallback ke icontains untuk SQLite.
    """
    def get(self, request):
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return Response({"tabel": [], "indikator": []})

        if connection.vendor == 'postgresql':
            tabel_qs = Tabel.objects.annotate(
                similarity=TrigramSimilarity('judul', query) + TrigramSimilarity('nama_ringkas', query)
            ).filter(similarity__gt=0.1).order_by('-similarity')[:10]

            indikator_qs = Indikator.objects.annotate(
                similarity=TrigramSimilarity('nama', query)
            ).filter(similarity__gt=0.1, kolom_set__isnull=False).distinct().order_by('-similarity')[:15]
        else:
            # Fallback untuk SQLite (Dev)
            tabel_qs = Tabel.objects.filter(
                Q(judul__icontains=query) | Q(nama_ringkas__icontains=query)
            )[:10]

            indikator_qs = Indikator.objects.filter(
                nama__icontains=query, kolom_set__isnull=False
            ).distinct()[:15]

        return Response({
            "tabel": TabelSerializer(tabel_qs, many=True).data,
            "indikator": IndikatorSerializer(indikator_qs, many=True).data
        })

class TimeSeriesAPIView(APIView):
    """
    API untuk data Fakta (time-series) berdasarkan Indikator atau Tabel.
    """
    @method_decorator(cache_page(60 * 15)) # 15 menit cache
    def get(self, request):
        indikator_id = request.GET.get('indikator_id')
        tabel_id = request.GET.get('tabel_id')

        if not indikator_id and not tabel_id:
            return Response({"error": "indikator_id atau tabel_id harus disertakan"}, status=400)

        # Anti N+1: Memuat relasi wilayah dan rincian sekaligus
        qs = Fakta.objects.select_related('wilayah', 'rincian')

        if indikator_id:
            qs = qs.filter(kolom__indikator_id=indikator_id)
        if tabel_id:
            qs = qs.filter(tabel_id=tabel_id)

        qs = qs.exclude(nilai_num__isnull=True).order_by('tahun')

        serializer = FaktaTimeSeriesSerializer(qs, many=True)
        return Response(serializer.data)


class CanonicalTimeSeriesAPIView(APIView):
    """
    API time-series harmonized by CanonicalIndicator aliases.

    Accepts either `indicator_code` (preferred) or `canonical_indicator_id`.
    """
    @method_decorator(cache_page(60 * 15))
    def get(self, request):
        indicator_code = request.GET.get('indicator_code') or request.GET.get('code')
        canonical_indicator_id = request.GET.get('canonical_indicator_id')
        wilayah_id = request.GET.get('wilayah_id')
        start_year = request.GET.get('start_year')
        end_year = request.GET.get('end_year')
        limit = request.GET.get('limit')

        if not indicator_code and not canonical_indicator_id:
            return Response({"error": "indicator_code atau canonical_indicator_id harus disertakan"}, status=400)

        try:
            payload = get_canonical_time_series(
                indicator_code=indicator_code,
                canonical_indicator_id=int(canonical_indicator_id) if canonical_indicator_id else None,
                wilayah_id=int(wilayah_id) if wilayah_id else None,
                start_year=int(start_year) if start_year else None,
                end_year=int(end_year) if end_year else None,
                limit=min(int(limit), 20000) if limit else 5000,
            )
        except CanonicalIndicator.DoesNotExist:
            return Response({"error": "Canonical indicator tidak ditemukan"}, status=404)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        return Response(payload)
