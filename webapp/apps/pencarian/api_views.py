from copy import deepcopy
from decimal import Decimal
import re

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
    """Return all wilayah mentioned in a free-text query, preserving query order.

    Exact names are preferred. Unique prefixes of at least 4 characters are accepted
    so a still-typing query like "cisayong + ciaw" can already compare Cisayong
    with Ciawi.
    """
    query_norm = f" {normalize_text(query)} "
    query_tokens = normalize_text(query).split()
    matches = []
    candidates = list(Wilayah.objects.only('id', 'nama', 'jenis').order_by('-nama'))

    for wilayah in candidates:
        name_norm = normalize_text(wilayah.nama)
        token = f" {name_norm} "
        if name_norm and token in query_norm:
            matches.append((query_norm.index(token), wilayah))

    matched_ids = {wilayah.id for _, wilayah in matches}
    candidate_names = [(normalize_text(wilayah.nama), wilayah) for wilayah in candidates]
    for token in query_tokens:
        if len(token) < 4:
            continue
        if any(token in normalize_text(wilayah.nama).split() for _, wilayah in matches):
            continue
        prefix_matches = [
            wilayah for name_norm, wilayah in candidate_names
            if wilayah.id not in matched_ids and name_norm.startswith(token)
        ]
        if len(prefix_matches) == 1:
            wilayah = prefix_matches[0]
            matches.append((query_norm.find(token), wilayah))
            matched_ids.add(wilayah.id)

    return [wilayah for _, wilayah in sorted(matches, key=lambda item: item[0])]


def _wilayah_rank(wilayah):
    """Rank a detected wilayah so the most 'authoritative' one wins as the
    primary region. Kabupaten/Kota (regency) outranks kecamatan, and longer
    names outrank short fragments that merely share a token (e.g. a kecamatan
    named 'Hasil Registrasi' must not hijack a query mentioning 'Hasil
    Penjualan')."""
    jenis = (wilayah.jenis or "").lower()
    if jenis in ("kabupaten", "kota", "kota administratif"):
        base = 0
    elif jenis in ("kecamatan",):
        base = 100
    else:
        base = 50
    # Longer names are more specific; subtract length so bigger == higher priority.
    return base * 1000 - len(wilayah.nama)


def _detect_wilayah(query):
    """Return the first wilayah mentioned in the free-text query."""
    wilayahs = _detect_wilayahs(query)
    return wilayahs[0] if wilayahs else None


def _query_without_wilayahs(query, wilayahs):
    if not wilayahs:
        return query
    wilayah_names = [normalize_text(wilayah.nama) for wilayah in wilayahs]
    wilayah_terms = set()
    for name in wilayah_names:
        wilayah_terms.update(name.split())

    remaining = []
    for token in normalize_text(query).split():
        is_exact_wilayah_token = token in wilayah_terms
        is_detected_prefix = len(token) >= 4 and any(name.startswith(token) for name in wilayah_names)
        if not is_exact_wilayah_token and not is_detected_prefix:
            remaining.append(token)
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


# Age signature of a query, e.g. "penduduk umur 15 tahun" -> "berumur 15 tahun".
# Many BPS tables are scoped to an age band (3.2.1 = "Berumur 15 Tahun Keatas",
# 4.1.11 = "Berumur 7-24 Tahun"), so a query that names an age must NOT
# fall back to the all-ages population total. We extract the age phrase and use
# it to (a) drop facts from tables whose title does not mention that age, and
# (b) boost tables that DO mention it.
_AGE_RE = re.compile(r"umur\s+(\d{1,3})\s*(tahun|thn|th)?", re.IGNORECASE)
_AGE_BAND_RE = re.compile(r"umur\s+(\d{1,3})\s*[-–\s]\s*(\d{1,3})\s*tahun", re.IGNORECASE)


def _extract_age_signature(query):
    """Return a normalized age phrase from the query, or '' if none.

    "umur 15 tahun" -> "berumur 15 tahun"
    "usia 7-24 tahun" -> "berumur 7-24 tahun"
    """
    q = normalize_text(query)
    m = _AGE_BAND_RE.search(q)
    if m:
        return f"berumur {m.group(1)}-{m.group(2)} tahun"
    m = _AGE_RE.search(q)
    if m:
        return f"berumur {m.group(1)} tahun"
    return ""


def _title_matches_age(title_norm, age_sig):
    """True if the (already normalized) table title mentions the age signature."""
    if not age_sig:
        return True
    return age_sig in title_norm


SCHOOL_LEVELS = {"SD", "MI", "RA", "TK", "SMP", "MTS", "SMA", "SMK", "MA", "SLB"}


# Indicators whose values are point observations (a level, not a count) and so
# must never be summed across regions. Summing elevations/percentages/indices
# across kecamatan produces a meaningless "Total" (e.g. 39 district elevations
# adding to ~17,000 mdpl). For these we return per-region lines instead.
NON_ADDITIVE_INDICATOR_KEYWORDS = (
    "tinggi wilayah", "ketinggian", "elevasi", "mdpl",
    "jarak",
    "persentase", "presentase", "%",
    "angka partisipasi", "apk", "angka melek huruf", "amh", "aps",
    "rasio", "indeks", "ipm", "gini", "laju pertumbuhan",
    "rata-rata", "rata rata", "kepadatan", "intensitas", "prevalensi",
    "pertumbuhan", "inflasi", "pdrb", "produk domestik",
)


def _is_non_additive(indicator_name):
    name = normalize_text(indicator_name)
    return any(keyword in name for keyword in NON_ADDITIVE_INDICATOR_KEYWORDS)


def _extract_school_level(title):
    """Pull the formal school-level tag (SD/SMP/SMA/TK/SMK/MA/...) from a
    BPS table title such as 'Jumlah Sekolah ... Sekolah Dasar (SD) ...'.

    Returns None for titles without a recognized school level so non-school
    queries (penduduk, luas wilayah, panjang jalan) are unaffected.
    """
    if not title:
        return None
    match = re.search(r"\(([^)]+)\)", title)
    if not match:
        return None
    token = match.group(1).strip().upper().split()[0]
    return token if token in SCHOOL_LEVELS else None


