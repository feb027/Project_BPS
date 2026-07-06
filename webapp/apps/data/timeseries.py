"""Canonical time-series query service."""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from django.db.models import Q

from apps.data.models import CanonicalIndicator, Fakta, UnitAlias
from apps.data.utils import normalize_text
from apps.referensi.models import Indikator


def _decimal_to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unit_multiplier(unit_text: str, unit_aliases: dict[str, UnitAlias]) -> Decimal:
    alias = unit_aliases.get(normalize_text(unit_text))
    return alias.multiplier if alias else Decimal("1")


def _effective_year(fakta: Fakta) -> int | None:
    return fakta.tahun_lengkap


def _source_rank(fakta: Fakta) -> tuple:
    publication_year = fakta.tabel.bab.publikasi.tahun_terbit if fakta.tabel_id and fakta.tabel.bab_id else 0
    table_year = fakta.tabel.tahun_data or 0 if fakta.tabel_id else 0
    return (publication_year, table_year, fakta.id)


def _indicator_ids_for_alias(alias) -> list[int]:
    """
    Return every raw indicator whose normalized label matches the approved alias.

    IndicatorAlias keeps one row per normalized alias/context. When two raw
    Indikator rows only differ by spacing or punctuation (e.g. ``Produksi Jagung``
    vs ``Produksi  Jagung``), the alias row can only point at one raw_indicator.
    Time-series lookup must still include the normalized siblings, otherwise a
    harmless extraction typo silently drops most years.
    """
    normalized_alias = alias.normalized_alias or normalize_text(alias.alias_text)
    ids = [
        indicator.id
        for indicator in Indikator.objects.only("id", "nama")
        if normalize_text(indicator.nama) == normalized_alias
    ]
    if alias.raw_indicator_id and alias.raw_indicator_id not in ids:
        ids.append(alias.raw_indicator_id)
    return ids


def _build_alias_filter(canonical_indicator: CanonicalIndicator) -> Q | None:
    query = None
    for alias in canonical_indicator.aliases.filter(is_approved=True).select_related("raw_indicator"):
        indicator_ids = _indicator_ids_for_alias(alias)
        if indicator_ids:
            alias_query = Q(kolom__indikator_id__in=indicator_ids)
        else:
            alias_query = Q(kolom__indikator__nama__iexact=alias.alias_text)

        if alias.table_title_pattern:
            for token in alias.table_title_pattern.split():
                alias_query &= Q(tabel__judul__icontains=token)

        if alias.topic_hint:
            alias_query &= Q(tabel__bab__nama__icontains=alias.topic_hint)

        query = alias_query if query is None else query | alias_query
    return query


