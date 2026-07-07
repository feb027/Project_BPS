from decimal import Decimal

from django.db import connection
from django.db.models import Q
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


def _detect_wilayahs(query):
    """Return all wilayah mentioned in a free-text query, preserving query order."""
    query_norm = f" {normalize_text(query)} "
    matches = []
    candidates = Wilayah.objects.only('id', 'nama', 'jenis').order_by('-nama')
    for wilayah in candidates:
        name_norm = normalize_text(wilayah.nama)
        token = f" {name_norm} "
        if name_norm and token in query_norm:
            matches.append((query_norm.index(token), wilayah))
    return [wilayah for _, wilayah in sorted(matches, key=lambda item: item[0])]


def _detect_wilayah(query):
    """Return the first wilayah mentioned in the free-text query."""
    wilayahs = _detect_wilayahs(query)
    return wilayahs[0] if wilayahs else None


def _query_without_wilayahs(query, wilayahs):
    if not wilayahs:
        return query
    wilayah_terms = set()
    for wilayah in wilayahs:
        wilayah_terms.update(normalize_text(wilayah.nama).split())
    remaining = [token for token in normalize_text(query).split() if token not in wilayah_terms]
    return " ".join(remaining).strip() or query


def _query_without_wilayah(query, wilayah):
    return _query_without_wilayahs(query, [wilayah] if wilayah else [])


def _merge_by_id(primary, extra):
    seen = set()
    merged = []
    for item in list(primary) + list(extra):
        if item.id not in seen:
            seen.add(item.id)
            merged.append(item)
    return merged


SHORT_INTENT_TERMS = {"ra", "tk", "sd", "mi", "ma"}
QUERY_STOPWORDS = {"di", "ke", "dan", "yang", "untuk", "dari"}


def _query_terms(query):
    tokens = normalize_text(query).split()
    return [
        token for token in tokens
        if token not in QUERY_STOPWORDS and (len(token) >= 3 or token in SHORT_INTENT_TERMS)
    ]


def _wilayah_payload(groups, wilayah, limit=12):
    payload = []
    for group in groups:
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
            "indicator_name": group.get("display_name") or group["indicator"].nama,
            "wilayah": {"id": wilayah.id, "nama": wilayah.nama, "jenis": wilayah.jenis},
            "observations": observations,
        })
    return payload


def _quick_topic_matches(query, limit=12):
    """Small answer card for topic-only queries like 'produksi alpukat'."""
    terms = [term for term in normalize_text(query).split() if len(term) >= 3]
    if not terms:
        return []

    qs = (
        Fakta.objects.filter(nilai_num__isnull=False)
        .select_related('kolom__indikator', 'tabel', 'tabel__bab__publikasi', 'wilayah', 'rincian')
    )
    for term in terms:
        qs = qs.filter(
            Q(kolom__indikator__nama__icontains=term)
            | Q(tabel__judul__icontains=term)
            | Q(rincian__nama__icontains=term)
            | Q(wilayah__nama__icontains=term)
        )

    rows = list(qs.order_by('kolom__indikator__nama', 'tabel__bab__publikasi__tahun_terbit', 'tahun', 'id')[:6000])
    if "produksi" in terms:
        rows = [fakta for fakta in rows if "produktivit" not in normalize_text(fakta.tabel.judul)]
    if not rows:
        return []

    grouped = {}
    for fakta in rows:
        indicator = fakta.kolom.indikator
        grouped.setdefault(indicator.id, {"indicator": indicator, "rows": []})["rows"].append(fakta)

    query_norm = normalize_text(query)

    def score(group):
        indicator_name = normalize_text(group["indicator"].nama)
        titles = " ".join(normalize_text(f.tabel.judul) for f in group["rows"][:20])
        subjects = " ".join(
            normalize_text(getattr(f.wilayah, 'nama', '') or getattr(f.rincian, 'nama', ''))
            for f in group["rows"][:80]
        )
        haystack = f"{indicator_name} {titles} {subjects}"
        points = 0
        if indicator_name == query_norm:
            points += 120
        if all(term in indicator_name for term in terms):
            points += 80
        if all(term in haystack for term in terms):
            points += 30
        if any(term in indicator_name for term in terms):
            points += 10
        years = {f.tahun_lengkap for f in group["rows"] if f.tahun_lengkap is not None}
        points += min(len(years), 12)
        # Penalize very generic indicators when a more specific indicator exists.
        if len(indicator_name.split()) <= 1:
            points -= 25
        return -points, indicator_name

    best = sorted(grouped.values(), key=score)[:3]
    payload = []
    for group in best:
        table_rows_by_year = {}
        for fakta in group["rows"]:
            year = fakta.tahun_lengkap
            if year is None:
                continue
            table_rows_by_year.setdefault(year, {}).setdefault(fakta.tabel_id, []).append(fakta)

        rows_by_year = {}
        for year, by_table in table_rows_by_year.items():
            ranked_tables = []
            for table_id, table_rows in by_table.items():
                sample = table_rows[0]
                pub_year = sample.tabel.bab.publikasi.tahun_terbit if sample.tabel and sample.tabel.bab_id else 0
                subjects = {
                    getattr(f.wilayah, 'nama', None) or getattr(f.rincian, 'nama', None) or 'Kabupaten Tasikmalaya'
                    for f in table_rows
                }
                subject_count = len(subjects)
                row_count = len(table_rows)
                reasonable = row_count <= max(subject_count * 2, 80)
                ranked_tables.append((reasonable, -abs(row_count - subject_count), pub_year, table_id, table_rows))
            best_reasonable, _, _, best_table_id, best_rows = max(ranked_tables, key=lambda item: item[:4])
            if not best_reasonable:
                # Better to omit a suspicious year than present an inflated aggregate.
                continue
            rows_by_year[year] = {"table_id": best_table_id, "rows": best_rows}

        observations = []
        for year in sorted(rows_by_year)[:limit]:
            year_rows = rows_by_year[year]["rows"]
            if not year_rows:
                continue
            total = sum((f.nilai_num for f in year_rows if f.nilai_num is not None), Decimal('0'))
            sample = year_rows[0]
            observations.append({
                "id": sample.id,
                "tahun": year,
                "nilai": float(total),
                "nilai_teks": str(total.normalize()) if hasattr(total, 'normalize') else str(total),
                "wilayah_nama": "Kabupaten Tasikmalaya",
                "satuan": getattr(sample.kolom, 'satuan', '') or getattr(group["indicator"], 'satuan', '') or '',
                "tabel": {
                    "id": sample.tabel_id,
                    "nomor_tabel": sample.tabel.nomor_tabel,
                    "judul": sample.tabel.judul,
                },
            })
        if observations:
            payload.append({
                "indicator_id": group["indicator"].id,
                "indicator_name": f"Total {group['indicator'].nama}",
                "subject_name": "Kabupaten Tasikmalaya",
                "summary_kind": "aggregate",
                "observations": observations,
            })
    return payload


