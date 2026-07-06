from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand

from apps.data.models import CanonicalIndicator, Fakta, UnitAlias
from apps.data.timeseries import _build_alias_filter, _source_rank
from apps.data.utils import normalize_text


class Command(BaseCommand):
    help = "Validate approved canonical time-series coverage, year stats, duplicate grains, and suspicious jumps. Read-only."

    def add_arguments(self, parser):
        parser.add_argument("--indicator-code", type=str, default="", help="Validate only one canonical indicator code.")
        parser.add_argument("--start-year", type=int, default=0)
        parser.add_argument("--end-year", type=int, default=0)
        parser.add_argument("--jump-ratio", type=float, default=5.0, help="Flag subject-level year jumps above this ratio.")
        parser.add_argument("--examples", type=int, default=10)

    def handle(self, *args, **options):
        indicator_code = options["indicator_code"].strip()
        start_year = options["start_year"] or None
        end_year = options["end_year"] or None
        jump_ratio = Decimal(str(options["jump_ratio"]))
        examples = options["examples"]

        indicators = CanonicalIndicator.objects.filter(is_active=True).order_by("topic", "code")
        if indicator_code:
            indicators = indicators.filter(code=indicator_code)

        unit_aliases = {
            alias.normalized_alias: alias
            for alias in UnitAlias.objects.select_related("canonical_unit").all()
        }

        self.stdout.write(self.style.SUCCESS("=== HARMONIZED TIME-SERIES VALIDATION ==="))
        self.stdout.write(f"Indicator filter: {indicator_code or 'ALL'}")
        self.stdout.write(f"Year range: {start_year or '-'}..{end_year or '-'}")
        self.stdout.write(f"Jump ratio threshold: {jump_ratio}")
        self.stdout.write("")

        for indicator in indicators:
            self._validate_indicator(indicator, unit_aliases, start_year, end_year, jump_ratio, examples)

    def _validate_indicator(self, indicator, unit_aliases, start_year, end_year, jump_ratio, examples):
        alias_filter = _build_alias_filter(indicator)
        if alias_filter is None:
            self.stdout.write(f"- {indicator.code}: no approved aliases")
            return

        qs = (
            Fakta.objects.filter(alias_filter)
            .exclude(nilai_num__isnull=True)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "kolom", "kolom__indikator", "wilayah", "rincian")
            .order_by("tahun", "wilayah_id", "rincian_id", "id")
        )

        selected_by_grain: dict[tuple, tuple[tuple, int, Decimal, Fakta]] = {}
        grain_seen: set[tuple] = set()
        duplicate_grains = 0

        for fakta in qs.iterator(chunk_size=1000):
            year = fakta.tahun_lengkap
            if year is None:
                continue
            if start_year and year < start_year:
                continue
            if end_year and year > end_year:
                continue
            value = self._canonical_value(fakta, unit_aliases)
            if value is None:
                continue

            grain = (year, fakta.wilayah_id, fakta.rincian_id, indicator.id)
            if grain in grain_seen:
                duplicate_grains += 1
            else:
                grain_seen.add(grain)

            source_rank = _source_rank(fakta)
            current = selected_by_grain.get(grain)
            if current is None or source_rank > current[0]:
                selected_by_grain[grain] = (source_rank, year, value, fakta)

        year_values: dict[int, list[Decimal]] = defaultdict(list)
        source_counter = Counter()
        subject_series: dict[tuple, list[tuple[int, Decimal, Fakta]]] = defaultdict(list)
        for _, year, value, fakta in selected_by_grain.values():
            subject_key = (fakta.wilayah_id, fakta.rincian_id)
            subject_series[subject_key].append((year, value, fakta))
            year_values[year].append(value)
            source_counter[(fakta.tabel.bab.publikasi.tahun_terbit, fakta.tabel.nomor_tabel, fakta.tabel.judul)] += 1

        total_rows = sum(len(values) for values in year_values.values())
        years = sorted(year_values)
        if not years:
            self.stdout.write(f"- {indicator.code}: no numeric rows after filters")
            return

        expected_years = set(range(years[0], years[-1] + 1))
        missing_years = sorted(expected_years - set(years))
        jumps = self._find_jumps(subject_series, jump_ratio)

        self.stdout.write(f"=== {indicator.code} | {indicator.name} ===")
        self.stdout.write(
            f"selected_rows={total_rows} years={years[0]}..{years[-1]} year_count={len(years)} "
            f"missing_years={missing_years[:20]} duplicate_candidates={duplicate_grains} suspicious_jumps={len(jumps)}"
        )
        self.stdout.write("Year stats:")
        for year in years:
            values = year_values[year]
            self.stdout.write(
                f"  {year}: n={len(values):>4} min={min(values)} avg={self._avg(values)} max={max(values)}"
            )

        if jumps:
            self.stdout.write("Suspicious jumps:")
            for jump in jumps[:examples]:
                prev_year, year, prev_value, value, ratio, fakta = jump
                subject = fakta.rincian.nama if fakta.rincian_id else (fakta.wilayah.nama if fakta.wilayah_id else "Indonesia")
                self.stdout.write(
                    f"  - {subject}: {prev_year}={prev_value} -> {year}={value} ratio={ratio:.2f} | "
                    f"source={fakta.tabel.bab.publikasi.tahun_terbit} {fakta.tabel.nomor_tabel} {fakta.tabel.judul[:75]}"
                )

        self.stdout.write("Top source tables:")
        for (pub_year, table_number, title), count in source_counter.most_common(5):
            self.stdout.write(f"  - rows={count:>5} | pub={pub_year} table={table_number} | {title[:90]}")
        self.stdout.write("")

    def _canonical_value(self, fakta, unit_aliases):
        raw_unit = (getattr(fakta.kolom, "satuan", "") or getattr(fakta.kolom.indikator, "satuan", "") or "").strip()
        alias = unit_aliases.get(normalize_text(raw_unit))
        multiplier = alias.multiplier if alias else Decimal("1")
        try:
            return Decimal(fakta.nilai_num) * multiplier
        except (InvalidOperation, TypeError, ValueError):
            return None

    def _find_jumps(self, subject_series, jump_ratio):
        jumps = []
        for rows in subject_series.values():
            rows = sorted(rows, key=lambda item: (item[0], item[2].id))
            previous_by_year = {}
            for year, value, fakta in rows:
                previous_by_year.setdefault(year, (value, fakta))
            ordered = sorted(previous_by_year.items())
            for index in range(1, len(ordered)):
                prev_year, (prev_value, _) = ordered[index - 1]
                year, (value, fakta) = ordered[index]
                if prev_value == 0 or value == 0:
                    continue
                high = max(abs(value), abs(prev_value))
                low = min(abs(value), abs(prev_value))
                if low == 0:
                    continue
                ratio = high / low
                if ratio >= jump_ratio:
                    jumps.append((prev_year, year, prev_value, value, ratio, fakta))
        return sorted(jumps, key=lambda item: item[4], reverse=True)

    def _avg(self, values):
        if not values:
            return Decimal("0")
        return (sum(values) / Decimal(len(values))).quantize(Decimal("0.0001"))