def get_canonical_time_series(
    *,
    indicator_code: str | None = None,
    canonical_indicator_id: int | None = None,
    wilayah_id: int | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    limit: int = 5000,
) -> dict:
    """
    Return canonical observations for a harmonized indicator.

    This service is read-only. It does not mutate raw ``Fakta`` rows and it does
    not guess mappings outside approved ``IndicatorAlias`` records.
    """
    if not indicator_code and not canonical_indicator_id:
        raise ValueError("indicator_code or canonical_indicator_id is required")

    indicators = CanonicalIndicator.objects.select_related("default_unit").filter(is_active=True)
    if canonical_indicator_id:
        canonical_indicator = indicators.get(id=canonical_indicator_id)
    else:
        canonical_indicator = indicators.get(code=indicator_code)

    alias_filter = _build_alias_filter(canonical_indicator)
    if alias_filter is None:
        return {
            "canonical_indicator": _serialize_indicator(canonical_indicator),
            "observations": [],
            "meta": {"row_count": 0, "duplicate_grain_count": 0, "warning": "No approved aliases."},
        }

    qs = (
        Fakta.objects.filter(alias_filter)
        .exclude(nilai_num__isnull=True)
        .select_related(
            "tabel",
            "tabel__bab",
            "tabel__bab__publikasi",
            "kolom",
            "kolom__indikator",
            "wilayah",
            "rincian",
        )
        .order_by("tahun", "wilayah__nama", "rincian__nama", "id")
    )
    if wilayah_id:
        qs = qs.filter(wilayah_id=wilayah_id)

    unit_aliases = {
        alias.normalized_alias: alias
        for alias in UnitAlias.objects.select_related("canonical_unit").all()
    }

    grouped: OrderedDict[tuple, dict] = OrderedDict()
    grouped_rank: dict[tuple, tuple] = {}
    duplicate_grain_count = 0

    for fakta in qs.iterator(chunk_size=1000):
        year = _effective_year(fakta)
        if year is None:
            continue
        if start_year and year < start_year:
            continue
        if end_year and year > end_year:
            continue

        raw_unit = (getattr(fakta.kolom, "satuan", "") or getattr(fakta.kolom.indikator, "satuan", "") or "").strip()
        multiplier = _unit_multiplier(raw_unit, unit_aliases)
        try:
            canonical_value = Decimal(fakta.nilai_num) * multiplier
        except (InvalidOperation, TypeError, ValueError):
            continue

        grain = (
            year,
            fakta.wilayah_id,
            fakta.rincian_id,
            canonical_indicator.id,
        )
        observation = _serialize_observation(fakta, year, canonical_value, raw_unit, multiplier)
        source_rank = _source_rank(fakta)

        if grain in grouped:
            duplicate_grain_count += 1
            duplicate_count = grouped[grain]["duplicate_count"] + 1
            if source_rank > grouped_rank[grain]:
                observation["duplicate_count"] = duplicate_count
                observation["quality_flags"].append("duplicate_canonical_grain")
                grouped[grain] = observation
                grouped_rank[grain] = source_rank
            else:
                grouped[grain]["duplicate_count"] = duplicate_count
                if "duplicate_canonical_grain" not in grouped[grain]["quality_flags"]:
                    grouped[grain]["quality_flags"].append("duplicate_canonical_grain")
            continue

        grouped[grain] = observation
        grouped_rank[grain] = source_rank
        if len(grouped) >= limit:
            break

    observations = list(grouped.values())
    return {
        "canonical_indicator": _serialize_indicator(canonical_indicator),
        "observations": observations,
        "meta": {
            "row_count": len(observations),
            "duplicate_grain_count": duplicate_grain_count,
            "limit": limit,
        },
    }


def _serialize_indicator(indicator: CanonicalIndicator) -> dict:
    unit = indicator.default_unit
    return {
        "id": indicator.id,
        "code": indicator.code,
        "name": indicator.name,
        "topic": indicator.topic,
        "unit": {
            "code": unit.code,
            "name": unit.name,
            "symbol": unit.symbol,
        }
        if unit
        else None,
    }


def _serialize_observation(fakta: Fakta, year: int, canonical_value: Decimal, raw_unit: str, multiplier: Decimal) -> dict:
    wilayah = fakta.wilayah
    rincian = fakta.rincian
    raw_indicator = fakta.kolom.indikator if fakta.kolom_id else None
    subject_name = rincian.nama if rincian else (wilayah.nama if wilayah else "Indonesia")
    subject_type = "rincian" if rincian else ("wilayah" if wilayah else "nasional")
    return {
        "id": fakta.id,
        "tahun": year,
        "nilai": _decimal_to_float(canonical_value),
        "nilai_decimal": str(canonical_value),
        "nilai_teks": fakta.nilai_teks,
        "subject": {"type": subject_type, "name": subject_name},
        "wilayah": {"id": wilayah.id, "nama": wilayah.nama} if wilayah else None,
        "wilayah_nama": wilayah.nama if wilayah else None,
        "rincian": {"id": rincian.id, "nama": rincian.nama, "kelompok": rincian.kelompok} if rincian else None,
        "rincian_nama": rincian.nama if rincian else None,
        "raw_indicator": {"id": raw_indicator.id, "nama": raw_indicator.nama} if raw_indicator else None,
        "raw_unit": raw_unit,
        "unit_multiplier": str(multiplier),
        "source": {
            "tabel_id": fakta.tabel_id,
            "nomor_tabel": fakta.tabel.nomor_tabel,
            "judul_tabel": fakta.tabel.judul,
            "publikasi": fakta.tabel.bab.publikasi.judul if fakta.tabel.bab_id else None,
        },
        "duplicate_count": 1,
        "quality_flags": [],
    }
