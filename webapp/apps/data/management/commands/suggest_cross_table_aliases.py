import csv
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.data.harmonization import build_cross_table_suggestion, normalize_text, table_title_similarity
from apps.data.management.commands.audit_table_harmonization import TableSignatureCache, split_score, table_score
from apps.katalog.models import KolomTabel, Publikasi, Tabel


class Command(BaseCommand):
    help = "Suggest indicator aliases across renamed/split/merged tables against a master year. Dry-run only."

    def add_arguments(self, parser):
        parser.add_argument("--master-year", type=int, default=2026)
        parser.add_argument("--min-table-score", type=float, default=0.62)
        parser.add_argument("--split-min-score", type=float, default=0.55)
        parser.add_argument("--min-confidence", type=float, default=0.70)
        parser.add_argument("--examples", type=int, default=30)
        parser.add_argument("--max-table-candidates", type=int, default=1, help="Top renamed-table candidates per master table/year.")
        parser.add_argument("--export", type=str, default="", help="Optional CSV export path for review.")

    def handle(self, *args, **options):
        master_year = options["master_year"]
        min_table_score = options["min_table_score"]
        split_min_score = options["split_min_score"]
        min_confidence = options["min_confidence"]
        examples = options["examples"]
        max_table_candidates = options["max_table_candidates"]
        export_path = options["export"]

        master_pubs = Publikasi.objects.filter(tahun_terbit=master_year)
        if not master_pubs.exists():
            raise CommandError(f"No publication found for master year {master_year}")

        master_tables = list(
            Tabel.objects.filter(bab__publikasi__in=master_pubs)
            .select_related("bab", "bab__publikasi")
            .prefetch_related("kolom_set", "kolom_set__indikator")
            .order_by("nomor_tabel", "id")
        )
        legacy_by_year: dict[int, list[Tabel]] = defaultdict(list)
        for table in (
            Tabel.objects.exclude(bab__publikasi__tahun_terbit=master_year)
            .select_related("bab", "bab__publikasi")
            .prefetch_related("kolom_set", "kolom_set__indikator")
            .order_by("bab__publikasi__tahun_terbit", "nomor_tabel", "id")
        ):
            legacy_by_year[table.bab.publikasi.tahun_terbit].append(table)

        master_columns = self._columns_by_table(master_year=master_year, master=True)
        legacy_columns = self._columns_by_table(master_year=master_year, master=False)
        cache = TableSignatureCache()

        suggestions = []
        seen = set()
        relation_counter = Counter()

        for master in master_tables:
            for year, legacy_tables in sorted(legacy_by_year.items(), reverse=True):
                table_candidates = self._renamed_table_candidates(master, legacy_tables, cache, min_table_score, max_table_candidates)
                split_candidates = self._split_table_candidates(master, legacy_tables, cache, split_min_score)
                all_pairs = table_candidates + split_candidates

                for table_confidence, legacy, relation, table_reasons in all_pairs:
                    master_cols = master_columns.get(master.id, [])
                    legacy_cols = legacy_columns.get(legacy.id, [])
                    for master_col in master_cols:
                        best = None
                        for legacy_col in legacy_cols:
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
                        key = (
                            best.canonical_code,
                            normalize_text(best.alias_text),
                            best.table_title_pattern,
                            best.legacy_column_id,
                            best.legacy_table_id,
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        relation_counter[relation] += 1
                        suggestions.append((best, master, legacy, table_reasons))

        auto_count = sum(1 for suggestion, _, _, _ in suggestions if suggestion.confidence >= 0.90 and not suggestion.needs_review)
        review_count = len(suggestions) - auto_count

        self.stdout.write(self.style.SUCCESS("=== CROSS-TABLE ALIAS SUGGESTIONS ==="))
        self.stdout.write(f"Master year: {master_year}")
        self.stdout.write("Mode: DRY-RUN")
        self.stdout.write(f"Min table score: {min_table_score:.2f}")
        self.stdout.write(f"Min alias confidence: {min_confidence:.2f}")
        self.stdout.write(f"Suggestions total: {len(suggestions)}")
        self.stdout.write(f"Auto-band suggestions: {auto_count}")
        self.stdout.write(f"Needs-review suggestions: {review_count}")
        for relation in ["RENAMED_TABLE", "SPLIT_LEGACY"]:
            self.stdout.write(f"{relation:<15} {relation_counter[relation]:>6}")

        if suggestions:
            self.stdout.write("\n=== EXAMPLES ===")
            for suggestion, master, legacy, table_reasons in suggestions[:examples]:
                mode = "AUTO" if suggestion.confidence >= 0.90 and not suggestion.needs_review else "REVIEW"
                self.stdout.write(
                    f"  - {mode} {suggestion.table_relation} alias={suggestion.confidence:.2f} table={suggestion.table_confidence:.2f} | "
                    f"{suggestion.canonical_code} <= {suggestion.alias_text!r} pattern={suggestion.table_title_pattern!r} | "
                    f"master_col={suggestion.master_column_id} legacy_col={suggestion.legacy_column_id} | "
                    f"MASTER {master.nomor_tabel} {master.judul[:65]} <- LEGACY {suggestion.legacy_year} {legacy.nomor_tabel} {legacy.judul[:65]} | "
                    f"alias_reasons={','.join(suggestion.reasons)} | table_reasons={','.join(table_reasons)}"
                )

        if export_path:
            self._export_csv(Path(export_path), suggestions)
            self.stdout.write(f"\nExported review CSV: {export_path}")

        self.stdout.write("\nDry-run only. No database rows were changed.")

    def _columns_by_table(self, *, master_year: int, master: bool) -> dict[int, list[KolomTabel]]:
        qs = KolomTabel.objects.select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator").order_by("tabel_id", "urutan", "id")
        if master:
            qs = qs.filter(tabel__bab__publikasi__tahun_terbit=master_year)
        else:
            qs = qs.exclude(tabel__bab__publikasi__tahun_terbit=master_year)
        result: dict[int, list[KolomTabel]] = defaultdict(list)
        for col in qs:
            result[col.tabel_id].append(col)
        return result

    def _renamed_table_candidates(self, master, legacy_tables, cache, min_table_score, max_table_candidates):
        candidates = []
        for legacy in legacy_tables:
            if master.nomor_tabel == legacy.nomor_tabel:
                continue
            score, reasons = table_score(master, legacy, cache)
            if score >= min_table_score:
                candidates.append((score, legacy, "RENAMED_TABLE", reasons))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[:max_table_candidates]

    def _split_table_candidates(self, master, legacy_tables, cache, split_min_score):
        same_topic = [table for table in legacy_tables if table.bab.nama == master.bab.nama]
        split_candidates = sorted(
            same_topic,
            key=lambda table: table_title_similarity(master.judul, table.judul),
            reverse=True,
        )[:4]
        score, reasons = split_score(master, split_candidates, cache)
        if len(split_candidates) < 2 or score < split_min_score:
            return []
        return [(score, legacy, "SPLIT_LEGACY", reasons) for legacy in split_candidates if legacy.nomor_tabel != master.nomor_tabel]

    def _export_csv(self, path: Path, suggestions):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "relation",
                "legacy_year",
                "confidence",
                "table_confidence",
                "canonical_code",
                "alias_text",
                "table_title_pattern",
                "master_table",
                "master_title",
                "legacy_table",
                "legacy_title",
                "reasons",
            ])
            for suggestion, master, legacy, table_reasons in suggestions:
                writer.writerow([
                    suggestion.table_relation,
                    suggestion.legacy_year,
                    f"{suggestion.confidence:.2f}",
                    f"{suggestion.table_confidence:.2f}",
                    suggestion.canonical_code,
                    suggestion.alias_text,
                    suggestion.table_title_pattern,
                    master.nomor_tabel,
                    master.judul,
                    legacy.nomor_tabel,
                    legacy.judul,
                    ";".join(suggestion.reasons + table_reasons),
                ])