def _wilayah_payload(groups, wilayah, limit=12):
    payload = []
    for group in groups:
        # Cap by number of years (keep every row within the selected years)
        # instead of a raw row limit, otherwise indicators with several
        # sub-series per year (e.g. Sekolah Jumlah: SD/SMP/SMA/TK/SMK/MA)
        # silently lose their later years.
        years = sorted({f.tahun_lengkap for f in group["rows"] if f.tahun_lengkap is not None})
        selected_years = set(years[-limit:]) if limit else set(years)

        best = {}
        for fakta in sorted(group["rows"], key=lambda f: (f.tahun_lengkap or 0, f.tabel_id or 0, f.id or 0)):
            year = fakta.tahun_lengkap
            if year is None or year not in selected_years:
                continue
            subject = _extract_school_level(fakta.tabel.judul) or wilayah.nama
            # Later tables (higher id) win when a year has overlapping publications.
            best[(year, subject)] = fakta

        observations = []
        for (year, subject), fakta in sorted(best.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            observations.append({
                "id": fakta.id,
                "tahun": year,
                "nilai": float(fakta.nilai_num),
                "nilai_teks": fakta.nilai_teks,
                "wilayah_nama": wilayah.nama,
                "subject_name": subject if subject != wilayah.nama else None,
                "satuan": getattr(fakta.kolom, 'satuan', '') or getattr(group["indicator"], 'satuan', '') or '',
                "tabel": {
                    "id": fakta.tabel_id,
                    "nomor_tabel": fakta.tabel.nomor_tabel,
                    "judul": fakta.tabel.judul,
                },
            })
        # When the query filtered to a single school level (e.g. '... SD ...'),
        # surface that level in the card subject so the UI header/title shows it
        # instead of only the wilayah name. Multi-level results (all school types)
        # stay unlabeled and rely on the SD/SMP/SMA columns/legend.
        level_subjects = sorted({o["subject_name"] for o in observations if o.get("subject_name")})
        card_subject = f"{wilayah.nama} ({level_subjects[0]})" if len(level_subjects) == 1 else None

        payload.append({
            "indicator_id": group["indicator"].id,
            "indicator_name": group.get("display_name") or group["indicator"].nama,
            "wilayah": {"id": wilayah.id, "nama": wilayah.nama, "jenis": wilayah.jenis},
            "subject_name": card_subject,
            "observations": observations,
        })
    return payload


def _quick_topic_matches(query, limit=12):
    """Small answer card for topic-only queries like 'produksi alpukat'."""
    terms = [term for term in normalize_text(query).split() if len(term) >= 3]
    if not terms:
        return []

    age_sig = _extract_age_signature(query)

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
    # Drop facts from tables that don't match the requested age band, so an
    # age-scoped query like "jumlah penduduk umur 15 tahun" never aggregates the
    # all-ages population total.
    if age_sig:
        rows = [fakta for fakta in rows if _title_matches_age(normalize_text(fakta.tabel.judul), age_sig)]
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
        # Negation handling for paired indicators like "Irigasi" vs
        # "Non Irigasi" / "Bukan ...". A bare "irigasi" query must
        # pick the "Irigasi" indicator, NOT "Non Irigasi" (whose name
        # merely contains the substring "irigasi"). Conversely
        # "non irigasi" must pick "Non Irigasi", not "Irigasi".
        NEG_TOKENS = ("non", "bukan", "tanpa")
        irigasi_terms = [t for t in terms if "irigasi" in t]
        if irigasi_terms:
            has_neg = any(neg in terms for neg in NEG_TOKENS)
            name_l = indicator_name
            if has_neg:
                # "non irigasi": prefer "Non Irigasi"; penalize
                # the plain "Irigasi" indicator (no neg token in name).
                if "non" not in name_l and "bukan" not in name_l:
                    points -= 1000
            else:
                # bare "irigasi": prefer "Irigasi"; penalize
                # "Non Irigasi" and boost the plain indicator.
                if "non" in name_l or "bukan" in name_l:
                    points -= 1000
                else:
                    points += 30
        return -points, indicator_name

    best = sorted(grouped.values(), key=score)[:3]
    # No-wilayah topic queries cannot pick a single sensible region for
    # point-level indicators (elevation, %, index, density, ...). Summing them
    # is meaningless and picking one kecamatan arbitrarily is misleading, so we
    # drop those indicators here and let the UI surface them as per-region
    # candidates the user can open (the chart modal already plots per-region
    # lines). Count-style indicators still get a proper total card.
    best = [group for group in best if not _is_non_additive(group["indicator"].nama)][:3]
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
            # If the table carries a parent/regency total row (wilayah ==
            # "Kabupaten Tasikmalaya"), that row already aggregates the
            # sub-region rows, so using it ALONE is correct. Summing every
            # row would double-count (regency total + its districts).
            # Only fall back to summing the components when no such parent
            # row exists (purely sub-region tables whose total is the sum).
            parent_rows = [
                f
                for f in year_rows
                if getattr(f.wilayah, "nama", None) == "Kabupaten Tasikmalaya"
                and f.nilai_num is not None
            ]
            if parent_rows:
                total = sum((f.nilai_num for f in parent_rows), Decimal("0"))
            else:
                total = sum(
                    (f.nilai_num for f in year_rows if f.nilai_num is not None),
                    Decimal("0"),
                )
            sample = year_rows[0]
            observations.append({
                "id": sample.id,
                "tahun": year,
                "nilai": float(total),
                "nilai_teks": str(total.normalize()) if hasattr(total, "normalize") else str(total),
                "wilayah_nama": "Kabupaten Tasikmalaya",
                "satuan": getattr(sample.kolom, "satuan", "") or getattr(group["indicator"], "satuan", "") or "",
                "tabel": {
                    "id": sample.tabel_id,
                    "nomor_tabel": sample.tabel.nomor_tabel,
                    "judul": sample.tabel.judul,
                },
            })
        if observations:
            payload.append({
                "indicator_id": group["indicator"].id,
                "indicator_name": _indicator_display_name(group["indicator"].nama),
                "subject_name": "Kabupaten Tasikmalaya",
                "summary_kind": "aggregate",
                "observations": observations,
            })
    return payload


def _indicator_display_name(raw_name):
    """Human-friendly indicator label for the direct-answer card.

    Publication indicator names are often noisy compound tags like
    'Penduduk - Jumlah' or 'Penduduk - Laki-Laki'. Strip the leading
    subject/entity prefix (anything before the first ' - ') so the card shows
    a clean concept ('Jumlah', 'Laki-Laki') rather than the extraction artifact.
    """
    label = (raw_name or "").strip()
    if " - " in label:
        label = label.split(" - ", 1)[1].strip()
    return label or (raw_name or "-").strip() or "-"


def _rincian_display_name(raw_name):
    """Normalize noisy left-column labels for chart subjects.

    Publication rows often mix Indonesian/English labels (Aspal/Paved) or carry
    section prefixes ([I. JENIS PERMUKAAN] a. Diaspal). The search card should
    show the human concept, not the extraction artifact.
    """
    label = (raw_name or "").strip()
    label = re.sub(r"^\[[^\]]+\]\s*", "", label)
    label = re.sub(r"^[a-z]\.?\s+", "", label, flags=re.IGNORECASE)
    label = label.split("/")[0].strip(" \t-–—")
    normalized = normalize_text(label)
    if normalized == "diaspal":
        return "Aspal"
    return label or (raw_name or "-").strip() or "-"


def _rincian_key(raw_name):
    return normalize_text(_rincian_display_name(raw_name))


def _publication_year(fakta):
    try:
        return fakta.tabel.bab.publikasi.tahun_terbit
    except Exception:
        return 0


def _fakta_observation(fakta, subject_name, subject_kind="rincian"):
    return {
        "id": fakta.id,
        "tahun": fakta.tahun_lengkap,
        "nilai": float(fakta.nilai_num),
        "nilai_teks": fakta.nilai_teks,
        "wilayah_nama": getattr(fakta.wilayah, 'nama', None) or "-",
        "rincian_nama": subject_name if subject_kind == "rincian" else getattr(fakta.rincian, 'nama', None),
        "subject_name": subject_name,
        "subject_kind": subject_kind,
        "satuan": getattr(fakta.kolom, 'satuan', '') or getattr(fakta.kolom.indikator, 'satuan', '') or '',
        "tabel": {
            "id": fakta.tabel_id,
            "nomor_tabel": fakta.tabel.nomor_tabel,
            "judul": fakta.tabel.judul,
        },
    }


def _quick_rincian_matches(query, limit=12):
    """Direct answer cards for left-column/rincian queries like 'aspal'.

    If the user's term hits a `rincian` label, return that rincian as the chart
    subject. If the term only names the indicator/table (e.g. 'panjang jalan'),
    return a compact comparison of the most relevant rincian categories.
    """
    terms = _query_terms(query)
    if not terms:
        return []

    age_sig = _extract_age_signature(query)

    qs = (
        Fakta.objects.filter(rincian__isnull=False, nilai_num__isnull=False)
        .select_related('kolom__indikator', 'tabel', 'tabel__bab__publikasi', 'wilayah', 'rincian')
    )
    for term in terms:
        qs = qs.filter(
            Q(kolom__indikator__nama__icontains=term)
            | Q(tabel__judul__icontains=term)
            | Q(rincian__nama__icontains=term)
        )

    rows = list(qs.order_by('tabel__nomor_tabel', 'kolom__indikator__nama', 'tahun', 'id')[:8000])
    if age_sig:
        rows = [fakta for fakta in rows if _title_matches_age(normalize_text(fakta.tabel.judul), age_sig)]
    if not rows:
        return []

    subject_intent = any(
        any(term in _rincian_key(fakta.rincian.nama) for term in terms)
        for fakta in rows
        if fakta.rincian_id
    )

    grouped = {}
    for fakta in rows:
        indicator = fakta.kolom.indikator
        table_number = fakta.tabel.nomor_tabel or ""
        key = (indicator.id, table_number)
        grouped.setdefault(key, {"indicator": indicator, "table_number": table_number, "rows": []})["rows"].append(fakta)

    surface_terms = {"aspal", "kerikil", "tanah", "lainnya"}

    def group_score(group):
        indicator_name = normalize_text(group["indicator"].nama)
        titles = " ".join(normalize_text(fakta.tabel.judul) for fakta in group["rows"][:20])
        subjects = " ".join(_rincian_key(fakta.rincian.nama) for fakta in group["rows"][:80] if fakta.rincian_id)
        haystack = f"{indicator_name} {titles} {subjects}"
        points = 0
        if all(term in indicator_name for term in terms):
            points += 90
        if all(term in titles for term in terms):
            points += 70
        if subject_intent and any(term in subjects for term in terms):
            points += 85
        if all(term in haystack for term in terms):
            points += 30
        if "panjang" in terms and "jalan" in terms and "jenis permukaan" in titles:
            points += 35
        subject_keys = {_rincian_key(fakta.rincian.nama) for fakta in group["rows"] if fakta.rincian_id}
        if subject_keys & surface_terms:
            points += 15
        points += min(len({fakta.tahun_lengkap for fakta in group["rows"] if fakta.tahun_lengkap}), 12)
        points += min(max((_publication_year(fakta) for fakta in group["rows"]), default=0) - 2010, 20)
        if indicator_name.startswith("status jalan"):
            points -= 45
        return -points, indicator_name, group["table_number"]

    def build_payload(group):
        rows_by_subject = {}
        for fakta in group["rows"]:
            if not fakta.rincian_id:
                continue
            subject_name = _rincian_display_name(fakta.rincian.nama)
            subject_key = _rincian_key(fakta.rincian.nama)
            if not subject_key:
                continue
            rows_by_subject.setdefault(subject_key, {"name": subject_name, "rows": []})["rows"].append(fakta)

        if not rows_by_subject:
            return None

        group_titles = " ".join(normalize_text(fakta.tabel.judul) for fakta in group["rows"][:20])
        if subject_intent:
            matched = [
                key for key in rows_by_subject
                if any(term in key for term in terms)
            ]
            # If the only intent match is the trivial total ('jumlah'/'total'),
            # prefer the real breakdown categories instead of collapsing to it.
            trivial = {key for key in matched if key in {"jumlah", "total"}}
            if matched and matched != list(trivial):
                selected_keys = matched
            else:
                breakdown_keys = [
                    key for key in rows_by_subject
                    if key not in {"jumlah", "total", "kabupaten tasikmalaya"}
                ]
                selected_keys = breakdown_keys or list(rows_by_subject)
        elif "jenis permukaan" in group_titles and (set(rows_by_subject) & surface_terms):
            selected_keys = [key for key in rows_by_subject if key in surface_terms]
        else:
            # No explicit subject in the query. Prefer a meaningful breakdown
            # (the real rincian categories) over collapsing to the 'Jumlah'
            # total row. E.g. "penduduk umur 15 tahun" should surface the
            # weekly-activity split (Bekerja, Sekolah, Mengurus Rumah
            # Tangga, ...) rather than just the grand total labelled
            # "Penduduk - Jumlah".
            breakdown_keys = [
                key for key in rows_by_subject
                if key not in {"jumlah", "total", "kabupaten tasikmalaya"}
            ]
            selected_keys = breakdown_keys or list(rows_by_subject)

        def subject_rank(key):
            subject_rows = rows_by_subject[key]["rows"]
            latest_pub = max((_publication_year(fakta) for fakta in subject_rows), default=0)
            latest_year = max((fakta.tahun_lengkap or 0 for fakta in subject_rows), default=0)
            term_hit = any(term in key for term in terms)
            surface_order = {"aspal": 0, "kerikil": 1, "tanah": 2, "lainnya": 3}.get(key, 9)
            return (0 if term_hit else 1, surface_order, -latest_pub, -latest_year, key)

        selected_keys = sorted(selected_keys, key=subject_rank)[:6]
        best_by_subject_year = {}
        for key in selected_keys:
            for fakta in rows_by_subject[key]["rows"]:
                year = fakta.tahun_lengkap
                if year is None:
                    continue
                current = best_by_subject_year.get((key, year))
                current_rank = (_publication_year(current), current.tabel_id, current.id) if current else (-1, -1, -1)
                fakta_rank = (_publication_year(fakta), fakta.tabel_id, fakta.id)
                if current is None or fakta_rank > current_rank:
                    best_by_subject_year[(key, year)] = fakta

        observations = []
        for key in selected_keys:
            subject_rows = [
                best_by_subject_year[(key, year)]
                for year in sorted({year for subject_key, year in best_by_subject_year if subject_key == key})[:limit]
            ]
            subject_name = rows_by_subject[key]["name"]
            observations.extend(_fakta_observation(fakta, subject_name) for fakta in subject_rows)

        if not observations:
            return None

        subject_names = [rows_by_subject[key]["name"] for key in selected_keys]
        subject_name = subject_names[0] if len(subject_names) == 1 else " + ".join(subject_names)
        return {
            "indicator_id": group["indicator"].id,
            "indicator_name": _indicator_display_name(group["indicator"].nama),
            "subject_name": subject_name,
            "age_label": age_sig or None,
            "summary_kind": "rincian",
            "comparison_subjects": [{"nama": name, "jenis": "rincian"} for name in subject_names],
            "observations": sorted(
                observations,
                key=lambda observation: (observation.get("subject_name") or "", observation.get("tahun") or 0, observation.get("id") or 0),
            ),
        }

    payload = []
    for group in sorted(grouped.values(), key=group_score):
        item = build_payload(group)
        if item:
            payload.append(item)
        if len(payload) >= 3:
            break
    return payload


def _quick_school_matches(query, wilayah=None, limit=12):
    """Resolve school queries (e.g. 'jumlah sekolah RA', 'murid SMK swasta',
    'guru SMP di singaparna') to the correct indicator in the matching
    'Jumlah Sekolah, Murid, Guru ... (LEVEL)' table.

    This bypasses the generic rincian/indicator matchers, which wrongly match
    'sekolah' to the *rincian* named 'Sekolah' inside the population table
    (3.2.1: people whose weekly activity is schooling), returning population
    headcount instead of the school figure.

    The subject (sekolah/murid/guru) and ownership (swasta/negeri/jumlah) are
    read from the query and mapped onto the real indicator names used by the
    publications (e.g. 'Murid Swasta', 'Sekolah Jumlah'), so 'murid SMK swasta'
    returns private SMK students, not the SMK school count.
    """
    terms = _query_terms(query)
    school_terms = [t for t in terms if t.upper() in SCHOOL_LEVELS]
    # Must contain a school subject word AND a school level to qualify.
    subject_terms = [t for t in terms if t in {"sekolah", "murid", "guru", "siswa"}]
    if not (school_terms and subject_terms):
        return []

    # Map query subject word -> indicator stem.
    SUBJECT_STEMS = {"sekolah": "Sekolah", "murid": "Murid", "siswa": "Murid", "guru": "Guru"}
    subject_stem = SUBJECT_STEMS[subject_terms[0]]
    # Ownership: swasta/negeri override the default 'Jumlah'.
    if "swasta" in terms:
        ownership = "Swasta"
    elif "negeri" in terms:
        ownership = "Negeri"
    else:
        ownership = "Jumlah"

    qs = (
        Fakta.objects.filter(nilai_num__isnull=False)
        .select_related("kolom__indikator", "tabel", "tabel__bab__publikasi", "wilayah")
    )
    if wilayah is not None:
        qs = qs.filter(wilayah=wilayah)
    # School tables are titled 'Jumlah Sekolah, Murid, Guru ... (LEVEL) Menurut
    # Kecamatan'. Match the formal level tag inside parentheses (e.g. "(SMK)")
    # rather than a bare icontains, because bare "smk"/"ra" would hit other words.
    from django.db.models import Q  # noqa: F401 (already imported at module top)
    level_filters = Q()
    for level in school_terms:
        level_filters |= Q(tabel__judul__icontains=f"({level.upper()})")
    qs = qs.filter(level_filters)
    # Match the subject indicator. Indicator naming differs across publications:
    # 4.1.2 (RA) uses bare 'Sekolah'/'Murid', while 4.1.3+ use 'Sekolah Jumlah'/
    # 'Murid Swasta'. So we match on the stem and, for an explicit ownership,
    # require that word; for the default 'Jumlah' we exclude the Swasta/Negeri
    # variants so the bare stem does not also pull 'Sekolah Swasta'.
    qs = qs.filter(kolom__indikator__nama__icontains=subject_stem)
    if ownership == "Swasta":
        qs = qs.filter(kolom__indikator__nama__icontains="Swasta")
    elif ownership == "Negeri":
        qs = qs.filter(kolom__indikator__nama__icontains="Negeri")
    else:
        qs = qs.exclude(kolom__indikator__nama__icontains="Swasta").exclude(
            kolom__indikator__nama__icontains="Negeri"
        )

    rows = list(qs.order_by("tabel__bab__publikasi__tahun_terbit", "tahun", "id")[:8000])
    if not rows:
        return []

    regency_name = "Kabupaten Tasikmalaya"
    # Aggregate per year. With a specific wilayah we take that row; otherwise we
    # prefer the regency-total row if present, else sum ALL kecamatan rows to
    # produce the kabupaten total (not an arbitrary single-kecamatan value).
    rows_by_year = {}
    for fakta in rows:
        year = fakta.tahun_lengkap
        if year is None:
            continue
        rows_by_year.setdefault(year, []).append(fakta)

    by_year = {}
    for year, fakta_rows in rows_by_year.items():
        if wilayah is not None:
            chosen = next((f for f in fakta_rows if f.wilayah_id == wilayah.id), fakta_rows[0])
            by_year[year] = chosen
            continue
        # Sum every matched school-level table's regency total so the card
        # shows the true kabupaten total across ALL levels (SD+SMP+SMA+...),
        # not just the first table that happens to sort first.
        regency_rows = [f for f in fakta_rows if f.wilayah and f.wilayah.nama == regency_name]
        if regency_rows:
            total = sum((f.nilai_num for f in regency_rows if f.nilai_num is not None), Decimal("0"))
            repr_fakta = regency_rows[0]
            repr_fakta.nilai_num = total
            by_year[year] = repr_fakta
        else:
            # No pre-computed regency total: sum every kecamatan row for the year.
            total = sum((f.nilai_num for f in fakta_rows if f.nilai_num is not None), Decimal("0"))
            # Clone the first row and stamp the summed value so the payload keeps
            # a consistent shape (table/satuan identifiers stay intact).
            repr_fakta = fakta_rows[0]
            repr_fakta.nilai_num = total
            repr_fakta.wilayah = None
            by_year[year] = repr_fakta

    observations = sorted(
        (
            {
                "id": f.id,
                "tahun": year,
                "nilai": float(f.nilai_num),
                "nilai_teks": f.nilai_teks,
                "wilayah_nama": f.wilayah.nama if f.wilayah else regency_name,
                "subject_name": None,
                "satuan": getattr(f.kolom, "satuan", "") or getattr(f.kolom.indikator, "satuan", "") or "",
                "tabel": {"id": f.tabel_id, "nomor_tabel": f.tabel.nomor_tabel, "judul": f.tabel.judul},
            }
            for year, f in by_year.items()
        ),
        key=lambda o: (o["tahun"] or 0),
    )
    if not observations:
        return []

    # Map a school level tag to a friendly, human-readable label so the card
    # title says which kind of school the user asked for.
    _SCHOOL_LEVEL_NAMES = {
        "RA": "Raudatul Athfal (RA)",
        "SD": "SD",
        "MI": "Madrasah Ibtidaiyah (MI)",
        "TK": "TK",
        "SMP": "SMP",
        "MTS": "Madrasah Tsanawiyah (MTs)",
        "SMA": "SMA",
        "SMK": "SMK",
        "MA": "Madrasah Aliyah (MA)",
        "SLB": "SLB",
    }
    upper_levels = sorted({t.upper() for t in school_terms})
    friendly_levels = [_SCHOOL_LEVEL_NAMES.get(lvl, lvl) for lvl in upper_levels]
    level_label = friendly_levels[0] if len(friendly_levels) == 1 else "Sekolah"
    subject_label = {"Sekolah": "Jumlah Sekolah", "Murid": "Jumlah Murid", "Guru": "Jumlah Guru"}[subject_stem]
    ownership_label = "" if ownership == "Jumlah" else f" {ownership}"
    display_name = f"{subject_label}{ownership_label} ({level_label})"
    wilayah_nama = wilayah.nama if wilayah else regency_name
    # When a wilayah is named (e.g. 'di singaparna'), append the level so the
    # card subject reads 'Singaparna (SMK)'. For the no-wilayah case the level
    # is already in the indicator_name, so keep the subject plain.
    card_subject = (
        f"{wilayah_nama} ({friendly_levels[0]})" if (wilayah and len(friendly_levels) == 1) else wilayah_nama
    )
    return [
        {
            "indicator_id": rows[0].kolom.indikator.id,
            "indicator_name": display_name,
            "wilayah": {"id": wilayah.id, "nama": wilayah.nama, "jenis": wilayah.jenis} if wilayah else None,
            "subject_name": card_subject,
            "summary_kind": "aggregate",
            "drill_mode": "series",
            "observations": observations,
        }
    ]


def _quick_guru_matches(query, wilayah=None, limit=12):
    """Resolve 'jumlah guru' / 'guru swasta' / 'guru SMA' to the teacher count
    in the 'Jumlah Sekolah, Guru, dan Murid ... (LEVEL)' tables.

    Models after ``_quick_school_matches``. The generic rincian matcher must
    NOT handle 'guru': it wrongly surfaces the 'Jabatan Fungsional Guru'
    *rincian* inside the ASN/PNS tables (or, absent that, the population
    'Mengurus rumah tangga' breakdown), because it requires a ``rincian`` and
    only scores by substring presence. This returns the actual teacher count.
    """
    terms = _query_terms(query)
    if "guru" not in terms:
        return []

    level_terms = [t for t in terms if t.upper() in SCHOOL_LEVELS]

    # Ownership / category from the query.
    if "swasta" in terms:
        ownership = "Swasta"
    elif "negeri" in terms:
        ownership = "Negeri"
    elif "asn" in terms:
        ownership = "ASN"
    else:
        ownership = "Jumlah"

    qs = (
        Fakta.objects.filter(nilai_num__isnull=False)
        .select_related("kolom__indikator", "tabel", "tabel__bab__publikasi", "wilayah")
    )
    if wilayah is not None:
        qs = qs.filter(wilayah=wilayah)
    # Restrict to the teacher tables family so we never pull 'Jabatan
    # Fungsional Guru' from the ASN/PNS tables.
    qs = qs.filter(tabel__judul__icontains="Jumlah Sekolah, Guru, dan Murid")
    # When a school level is named, pin to that level's table.
    if level_terms:
        level_filters = Q()
        for level in level_terms:
            level_filters |= Q(tabel__judul__icontains=f"({level.upper()})")
        qs = qs.filter(level_filters)
    # Match the Guru indicator stem + ownership/category.
    qs = qs.filter(kolom__indikator__nama__icontains="Guru")
    if ownership == "Jumlah":
        # Plain total: 'Guru Jumlah' (exclude the qualified variants).
        qs = qs.filter(kolom__indikator__nama__icontains="Jumlah")
        qs = qs.exclude(kolom__indikator__nama__icontains="ASN")
        qs = qs.exclude(kolom__indikator__nama__icontains="Non")
    elif ownership == "Swasta":
        qs = qs.filter(kolom__indikator__nama__icontains="Swasta")
    elif ownership == "Negeri":
        qs = qs.filter(kolom__indikator__nama__icontains="Negeri")
    elif ownership == "ASN":
        qs = qs.filter(kolom__indikator__nama__icontains="ASN")

    rows = list(qs.order_by("tabel__bab__publikasi__tahun_terbit", "tahun", "id")[:8000])
    if not rows:
        return []

    regency_name = "Kabupaten Tasikmalaya"
    rows_by_year = {}
    for fakta in rows:
        year = fakta.tahun_lengkap
        if year is None:
            continue
        rows_by_year.setdefault(year, []).append(fakta)

    by_year = {}
    for year, fakta_rows in rows_by_year.items():
        if wilayah is not None:
            chosen = next((f for f in fakta_rows if f.wilayah_id == wilayah.id), fakta_rows[0])
            by_year[year] = chosen
            continue
        regency_rows = [f for f in fakta_rows if f.wilayah and f.wilayah.nama == regency_name]
        if regency_rows:
            # Sum every matched school-level table's regency total so the card
            # shows the true kabupaten total across ALL levels, not just the
            # first table that sorts first.
            total = sum((f.nilai_num for f in regency_rows if f.nilai_num is not None), Decimal("0"))
            repr_fakta = regency_rows[0]
            repr_fakta.nilai_num = total
            by_year[year] = repr_fakta
        else:
            # No pre-computed regency total: sum every row for the year
            # (across all matched school levels / kecamatan).
            total = sum((f.nilai_num for f in fakta_rows if f.nilai_num is not None), Decimal("0"))
            repr_fakta = fakta_rows[0]
            repr_fakta.nilai_num = total
            repr_fakta.wilayah = None
            by_year[year] = repr_fakta

    observations = sorted(
        (
            {
                "id": f.id,
                "tahun": year,
                "nilai": float(f.nilai_num),
                "nilai_teks": f.nilai_teks,
                "wilayah_nama": f.wilayah.nama if f.wilayah else regency_name,
                "subject_name": None,
                "satuan": getattr(f.kolom, "satuan", "") or getattr(f.kolom.indikator, "satuan", "") or "",
                "tabel": {"id": f.tabel_id, "nomor_tabel": f.tabel.nomor_tabel, "judul": f.tabel.judul},
            }
            for year, f in by_year.items()
        ),
        key=lambda o: (o["tahun"] or 0),
    )
    if not observations:
        return []

    ownership_label = "" if ownership == "Jumlah" else f" {ownership}"
    _SCHOOL_LEVEL_NAMES = {
        "RA": "Raudatul Athfal (RA)",
        "SD": "SD",
        "MI": "Madrasah Ibtidaiyah (MI)",
        "TK": "TK",
        "SMP": "SMP",
        "MTS": "Madrasah Tsanawiyah (MTs)",
        "SMA": "SMA",
        "SMK": "SMK",
        "MA": "Madrasah Aliyah (MA)",
        "SLB": "SLB",
    }
    if level_terms:
        upper_levels = sorted({t.upper() for t in level_terms})
        friendly_levels = [_SCHOOL_LEVEL_NAMES.get(lvl, lvl) for lvl in upper_levels]
        level_label = friendly_levels[0] if len(friendly_levels) == 1 else "Sekolah"
        display_name = f"Jumlah Guru{ownership_label} ({level_label})"
    else:
        display_name = f"Jumlah Guru{ownership_label}"
        level_label = None
    wilayah_nama = wilayah.nama if wilayah else regency_name
    card_subject = (
        f"{wilayah_nama} ({level_label})" if (wilayah and level_label) else wilayah_nama
    )
    return [
        {
            "indicator_id": rows[0].kolom.indikator.id,
            "indicator_name": display_name,
            "wilayah": {"id": wilayah.id, "nama": wilayah.nama, "jenis": wilayah.jenis} if wilayah else None,
            "subject_name": card_subject,
            "summary_kind": "aggregate",
            "drill_mode": "series",
            "observations": observations,
        }
    ]


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

    school_terms = [term for term in terms if term.upper() in SCHOOL_LEVELS]
    indicator_terms = [term for term in terms if term.upper() not in SCHOOL_LEVELS]

    qs = (
        Fakta.objects.filter(wilayah=wilayah, nilai_num__isnull=False)
        .select_related('kolom__indikator', 'tabel', 'wilayah')
    )
    for term in indicator_terms:
        qs = qs.filter(kolom__indikator__nama__icontains=term)
    # School-level tokens (SD/SMP/SMA/SMK/TK/MA/...) live in the table title
    # e.g. 'Jumlah Sekolah Dasar (SD) Menurut Kecamatan', not in the shared
    # indicator name 'Sekolah Jumlah'. Match them against the title so that a
    # query like 'jumlah sekolah SD di singaparna' still resolves to the SD series.
    for term in school_terms:
        qs = qs.filter(tabel__judul__icontains=term)

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


def _quick_wilayah_matches_for_wilayahs(query, wilayahs, limit=12):
    """Return quick answer cards whose observations include every detected wilayah.

    The first wilayah still controls ranking, but observations from the same
    indicator in the other detected wilayahs are merged into the same card so
    the inline search result can immediately draw a comparison chart.
    """
    wilayahs = list(wilayahs or [])
    if not wilayahs:
        return []
    if len(wilayahs) == 1:
        return _quick_wilayah_matches(query, wilayahs[0], limit)

    matches_by_wilayah = [
        (wilayah, _quick_wilayah_matches(query, wilayah, limit))
        for wilayah in wilayahs
    ]
    primary_matches = matches_by_wilayah[0][1]
    merged_payload = []

    for primary_match in primary_matches:
        merged_match = deepcopy(primary_match)
        merged_match["comparison_subjects"] = [
            {"id": wilayah.id, "nama": wilayah.nama, "jenis": wilayah.jenis}
            for wilayah in wilayahs
        ]
        merged_match["subject_name"] = " + ".join(wilayah.nama for wilayah in wilayahs)
        merged_observations = list(merged_match.get("observations") or [])

        for wilayah, wilayah_matches in matches_by_wilayah[1:]:
            comparable = next(
                (
                    match for match in wilayah_matches
                    if match.get("indicator_id") == primary_match.get("indicator_id")
                    or match.get("indicator_name") == primary_match.get("indicator_name")
                ),
                None,
            )
            if comparable:
                merged_observations.extend(comparable.get("observations") or [])

        selected_names = {wilayah.nama for wilayah in wilayahs}
        merged_match["observations"] = sorted(
            (
                observation for observation in merged_observations
                if observation.get("wilayah_nama") in selected_names
            ),
            key=lambda observation: (observation.get("wilayah_nama") or "", observation.get("tahun") or 0, observation.get("id") or 0),
        )
        merged_payload.append(merged_match)

    return merged_payload


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
        # Primary wilayah = highest-ranked (regency > kecamatan, longer name
        # wins), NOT first by query position. This stops a fragment like
        # kecamatan 'Hasil Registrasi' from hijacking a query that merely
        # mentions 'Hasil Penjualan'.
        detected_wilayah = (
            sorted(detected_wilayahs, key=_wilayah_rank)[0]
            if detected_wilayahs else None
        )
        search_query = _query_without_wilayahs(query, detected_wilayahs)
        # Teacher-count queries ('jumlah guru', 'guru swasta', 'guru SMA') resolve
        # to the correct 'Jumlah Sekolah, Guru, dan Murid (LEVEL)' table and take
        # priority over the generic rincian matcher, which would otherwise
        # surface the 'Jabatan Fungsional Guru' rincian (ASN/PNS tables) or the
        # population 'Mengurus rumah tangga' breakdown.
        quick_matches = _quick_guru_matches(search_query, detected_wilayah)
        if not quick_matches:
            # School-count queries ('jumlah sekolah RA', 'jumlah sekolah SD di X')
            # resolve to the correct 'Jumlah Sekolah (LEVEL)' table and take
            # priority over the generic rincian/indicator matchers, which would
            # otherwise collide with the population table's 'Sekolah' rincian.
            quick_matches = _quick_school_matches(search_query, detected_wilayah)
        if not quick_matches:
            wilayah_matches = (
                _quick_wilayah_matches_for_wilayahs(search_query, detected_wilayahs)
                if detected_wilayah
                else []
            )
            if wilayah_matches:
                quick_matches = wilayah_matches
            else:
                # The wilayah-scoped matcher ANDs every query term against the
                # indicator *name* (line 830). Table-title queries like
                # "Hasil Penjualan Tiket Objek Wisata Per Triwulan" carry terms
                # ("penjualan", "wisata", "triwulan") that live in the table
                # title, not the indicator name ("Pengunjung"/"Tiket"), so
                # the strict matcher returns nothing. Fall through to the
                # broader rincian/topic matchers (which OR across title) so
                # these queries still get a direct-answer card.
                quick_matches = _quick_rincian_matches(search_query) or _quick_topic_matches(search_query)

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

        if quick_matches:
            quick_indicator_ids = [item["indicator_id"] for item in quick_matches if item.get("indicator_id")]
            indicator_by_id = Indikator.objects.in_bulk(quick_indicator_ids)
            extra_indikator_qs = [
                indicator_by_id[indicator_id]
                for indicator_id in quick_indicator_ids
                if indicator_id in indicator_by_id
            ]
            indikator_qs = _merge_by_id(extra_indikator_qs, indikator_qs)[:15]

            quick_table_ids = []
            for item in quick_matches:
                for observation in item.get("observations") or []:
                    table_id = (observation.get("tabel") or {}).get("id")
                    if table_id:
                        quick_table_ids.append(table_id)
            table_by_id = Tabel.objects.in_bulk(quick_table_ids)
            extra_tabel_qs = [table_by_id[table_id] for table_id in quick_table_ids if table_id in table_by_id]
            tabel_qs = _merge_by_id(extra_tabel_qs, tabel_qs)[:10]

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


class CatalogAPIView(APIView):
    """Read-only catalog browser across all publications.

    Tables are merged by `nomor_tabel` so Table 1.1.1 is ONE item covering
    every publication year (2018-2025), not N separate cards. Each merged item
    links to a time-series that spans all years.

    Because the same nomor_tabel can carry different units between years
    (e.g. ha vs km2) or extra indicator columns, the merged series endpoint
    tags every row with its derived `tahun` and `unit` so the chart can keep
    incompatible units as separate series instead of plotting a false crash.
    No write actions are exposed.
    """

    NORMALIZE = lambda self, name: re.sub(r"\s+", " ", (name or "").strip().lower())

    def get(self, request):
        from apps.katalog.models import Bab, Tabel

        # Merged time-series fetch: ?nomor_tabel=<n> returns the combined
        # series for that table number across ALL publications (multi-year).
        nomor = request.GET.get("nomor_tabel")
        if nomor:
            tables = list(
                Tabel.objects.filter(nomor_tabel=nomor)
                .select_related("bab__publikasi")
                .order_by("-bab__publikasi__tahun_terbit")
            )
            if not tables:
                return Response({"error": "nomor_tabel tidak ditemukan"}, status=404)
            rows = (
                Fakta.objects.filter(tabel__in=tables)
                .exclude(nilai_num__isnull=True)
                .select_related("wilayah", "rincian", "kolom", "tabel")
                .order_by("tabel__bab__publikasi__tahun_terbit")
            )
            series = []
            for f in rows:
                tahun = f.tahun_lengkap
                if tahun is None:
                    continue
                unit = (f.kolom.satuan if f.kolom_id else "") or ""
                # Normalize unit case so "Jiwa" and "jiwa" merge as one indicator.
                unit = unit.strip().lower() if unit and unit.strip().lower() != "none" else ""
                series.append(
                    {
                        "id": f.id,
                        "tahun": tahun,
                        "nilai": float(f.nilai_num),
                        "nilai_teks": f.nilai_teks,
                        "unit": unit,
                        "wilayah_nama": f.wilayah.nama if f.wilayah else "-",
                        "rincian_nama": f.rincian.nama if f.rincian else "-",
                        "subject_name": f.kolom.indikator.nama if f.kolom_id else (f.wilayah.nama if f.wilayah else "-"),
                        "flag": f.flag or "ada",
                    }
                )
            first = tables[0]
            return Response(
                {
                    "nomor_tabel": nomor,
                    "judul": first.judul,
                    "nama_ringkas": first.nama_ringkas,
                    "series": series,
                }
            )

        babs = (
            Bab.objects.all()
            .select_related("publikasi")
            .prefetch_related("tabel_set")
            .order_by("nomor", "publikasi__tahun_terbit", "publikasi_id")
        )

        # Group babs by normalized name; preserve first-seen bab number for order.
        bab_order = []
        bab_map = {}  # normalized name -> (display_name, [Tabel,...])
        for bab in babs:
            key = self.NORMALIZE(bab.nama)
            tabel_list = list(bab.tabel_set.all().order_by("nomor_tabel"))
            if key not in bab_map:
                bab_map[key] = (bab.nama, [])
                bab_order.append(key)
            _, existing = bab_map[key]
            bab_map[key] = (bab_map[key][0], existing + tabel_list)

        bab_data = []
        # Collect every tabel in this run once, then do bulk aggregations in
        # SQL (no per-table Python round-trips — that used to be 800+ queries
        # and took >60s).
        all_tables = [t for _, (_, tl) in bab_map.items() for t in tl]
        tabel_ids = [t.id for t in all_tables]

        # Bulk counts + year range per table (uses the indexed `tahun` column).
        from django.db.models import Count, Min, Max
        agg = (
            Fakta.objects.filter(tabel_id__in=tabel_ids)
            .exclude(nilai_num__isnull=True)
            .values("tabel_id")
            .annotate(
                jumlah=Count("id"),
                min_tahun=Min("tahun"),
                max_tahun=Max("tahun"),
            )
        )
        stats = {row["tabel_id"]: row for row in agg}

        for key in bab_order:
            display_name, tables = bab_map[key]
            if not tables:
                continue
            # Merge tables by nomor_tabel: one node per table number.
            merged = {}  # nomor_tabel -> node
            for tabel in tables:
                nt = tabel.nomor_tabel
                s = stats.get(tabel.id, {"jumlah": 0, "min_tahun": None, "max_tahun": None})
                if nt not in merged:
                    merged[nt] = {
                        "nomor_tabel": nt,
                        "nama_ringkas": tabel.nama_ringkas,
                        "judul": tabel.judul,
                        "tipe_baris": tabel.tipe_baris,
                        "jumlah_publikasi": 0,
                        "jumlah_baris": 0,
                        "publikasi_tahun": set(),
                    }
                node = merged[nt]
                node["jumlah_publikasi"] += 1
                node["jumlah_baris"] += s["jumlah"]
                pub_year = tabel.bab.publikasi.tahun_terbit
                node["publikasi_tahun"].add(pub_year)
                # Prefer the title/short-name from the NEWEST publication so the
                # catalog shows the current wording (not the oldest year's).
                if pub_year >= node.get("_best_year", -1):
                    node["_best_year"] = pub_year
                    node["judul"] = tabel.judul
                    if tabel.nama_ringkas:
                        node["nama_ringkas"] = tabel.nama_ringkas
                elif not node["nama_ringkas"] and tabel.nama_ringkas:
                    node["nama_ringkas"] = tabel.nama_ringkas

            ordered = sorted(
                merged.values(),
                key=lambda n: [int(p) if p.isdigit() else p for p in n["nomor_tabel"].split(".")],
            )
            tabel_nodes = []
            for node in ordered:
                pub_years = sorted(node["publikasi_tahun"])
                rentang = [pub_years[0], pub_years[-1]] if pub_years else None
                tabel_nodes.append(
                    {
                        "nomor_tabel": node["nomor_tabel"],
                        "nama_ringkas": node["nama_ringkas"],
                        "judul": node["judul"],
                        "tipe_baris": node["tipe_baris"],
                        "jumlah_publikasi": node["jumlah_publikasi"],
                        "jumlah_baris": node["jumlah_baris"],
                        "rentang_tahun": rentang,
                    }
                )
            bab_data.append(
                {
                    "id": key,
                    "nomor": tables[0].bab.nomor,
                    "nama": display_name,
                    "jumlah_tabel": len(tabel_nodes),
                    "tabel": tabel_nodes,
                }
            )

        return Response({"babs": bab_data})


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
