"""Helpers for indicator harmonization against a master publication year."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from django.utils.text import slugify

from apps.data.models import CanonicalIndicator, IndicatorAlias
from apps.data.utils import normalize_text
from apps.katalog.models import KolomTabel

TITLE_STOPWORDS = {
    "dan",
    "di",
    "ke",
    "menurut",
    "kabupaten",
    "tasikmalaya",
    "tahun",
    "dalam",
    "pada",
    "per",
    "jumlah",
    "dengan",
    "provinsi",
    "jawa",
    "barat",
}

GENERIC_LABELS = {
    "jumlah",
    "total",
    "laki laki",
    "perempuan",
    "laki laki perempuan",
    "2020",
    "2021",
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
}

CONFLICT_TOKEN_GROUPS = (
    {"laki", "perempuan", "jumlah", "total"},
    {"negeri", "swasta", "jumlah", "total"},
    {"permanen", "semi", "tanpa"},
    {"berlaku", "konstan", "distribusi", "laju"},
)


@dataclass(frozen=True)
class AliasSuggestion:
    master_column_id: int
    legacy_column_id: int
    canonical_code: str
    canonical_name: str
    alias_text: str
    table_title_pattern: str
    confidence: float
    reasons: tuple[str, ...]
    needs_review: bool


@dataclass(frozen=True)
class CrossTableAliasSuggestion(AliasSuggestion):
    master_table_id: int
    legacy_table_id: int
    legacy_year: int
    table_confidence: float
    table_relation: str


def text_similarity(left: str, right: str) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm and not right_norm:
        return 1.0
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def meaningful_title_tokens(title: str) -> set[str]:
    """Meaningful title tokens for table-level matching."""
    return {
        token
        for token in normalize_text(title).split()
        if len(token) > 3 and token not in TITLE_STOPWORDS and not token.isdigit()
    }


def token_jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def table_title_similarity(left: str, right: str) -> float:
    """Title similarity that prioritizes shared statistical context words."""
    sequence = text_similarity(left, right)
    token_overlap = token_jaccard(meaningful_title_tokens(left), meaningful_title_tokens(right))
    return (sequence * 0.45) + (token_overlap * 0.55)


def title_pattern(title: str, max_tokens: int = 6) -> str:
    """Build a conservative context pattern from meaningful title tokens."""
    tokens = [t for t in normalize_text(title).split() if len(t) > 3 and t not in TITLE_STOPWORDS and not t.isdigit()]
    return " ".join(tokens[:max_tokens])


def is_generic_indicator(label: str) -> bool:
    norm = normalize_text(label)
    return norm in GENERIC_LABELS or norm.isdigit()


def has_conflicting_label_tokens(left: str, right: str) -> bool:
    """Detect labels that are lexically close but semantically different."""
    left_tokens = set(normalize_text(left).split())
    right_tokens = set(normalize_text(right).split())
    for group in CONFLICT_TOKEN_GROUPS:
        left_hits = left_tokens & group
        right_hits = right_tokens & group
        if left_hits and right_hits and left_hits != right_hits:
            return True
    return False


def alias_requires_context(master_col: KolomTabel, alias_label: str) -> bool:
    return is_generic_indicator(alias_label) or _master_label_reused(master_col)


def alias_context_pattern(master_col: KolomTabel, alias_label: str) -> str:
    return title_pattern(master_col.tabel.judul) if alias_requires_context(master_col, alias_label) else ""


def canonical_code_for_master(master_col: KolomTabel) -> str:
    """
    Generate stable canonical code from master table context.

    Generic/repeated column names must include table number to avoid mixing
    semantically different columns such as PNS Laki-Laki vs Penduduk Laki-Laki.
    """
    indicator_name = master_col.indikator.nama
    base = slugify(indicator_name)[:60] or f"kolom-{master_col.id}"
    if is_generic_indicator(indicator_name) or _master_label_reused(master_col):
        table_code = slugify(master_col.tabel.nomor_tabel.replace(".", "-"))
        base = f"t{table_code}-{base}"
    return base.replace("-", "_")[:80]


def _master_label_reused(master_col: KolomTabel) -> bool:
    return KolomTabel.objects.filter(
        tabel__bab__publikasi=master_col.tabel.bab.publikasi,
        indikator__nama__iexact=master_col.indikator.nama,
    ).exclude(tabel_id=master_col.tabel_id).exists()


def find_existing_canonical(master_col: KolomTabel) -> CanonicalIndicator | None:
    norm = normalize_text(master_col.indikator.nama)
    aliases = IndicatorAlias.objects.filter(
        normalized_alias=norm,
        is_approved=True,
    ).select_related("canonical_indicator")
    for alias in aliases:
        if not alias.table_title_pattern:
            return alias.canonical_indicator
        pattern_tokens = alias.table_title_pattern.split()
        title = normalize_text(master_col.tabel.judul)
        if all(token in title for token in pattern_tokens):
            return alias.canonical_indicator
    return None


def score_column_match(master_col: KolomTabel, legacy_col: KolomTabel) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    reasons: list[str] = []

    if master_col.tabel.nomor_tabel == legacy_col.tabel.nomor_tabel:
        score += 0.40
        reasons.append("same_table_number")

    if master_col.urutan == legacy_col.urutan:
        score += 0.20
        reasons.append("same_column_order")

    master_label = master_col.indikator.nama
    legacy_label = legacy_col.indikator.nama
    label_conflict = has_conflicting_label_tokens(master_label, legacy_label)
    label_sim = text_similarity(master_label, legacy_label)
    if normalize_text(master_label) == normalize_text(legacy_label):
        score += 0.25
        reasons.append("same_indicator_label")
    elif not label_conflict and label_sim >= 0.82:
        score += 0.18
        reasons.append(f"similar_indicator_label:{label_sim:.2f}")
    elif not label_conflict and label_sim >= 0.70:
        score += 0.10
        reasons.append(f"weak_indicator_label:{label_sim:.2f}")
    elif label_conflict:
        reasons.append("conflicting_indicator_tokens")

    master_unit = normalize_text(master_col.satuan or master_col.indikator.satuan or "")
    legacy_unit = normalize_text(legacy_col.satuan or legacy_col.indikator.satuan or "")
    if master_unit and legacy_unit and master_unit == legacy_unit:
        score += 0.08
        reasons.append("same_unit")

    title_sim = table_title_similarity(master_col.tabel.judul, legacy_col.tabel.judul)
    if title_sim >= 0.82:
        score += 0.12
        reasons.append(f"similar_table_title:{title_sim:.2f}")
    elif title_sim >= 0.65:
        score += 0.06
        reasons.append(f"weak_table_title:{title_sim:.2f}")

    if label_conflict:
        score = min(score, 0.74)

    return min(score, 1.0), tuple(reasons)


def _alias_payload(master_col: KolomTabel, legacy_col: KolomTabel, confidence: float, reasons: tuple[str, ...]):
    canonical = find_existing_canonical(master_col)
    canonical_code = canonical.code if canonical else canonical_code_for_master(master_col)
    canonical_name = canonical.name if canonical else master_col.indikator.nama
    pattern = alias_context_pattern(master_col, legacy_col.indikator.nama)
    needs_review = confidence < 0.90 or alias_requires_context(master_col, legacy_col.indikator.nama)
    return canonical_code, canonical_name, pattern, needs_review


def build_suggestion(master_col: KolomTabel, legacy_col: KolomTabel, min_confidence: float) -> AliasSuggestion | None:
    confidence, reasons = score_column_match(master_col, legacy_col)
    if confidence < min_confidence:
        return None

    canonical_code, canonical_name, pattern, needs_review = _alias_payload(master_col, legacy_col, confidence, reasons)
    return AliasSuggestion(
        master_column_id=master_col.id,
        legacy_column_id=legacy_col.id,
        canonical_code=canonical_code,
        canonical_name=canonical_name,
        alias_text=legacy_col.indikator.nama,
        table_title_pattern=pattern,
        confidence=confidence,
        reasons=reasons,
        needs_review=needs_review,
    )


def score_cross_table_column_match(
    master_col: KolomTabel,
    legacy_col: KolomTabel,
    table_confidence: float,
) -> tuple[float, tuple[str, ...]]:
    """Score column mapping when table numbers differ; title context is already table_confidence."""
    score = 0.0
    reasons: list[str] = []

    if master_col.urutan == legacy_col.urutan:
        score += 0.12
        reasons.append("same_column_order")

    master_label = master_col.indikator.nama
    legacy_label = legacy_col.indikator.nama
    label_conflict = has_conflicting_label_tokens(master_label, legacy_label)
    label_sim = text_similarity(master_label, legacy_label)
    if normalize_text(master_label) == normalize_text(legacy_label):
        score += 0.35
        reasons.append("same_indicator_label")
    elif not label_conflict and label_sim >= 0.86:
        score += 0.26
        reasons.append(f"similar_indicator_label:{label_sim:.2f}")
    elif not label_conflict and label_sim >= 0.74:
        score += 0.15
        reasons.append(f"weak_indicator_label:{label_sim:.2f}")
    elif label_conflict:
        reasons.append("conflicting_indicator_tokens")

    master_unit = normalize_text(master_col.satuan or master_col.indikator.satuan or "")
    legacy_unit = normalize_text(legacy_col.satuan or legacy_col.indikator.satuan or "")
    if master_unit and legacy_unit and master_unit == legacy_unit:
        score += 0.10
        reasons.append("same_unit")

    table_points = min(table_confidence, 1.0) * 0.35
    score += table_points
    reasons.append(f"table_context:{table_confidence:.2f}")

    if label_conflict:
        score = min(score, 0.69)

    return min(score, 1.0), tuple(reasons)


def build_cross_table_suggestion(
    *,
    master_col: KolomTabel,
    legacy_col: KolomTabel,
    table_confidence: float,
    table_relation: str,
    min_confidence: float,
) -> CrossTableAliasSuggestion | None:
    confidence, reasons = score_cross_table_column_match(master_col, legacy_col, table_confidence)
    if confidence < min_confidence:
        return None
    canonical_code, canonical_name, pattern, needs_review = _alias_payload(master_col, legacy_col, confidence, reasons)
    return CrossTableAliasSuggestion(
        master_column_id=master_col.id,
        legacy_column_id=legacy_col.id,
        canonical_code=canonical_code,
        canonical_name=canonical_name,
        alias_text=legacy_col.indikator.nama,
        table_title_pattern=pattern,
        confidence=confidence,
        reasons=reasons,
        needs_review=True if table_relation != "RENAMED_TABLE" else needs_review,
        master_table_id=master_col.tabel_id,
        legacy_table_id=legacy_col.tabel_id,
        legacy_year=legacy_col.tabel.bab.publikasi.tahun_terbit,
        table_confidence=table_confidence,
        table_relation=table_relation,
    )