def _quick_wilayah_matches(query, wilayah, limit=12):
    """Small answer card for queries like 'penduduk cisayong'."""
    if not wilayah:
        return []

    cleaned_query = _query_without_wilayah(query, wilayah)
    terms = _query_terms(cleaned_query)
    if not terms:
        return []

    wants_ra_school = "ra" in terms and "sekolah" in terms
    if wants_ra_school:
        ra_qs = (
            Fakta.objects.filter(wilayah=wilayah, nilai_num__isnull=False)
            .filter(tabel__judul__icontains="Raudatul Athfal")
            .filter(kolom__indikator__nama__icontains="Sekolah")
            .select_related('kolom__indikator', 'tabel', 'tabel__bab__publikasi', 'wilayah')
            .order_by('tabel__bab__publikasi__tahun_terbit', 'tahun', 'id')
        )
        rows_by_year = {}
        for fakta in ra_qs:
            year = fakta.tahun_lengkap
            if year is None:
                continue
            current = rows_by_year.get(year)
            current_pub_year = current.tabel.bab.publikasi.tahun_terbit if current else -1
            fakta_pub_year = fakta.tabel.bab.publikasi.tahun_terbit
            if current is None or fakta_pub_year > current_pub_year:
                rows_by_year[year] = fakta
        ra_rows = [rows_by_year[year] for year in sorted(rows_by_year)]
        if ra_rows:
            return _wilayah_payload([{
                "indicator": ra_rows[0].kolom.indikator,
                "display_name": "Jumlah Sekolah Raudatul Athfal (RA)",
                "rows": ra_rows,
            }], wilayah, limit)

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
    return _wilayah_payload(best, wilayah, limit)

class FacetedSearchAPIView(APIView):
    """
    API untuk mencari Tabel dan Indikator.
    Menggunakan Trigram Similarity untuk PostgreSQL, dan fallback ke icontains untuk SQLite.
    """
    def get(self, request):
        query = request.GET.get('q', '').strip()
        if len(query) < 2:
            return Response({"tabel": [], "indikator": []})

        detected_wilayahs = _detect_wilayahs(query)
        detected_wilayah = detected_wilayahs[0] if detected_wilayahs else None
        search_query = _query_without_wilayahs(query, detected_wilayahs)
        quick_matches = (
            _quick_wilayah_matches(search_query, detected_wilayah)
            if detected_wilayah
            else _quick_topic_matches(search_query)
        )

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
            "detected_wilayahs": [
                {"id": wilayah.id, "nama": wilayah.nama, "jenis": wilayah.jenis}
                for wilayah in detected_wilayahs
            ],
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
