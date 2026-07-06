from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.data.harmonization import build_cross_table_suggestion, build_suggestion, normalize_text, table_title_similarity
from apps.data.management.commands.audit_table_harmonization import TableSignatureCache, split_score, table_score
from apps.data.models import CanonicalIndicator, IndicatorAlias
from apps.katalog.models import KolomTabel, Publikasi, Tabel


class Command(BaseCommand):
    help = "Report current and potential harmonization coverage against a master year. Read-only."

    def add_arguments(self, parser):
        parser.add_argument("--master-year", type=int, default=2026)
        parser.add_argument("--min-confidence", type=float, default=0.75)
        parser.add_argument("--cross-min-confidence", type=float, default=0.70)
        parser.add_argument("--min-table-score", type=float, default=0.62)
        parser.add_argument("--split-min-score", type=float, default=0.55)
        parser.add_argument("--examples", type=int, default=15)

    def handle(self, *args, **options):
        master_year = options["master_year"]
        min_confidence = options["min_confidence"]
        cross_min_confidence = options["cross_min_confidence"]
        min_table_score = options["min_table_score"]
        split_min_score = options["split_min_score"]
        examples = options["examples"]

        master_pubs = Publikasi.objects.filter(tahun_terbit=master_year)
        if not master_pubs.exists():
            raise CommandError(f"No publication found for master year {master_year}")

        columns = list(
            KolomTabel.objects.select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
            .order_by("tabel__bab__publikasi__tahun_terbit", "tabel__nomor_tabel", "urutan", "id")
        )
        facts_by_column = {
            column_id: fact_count
            for column_id, fact_count in KolomTabel.objects.values("id")
            .annotate(fact_count=Count("fakta_set"))
            .values_list("id", "fact_count")
        }
        total_columns = len(columns)
        total_facts = sum(facts_by_column.get(col.id, 0) for col in columns)
        master_column_ids = {col.id for col in columns if col.tabel.bab.publikasi.tahun_terbit == master_year}
        current_column_ids, current_by_canonical = self._current_approved_coverage(columns)
        same_auto_ids, same_review_ids = self._same_table_potential(master_year, min_confidence)
        cross_auto_ids, cross_review_ids = self._cross_table_potential(
            master_year=master_year,
            min_table_score=min_table_score,
            split_min_score=split_min_score,
            min_confidence=cross_min_confidence,
        )

        # Master columns become coverable when canonical indicators/self-aliases are generated from master.
        potential_auto_ids = current_column_ids | master_column_ids | same_auto_ids | cross_auto_ids
        potential_review_ids = potential_auto_ids | same_review_ids | cross_review_ids

        self.stdout.write(self.style.SUCCESS("=== HARMONIZATION COVERAGE REPORT ==="))
        self.stdout.write(f"Master year: {master_year}")
        self.stdout.write(f"Canonical indicators: {CanonicalIndicator.objects.count()}")
        self.stdout.write(f"Approved aliases: {IndicatorAlias.objects.filter(is_approved=True).count()}")
        self.stdout.write("")
        self.stdout.write("=== BASELINE ===")
        self._print_coverage("Current approved aliases", current_column_ids, total_columns, total_facts, facts_by_column)
        self._print_coverage("Master self coverage potential", master_column_ids, total_columns, total_facts, facts_by_column)
        self.stdout.write("")
        self.stdout.write("=== POTENTIAL COVERAGE ===")
        self._print_coverage("Same-table AUTO", same_auto_ids, total_columns, total_facts, facts_by_column)
        self._print_coverage("Same-table REVIEW", same_review_ids, total_columns, total_facts, facts_by_column)
        self._print_coverage("Cross-table AUTO", cross_auto_ids, total_columns, total_facts, facts_by_column)
        self._print_coverage("Cross-table REVIEW", cross_review_ids, total_columns, total_facts, facts_by_column)
        self._print_coverage("Combined AUTO + master", potential_auto_ids, total_columns, total_facts, facts_by_column)
        self._print_coverage("Combined REVIEW-inclusive", potential_review_ids, total_columns, total_facts, facts_by_column)
        self.stdout.write("")
        self._print_year_coverage(columns, facts_by_column, current_column_ids, potential_auto_ids, potential_review_ids)
        self.stdout.write("")
        self._print_top_uncovered(columns, facts_by_column, potential_review_ids, examples)
        self.stdout.write("")
        self._print_current_canonical_summary(current_by_canonical, facts_by_column, examples)

    def _current_approved_coverage(self, columns):
        aliases = list(IndicatorAlias.objects.filter(is_approved=True).select_related("canonical_indicator", "raw_indicator"))
        covered: set[int] = set()
        by_canonical: dict[str, set[int]] = defaultdict(set)
        for col in columns:
            col_alias = normalize_text(col.indikator.nama)
            for alias in aliases:
                # A stored alias points at one raw Indikator row, but extracted
                # publications can contain normalized siblings that differ only
                # by whitespace/punctuation. Count those siblings the same way
                # the runtime time-series resolver does.
                if alias.raw_indicator_id and alias.raw_indicator_id != col.indikator_id and alias.normalized_alias != col_alias:
                    continue
                if not alias.raw_indicator_id and normalize_text(alias.alias_text) != col_alias:
                    continue
                title = normalize_text(col.tabel.judul)
                if alias.table_title_pattern and not all(token in title for token in alias.table_title_pattern.split()):
                    continue
                topic = normalize_text(col.tabel.bab.nama)
                if alias.topic_hint and normalize_text(alias.topic_hint) not in topic:
                    continue
                covered.add(col.id)
                by_canonical[alias.canonical_indicator.code].add(col.id)
                break
        return covered, by_canonical

    def _same_table_potential(self, master_year, min_confidence):
        master_cols = list(
            KolomTabel.objects.filter(tabel__bab__publikasi__tahun_terbit=master_year)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
        )
        legacy_cols = list(
            KolomTabel.objects.exclude(tabel__bab__publikasi__tahun_terbit=master_year)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
        )
        legacy_by_table_number: dict[str, list[KolomTabel]] = defaultdict(list)
        for col in legacy_cols:
            legacy_by_table_number[col.tabel.nomor_tabel].append(col)

        auto_ids: set[int] = set()
        review_ids: set[int] = set()
        seen = set()
        for master_col in master_cols:
            for legacy_col in legacy_by_table_number.get(master_col.tabel.nomor_tabel, []):
                suggestion = build_suggestion(master_col, legacy_col, min_confidence=min_confidence)
                if suggestion is None:
                    continue
                key = (suggestion.canonical_code, suggestion.legacy_column_id, suggestion.table_title_pattern)
                if key in seen:
                    continue
                seen.add(key)
                if suggestion.confidence >= 0.90 and not suggestion.needs_review:
                    auto_ids.add(suggestion.legacy_column_id)
                else:
                    review_ids.add(suggestion.legacy_column_id)
        return auto_ids, review_ids

    def _cross_table_potential(self, *, master_year, min_table_score, split_min_score, min_confidence):
        master_pubs = Publikasi.objects.filter(tahun_terbit=master_year)
        master_tables = list(
            Tabel.objects.filter(bab__publikasi__in=master_pubs)
            .select_related("bab", "bab__publikasi")
            .prefetch_related("kolom_set", "kolom_set__indikator")
        )
        legacy_by_year: dict[int, list[Tabel]] = defaultdict(list)
        for table in (
            Tabel.objects.exclude(bab__publikasi__tahun_terbit=master_year)
            .select_related("bab", "bab__publikasi")
            .prefetch_related("kolom_set", "kolom_set__indikator")
        ):
            legacy_by_year[table.bab.publikasi.tahun_terbit].append(table)

        master_columns = self._columns_by_table(master_year=master_year, master=True)
        legacy_columns = self._columns_by_table(master_year=master_year, master=False)
        cache = TableSignatureCache()
        auto_ids: set[int] = set()
        review_ids: set[int] = set()
        seen = set()

        for master in master_tables:
            for legacy_tables in legacy_by_year.values():
                candidates = self._renamed_table_candidates(master, legacy_tables, cache, min_table_score)
                candidates += self._split_table_candidates(master, legacy_tables, cache, split_min_score)
                for table_confidence, legacy, relation in candidates:
                    for master_col in master_columns.get(master.id, []):
                        best = None
                        for legacy_col in legacy_columns.get(legacy.id, []):
                            suggestion = build_cross_table_suggestion(
                                master_col=master_col,
                                legacy_col=legacy_col,
                                table_confidence=table_confidence,
                                table_relation=relation,
                                min_confidence=min_confidence,
                            )
                            if suggestion is None:
                                continue
                            if best is None or suggestion.confidence > best.confidence:
                                best = suggestion
                        if best is None:
                            continue
                        key = (best.canonical_code, best.legacy_column_id, best.table_title_pattern, best.legacy_table_id)
                        if key in seen:
                            continue
                        seen.add(key)
                        if best.confidence >= 0.90 and not best.needs_review:
                            auto_ids.add(best.legacy_column_id)
                        else:
                            review_ids.add(best.legacy_column_id)
        return auto_ids, review_ids

    def _columns_by_table(self, *, master_year: int, master: bool) -> dict[int, list[KolomTabel]]:
        qs = KolomTabel.objects.select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
        if master:
            qs = qs.filter(tabel__bab__publikasi__tahun_terbit=master_year)
        else:
            qs = qs.exclude(tabel__bab__publikasi__tahun_terbit=master_year)
        result: dict[int, list[KolomTabel]] = defaultdict(list)
        for col in qs:
            result[col.tabel_id].append(col)
        return result

    def _renamed_table_candidates(self, master, legacy_tables, cache, min_table_score):
        candidates = []
        for legacy in legacy_tables:
            if master.nomor_tabel == legacy.nomor_tabel:
                continue
            score, _ = table_score(master, legacy, cache)
            if score >= min_table_score:
                candidates.append((score, legacy, "RENAMED_TABLE"))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[:1]

    def _split_table_candidates(self, master, legacy_tables, cache, split_min_score):
        same_topic = [table for table in legacy_tables if table.bab.nama == master.bab.nama]
        split_candidates = sorted(
            same_topic,
            key=lambda table: table_title_similarity(master.judul, table.judul),
            reverse=True,
        )[:4]
        score, _ = split_score(master, split_candidates, cache)
        if len(split_candidates) < 2 or score < split_min_score:
            return []
        return [(score, legacy, "SPLIT_LEGACY") for legacy in split_candidates if legacy.nomor_tabel != master.nomor_tabel]

    def _print_coverage(self, label, column_ids, total_columns, total_facts, facts_by_column):
        fact_count = sum(facts_by_column.get(column_id, 0) for column_id in column_ids)
        column_pct = (len(column_ids) / total_columns * 100) if total_columns else 0
        fact_pct = (fact_count / total_facts * 100) if total_facts else 0
        self.stdout.write(f"{label:<30} columns={len(column_ids):>5}/{total_columns:<5} ({column_pct:5.1f}%) facts={fact_count:>7}/{total_facts:<7} ({fact_pct:5.1f}%)")

    def _print_year_coverage(self, columns, facts_by_column, current_ids, auto_ids, review_ids):
        self.stdout.write("=== COVERAGE BY PUBLICATION YEAR ===")
        by_year: dict[int, list[KolomTabel]] = defaultdict(list)
        for col in columns:
            by_year[col.tabel.bab.publikasi.tahun_terbit].append(col)
        for year in sorted(by_year):
            year_cols = by_year[year]
            year_ids = {col.id for col in year_cols}
            year_facts = sum(facts_by_column.get(col.id, 0) for col in year_cols)
            current_facts = sum(facts_by_column.get(col_id, 0) for col_id in year_ids & current_ids)
            auto_facts = sum(facts_by_column.get(col_id, 0) for col_id in year_ids & auto_ids)
            review_facts = sum(facts_by_column.get(col_id, 0) for col_id in year_ids & review_ids)
            self.stdout.write(
                f"{year}: current={len(year_ids & current_ids):>4}/{len(year_ids):<4} facts={current_facts:>6}/{year_facts:<6} | "
                f"auto={len(year_ids & auto_ids):>4}/{len(year_ids):<4} facts={auto_facts:>6}/{year_facts:<6} | "
                f"review={len(year_ids & review_ids):>4}/{len(year_ids):<4} facts={review_facts:>6}/{year_facts:<6}"
            )

    def _print_top_uncovered(self, columns, facts_by_column, covered_ids, examples):
        self.stdout.write("=== TOP UNCOVERED TABLES AFTER REVIEW-INCLUSIVE POTENTIAL ===")
        rows = []
        for col in columns:
            if col.id in covered_ids:
                continue
            rows.append((facts_by_column.get(col.id, 0), col))
        for fact_count, col in sorted(rows, key=lambda item: item[0], reverse=True)[:examples]:
            self.stdout.write(
                f"  - facts={fact_count:>5} | {col.tabel.bab.publikasi.tahun_terbit} {col.tabel.nomor_tabel}#{col.urutan} | "
                f"{col.indikator.nama} | {col.tabel.judul[:95]}"
            )

    def _print_current_canonical_summary(self, by_canonical, facts_by_column, examples):
        self.stdout.write("=== CURRENT APPROVED COVERAGE BY CANONICAL ===")
        rows = []
        for code, column_ids in by_canonical.items():
            fact_count = sum(facts_by_column.get(col_id, 0) for col_id in column_ids)
            rows.append((fact_count, code, len(column_ids)))
        for fact_count, code, col_count in sorted(rows, reverse=True)[:examples]:
            self.stdout.write(f"  - {code:<45} columns={col_count:>4} facts={fact_count:>6}")
