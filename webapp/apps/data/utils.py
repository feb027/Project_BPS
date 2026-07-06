"""Utility functions for data quality and value normalization."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

MISSING_VALUE_MARKERS = {"", "-", "–", "—", "...", "…", "na", "n/a", "null", "none"}
INTEGER_UNITS = {
    "jiwa",
    "orang",
    "penduduk",
    "kepala",
    "kk",
    "rumah tangga",
    "unit",
    "buah",
    "ekor",
    "sekolah",
    "desa",
    "kelurahan",
}
DECIMAL_UNITS = {"persen", "%", "km2", "km²", "ha", "hektare", "rasio"}


def normalize_text(value: str) -> str:
    """Normalize text for matching aliases without changing the stored raw value."""
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w%²]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def clean_numeric_text(value_text: object) -> str:
    """Remove footnotes/symbol noise while preserving numeric separators."""
    value = str(value_text or "").strip()
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\([^)]*\)", "", value)  # footnotes: 12,3 (1)
    value = value.replace("%", "")
    value = re.sub(r"[^0-9,\.\-]", "", value)
    return value.strip()


def _to_decimal(value: str) -> Optional[Decimal]:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _unit_kind(unit: str) -> str:
    unit_norm = normalize_text(unit)
    if any(token in unit_norm for token in DECIMAL_UNITS) or "per " in unit_norm:
        return "decimal"
    if any(token in unit_norm for token in INTEGER_UNITS):
        return "integer"
    if "ribu" in unit_norm:
        return "decimal"
    return "unknown"


def normalize_numeric(value_text: object, unit: str = "") -> Tuple[Optional[Decimal], str]:
    """
    Normalize BPS-style numeric text into Decimal.

    Returns ``(value, status)`` where status is one of:
    - ``original``: already parseable without separator conversion
    - ``normalized``: separators/noise were converted
    - ``missing``: value is an explicit missing marker such as '-' or '...'
    - ``unparseable``: not a recognizable number

    Rules:
    - ``60,126`` with integer/count units -> ``60126``
    - ``3,23`` with percent/ratio/area units -> ``3.23``
    - ``1.234,56`` -> ``1234.56``
    - ``1,234.56`` -> ``1234.56``
    """
    raw = str(value_text or "").strip()
    if raw.lower() in MISSING_VALUE_MARKERS:
        return None, "missing"

    cleaned = clean_numeric_text(raw)
    if cleaned.lower() in MISSING_VALUE_MARKERS:
        return None, "missing"
    if not cleaned or cleaned in {"-", ".", ","}:
        return None, "unparseable"

    if "," not in cleaned and "." not in cleaned:
        parsed = _to_decimal(cleaned)
        if parsed is not None:
            return parsed, "original"

    # Mixed locale formats. Last separator is treated as decimal separator.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            candidate = cleaned.replace(".", "").replace(",", ".")
        else:
            candidate = cleaned.replace(",", "")
        parsed = _to_decimal(candidate)
        return (parsed, "normalized") if parsed is not None else (None, "unparseable")

    unit_kind = _unit_kind(unit)

    if "," in cleaned:
        left, right = cleaned.rsplit(",", 1)
        if unit_kind == "integer" and len(right) == 3:
            candidate = left.replace(",", "") + right
        elif unit_kind == "decimal":
            candidate = left.replace(".", "").replace(",", "") + "." + right
        elif len(right) == 3 and re.fullmatch(r"-?\d{1,3}(,\d{3})*", cleaned):
            candidate = cleaned.replace(",", "")
        else:
            candidate = cleaned.replace(",", ".")
        parsed = _to_decimal(candidate)
        return (parsed, "normalized") if parsed is not None else (None, "unparseable")

    if "." in cleaned:
        left, right = cleaned.rsplit(".", 1)
        if unit_kind == "integer" and len(right) == 3:
            candidate = cleaned.replace(".", "")
        elif unit_kind == "decimal" and len(right) == 3 and re.fullmatch(r"-?\d{1,3}(\.\d{3})*", cleaned):
            # Some extracted BPS area rows use a dot where the PDF rendered a
            # two-decimal value without the decimal comma, e.g. ``24.667`` for
            # ``246,67`` km² and ``270.882`` for ``2.708,82`` km². Treat the
            # grouped digits as centesimal decimal evidence for decimal units.
            candidate = str(Decimal(cleaned.replace(".", "")) / Decimal("100"))
        elif len(right) == 3 and re.fullmatch(r"-?\d{1,3}(\.\d{3})*", cleaned):
            candidate = cleaned.replace(".", "")
        else:
            candidate = cleaned
        parsed = _to_decimal(candidate)
        return (parsed, "normalized") if parsed is not None else (None, "unparseable")

    return None, "unparseable"


def decimal_differs(left: Optional[Decimal], right: object) -> bool:
    """Return True when a normalized decimal differs from a stored DB value."""
    if left is None or right is None:
        return False
    try:
        return left != Decimal(str(right))
    except (InvalidOperation, ValueError):
        return True
