from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.postgres.search import TrigramSimilarity
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from apps.katalog.models import Tabel
from apps.referensi.models import Indikator, Wilayah
from apps.data.models import CanonicalIndicator, Fakta
from apps.data.timeseries import get_canonical_time_series
from apps.data.utils import normalize_text
from .serializers import TabelSerializer, IndikatorSerializer, FaktaTimeSeriesSerializer


def _detect_wilayah(query):
    """Return a wilayah mentioned in the free-text query, e.g. 'penduduk cisayong'."""
    query_norm = f" {normalize_text(query)} "
    candidates = Wilayah.objects.only('id', 'nama', 'jenis').order_by('-nama')
    for wilayah in candidates:
        name_norm = normalize_text(wilayah.nama)
        if name_norm and f" {name_norm} " in query_norm:
            return wilayah
    return None


def _query_without_wilayah(query, wilayah):
    if not wilayah:
        return query
    terms = normalize_text(wilayah.nama).split()
    remaining = [token for token in normalize_text(query).split() if token not in terms]
    return " ".join(remaining).strip() or query


def _merge_by_id(primary, extra):
    seen = set()
    merged = []
    for item in list(primary) + list(extra):
        if item.id not in seen:
            seen.add(item.id)
            merged.append(item)
    return merged


def _quick_wilayah_matches(query, wilayah, limit=12):
    """Small answer card for queries like 'penduduk cisayong'."""
    if not wilayah:
        return []

    cleaned_query = _query_without_wilayah(query, wilayah)
    terms = [term for term in normalize_text(cleaned_query).split() if len(term) >= 3]
    if not terms:
        return []

    qs = (
        Fakta.objects.filter(wilayah=wilayah, nilai_num__isnull=False)
        .select_related('kolom__indikator', 'tabel', 'wilayah')
    )
    for term in terms:
        qs = qs.filter(kolom__indikator__nama__icontains=term)

    # For user intent like 'penduduk cisayong', the 'Menurut Kecamatan' series
    # is the clearest result. Prefer it above generic labels such as '[Penduduk] Jumlah'.
    rows = list(qs.order_by('kolom__indikator__nama', 'tahun', 'id')[:300])
    if not rows:
        return []

    grouped = {}
    for fakta in rows:
        indicator = fakta.kolom.indikator
        grouped.setdefault(indicator.id, {"indicator": indicator, "rows": []})["rows"].append(fakta)

    wants_male = "laki" in terms
    wants_female = "perempuan" in terms
    wants_total_population = "penduduk" in terms and not wants_male and not wants_female

    def merged_rows_for_indicator(*, include_text: str | None = None, exclude_sex: bool = False):
        qs = (
            Fakta.objects.filter(wilayah=wilayah, nilai_num__isnull=False, tabel__nomor_tabel="3.1.1")
            .filter(kolom__indikator__nama__icontains="Penduduk")
            .filter(tabel__judul__icontains="Kecamatan")
            .exclude(kolom__indikator__nama__icontains="Miskin")
            .exclude(tabel__judul__icontains="Agama")
            .select_related('kolom__indikator', 'tabel', 'wilayah')
            .order_by('tahun', 'id')
        )
        if include_text:
            qs = qs.filter(kolom__indikator__nama__icontains=include_text)
        else:
            qs = qs.filter(kolom__indikator__nama__icontains="Jumlah")
        if exclude_sex:
            qs = qs.exclude(kolom__indikator__nama__icontains="Laki").exclude(kolom__indikator__nama__icontains="Perempuan")

        rows_by_year = {}
        for fakta in qs:
            year = fakta.tahun_lengkap
            if year is None:
                continue
            current = rows_by_year.get(year)
            if current is None or fakta.tabel_id > current.tabel_id:
                rows_by_year[year] = fakta
        return [rows_by_year[year] for year in sorted(rows_by_year)]

    # Natural query handling:
    # - "jumlah penduduk <wilayah>" -> merged total series across legacy labels.
    # - "jumlah penduduk <wilayah> laki laki" -> merged male series, not total.
    # - "jumlah penduduk <wilayah> perempuan" -> merged female series, not total.
    if wants_male or wants_female or wants_total_population:
        if wants_male:
            merged_rows = merged_rows_for_indicator(include_text="Laki")
            preferred_name = "Jumlah Penduduk Laki-laki Menurut Kecamatan"
        elif wants_female:
            merged_rows = merged_rows_for_indicator(include_text="Perempuan")
            preferred_name = "Jumlah Penduduk Perempuan Menurut Kecamatan"
        else:
            merged_rows = merged_rows_for_indicator(exclude_sex=True)
            preferred_name = "Jumlah Penduduk Menurut Kecamatan"

        if merged_rows:
            primary_indicator = next(
                (fakta.kolom.indikator for fakta in merged_rows if fakta.kolom.indikator.nama == preferred_name),
                merged_rows[0].kolom.indikator,
            )
            grouped[primary_indicator.id] = {"indicator": primary_indicator, "rows": merged_rows}

    def score(group):
        name = normalize_text(group["indicator"].nama)
        points = 0
        if "jumlah penduduk" in name:
            points += 20
        if "menurut kecamatan" in name:
            points += 10
        if name.startswith("penduduk") or name.startswith("jumlah"):
            points += 4
        points += min(len(group["rows"]), 10)
        return -points, name

    best = sorted(grouped.values(), key=score)[:3]
    payload = []
    for group in best:
        observations = []
        for fakta in sorted(group["rows"], key=lambda f: (f.tahun_lengkap or 0, f.id))[:limit]:
            observations.append({
                "id": fakta.id,
                "tahun": fakta.tahun_lengkap,
                "nilai": float(fakta.nilai_num),
                "nilai_teks": fakta.nilai_teks,
                "wilayah_nama": wilayah.nama,
                "satuan": getattr(fakta.kolom, 'satuan', '') or getattr(group["indicator"], 'satuan', '') or '',
                "tabel": {
                    "id": fakta.tabel_id,
                    "nomor_tabel": fakta.tabel.nomor_tabel,
                    "judul": fakta.tabel.judul,
                },
            })
        payload.append({
            "indicator_id": group["indicator"].id,
            "indicator_name": group["indicator"].nama,
            "wilayah": {"id": wilayah.id, "nama": wilayah.nama, "jenis": wilayah.jenis},
            "observations": observations,
        })
    return payload

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

        detected_wilayah = _detect_wilayah(query)
        search_query = _query_without_wilayah(query, detected_wilayah)
        quick_matches = _quick_wilayah_matches(query, detected_wilayah)

        if connection.vendor == 'postgresql':
            tabel_qs = Tabel.objects.annotate(
                similarity=TrigramSimilarity('judul', search_query) + TrigramSimilarity('nama_ringkas', search_query)
            ).filter(similarity__gt=0.1).order_by('-similarity')[:10]

            indikator_qs = Indikator.objects.annotate(
                similarity=TrigramSimilarity('nama', search_query)
            ).filter(similarity__gt=0.1, kolom_set__isnull=False).distinct().order_by('-similarity')[:15]
        else:
            # Fallback untuk SQLite (Dev)
            tabel_qs = Tabel.objects.filter(
                Q(judul__icontains=search_query) | Q(nama_ringkas__icontains=search_query)
            )[:10]

            indikator_qs = Indikator.objects.filter(
                nama__icontains=search_query, kolom_set__isnull=False
            ).distinct()[:15]

        if detected_wilayah:
            wilayah_indicator_ids = [item["indicator_id"] for item in quick_matches]
            indicator_by_id = Indikator.objects.in_bulk(wilayah_indicator_ids)
            extra_indikator_qs = [indicator_by_id[indicator_id] for indicator_id in wilayah_indicator_ids if indicator_id in indicator_by_id]
            indikator_qs = _merge_by_id(extra_indikator_qs, indikator_qs)[:15]

        return Response({
            "tabel": TabelSerializer(tabel_qs, many=True).data,
            "indikator": IndikatorSerializer(indikator_qs, many=True).data,
            "detected_wilayah": {
                "id": detected_wilayah.id,
                "nama": detected_wilayah.nama,
                "jenis": detected_wilayah.jenis,
            } if detected_wilayah else None,
            "interpreted_query": search_query,
            "quick_matches": quick_matches,
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
