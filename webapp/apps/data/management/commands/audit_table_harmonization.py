from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from apps.data.harmonization import normalize_text, table_title_similarity, token_jaccard
from apps.katalog.models import Publikasi, Tabel


class TableSignatureCache:
    def __init__(self):
        self._columns: dict[int, set[str]] = {}
        self._units: dict[int, set[str]] = {}

    def column_labels(self, table: Tabel) -> set[str]:
        if table.id not in self._columns:
            self._columns[table.id] = {
                normalize_text(col.indikator.nama)
                for col in table.kolom_set.all()
                if normalize_text(col.indikator.nama)
            }
        return self._columns[table.id]

    def unit_labels(self, table: Tabel) -> set[str]:
        if table.id not in self._units:
            self._units[table.id] = {
                normalize_text(col.satuan or col.indikator.satuan or "")
                for col in table.kolom_set.all()
                if normalize_text(col.satuan or col.indikator.satuan or "")
            }
        return self._units[table.id]


def table_score(master: Tabel, legacy: Tabel, cache: TableSignatureCache) -> tuple[float, tuple[str, ...]]:
    reasons: list[str] = []
    title_score = table_title_similarity(master.judul, legacy.judul)
    col_score = token_jaccard(cache.column_labels(master), cache.column_labels(legacy))
    unit_score = token_jaccard(cache.unit_labels(master), cache.unit_labels(legacy))

    score = title_score * 0.55 + col_score * 0.25 + unit_score * 0.10

    if master.bab.nama == legacy.bab.nama:
        score += 0.07
        reasons.append("same_topic")
    if master.nomor_tabel == legacy.nomor_tabel:
        score += 0.03
        reasons.append("same_table_number")

    reasons.extend([
        f"title:{title_score:.2f}",
        f"columns:{col_score:.2f}",
        f"units:{unit_score:.2f}",
    ])
    return min(score, 1.0), tuple(reasons)


def split_score(master: Tabel, candidates: list[Tabel], cache: TableSignatureCache) -> tuple[float, tuple[str, ...]]:
    if not candidates:
        return 0.0, ()
    master_cols = cache.column_labels(master)
    master_units = cache.unit_labels(master)
    candidate_cols = set().union(*(cache.column_labels(table) for table in candidates))
    candidate_units = set().union(*(cache.unit_labels(table) for table in candidates))
    title_avg = sum(table_title_similarity(master.judul, table.judul) for table in candidates) / len(candidates)
    col_cover = len(master_cols & candidate_cols) / len(master_cols) if master_cols else 0.0
    unit_cover = len(master_units & candidate_units) / len(master_units) if master_units else 0.0
    topic_bonus = 0.08 if all(table.bab.nama == master.bab.nama for table in candidates) else 0.0
    score = title_avg * 0.45 + col_cover * 0.40 + unit_cover * 0.07 + topic_bonus
    return min(score, 1.0), (f"title_avg:{title_avg:.2f}", f"column_cover:{col_cover:.2f}", f"unit_cover:{unit_cover:.2f}")


class Command(BaseCommand):
    help = "Audit table-level same/renamed/split/merge candidates against a master year. Read-only."

    def add_arguments(self, parser):
        parser.add_argument("--master-year", type=int, default=2026)
        parser.add_argument("--examples", type=int, default=20)
        parser.add_argument("--min-score", type=float, default=0.62)
        parser.add_argument("--split-min-score", type=float, default=0.55)

    def handle(self, *args, **options):
        master_year = options["master_year"]
        examples = options["examples"]
        min_score = options["min_score"]
        split_min_score = options["split_min_score"]

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

        cache = TableSignatureCache()
        classifications = Counter()
        examples_by_class: dict[str, list[str]] = defaultdict(list)
        best_legacy_usage: dict[tuple[int, int], list[str]] = defaultdict(list)

        for master in master_tables:
            for year, legacy_tables in sorted(legacy_by_year.items(), reverse=True):
                scored = []
                for legacy in legacy_tables:
                    score, reasons = table_score(master, legacy, cache)
                    if score >= min_score:
                        scored.append((score, legacy, reasons))
                scored.sort(key=lambda item: item[0], reverse=True)

                if scored:
                    best_score, best_legacy, reasons = scored[0]
                    if master.nomor_tabel == best_legacy.nomor_tabel:
                        klass = "SAME_TABLE"
                    else:
                        klass = "RENAMED_TABLE"
                    classifications[klass] += 1
                    best_legacy_usage[(year, best_legacy.id)].append(f"{master.nomor_tabel} {master.judul[:70]}")
                    self._add_example(
                        examples_by_class,
                        klass,
                        examples,
                        f"{year} score={best_score:.2f} {','.join(reasons)} | MASTER {master.nomor_tabel} {master.judul[:85]} <- LEGACY {best_legacy.nomor_tabel} {best_legacy.judul[:85]}",
                    )
                    continue

                same_topic = [table for table in legacy_tables if table.bab.nama == master.bab.nama]
                split_candidates = sorted(
                    same_topic,
                    key=lambda table: table_title_similarity(master.judul, table.judul),
                    reverse=True,
                )[:4]
                split_candidate_score, split_reasons = split_score(master, split_candidates, cache)
                if len(split_candidates) >= 2 and split_candidate_score >= split_min_score:
                    klass = "SPLIT_LEGACY"
                    classifications[klass] += 1
                    self._add_example(
                        examples_by_class,
                        klass,
                        examples,
                        f"{year} score={split_candidate_score:.2f} {','.join(split_reasons)} | MASTER {master.nomor_tabel} {master.judul[:85]} <- LEGACY {[table.nomor_tabel for table in split_candidates]}",
                    )
                else:
                    klass = "NO_MATCH"
                    classifications[klass] += 1
                    self._add_example(
                        examples_by_class,
                        klass,
                        examples,
                        f"{year} | MASTER {master.nomor_tabel} {master.judul[:100]}",
                    )

        merged_examples = []
        for (year, legacy_id), masters in best_legacy_usage.items():
            if len(masters) > 1 and len(merged_examples) < examples:
                legacy = Tabel.objects.get(id=legacy_id)
                merged_examples.append(
                    f"{year} LEGACY {legacy.nomor_tabel} {legacy.judul[:85]} -> MASTER {masters[:4]}"
                )
        classifications["MERGED_LEGACY"] = len(merged_examples)

        self.stdout.write(self.style.SUCCESS("=== TABLE HARMONIZATION AUDIT ==="))
        self.stdout.write(f"Master year: {master_year}")
        self.stdout.write(f"Master tables: {len(master_tables)}")
        self.stdout.write(f"Legacy years: {', '.join(str(y) for y in sorted(legacy_by_year))}")
        self.stdout.write(f"Title-first min score: {min_score:.2f}")
        self.stdout.write(f"Split min score: {split_min_score:.2f}")
        self.stdout.write("")
        self.stdout.write("=== CLASSIFICATION COUNTS (master table x legacy year) ===")
        for klass in ["SAME_TABLE", "RENAMED_TABLE", "SPLIT_LEGACY", "NO_MATCH", "MERGED_LEGACY"]:
            self.stdout.write(f"{klass:<15} {classifications[klass]:>6}")

        for klass in ["SAME_TABLE", "RENAMED_TABLE", "SPLIT_LEGACY", "NO_MATCH"]:
            rows = examples_by_class.get(klass, [])
            if rows:
                self.stdout.write(f"\n=== {klass} EXAMPLES ===")
                for row in rows:
                    self.stdout.write(f"  - {row}")

        if merged_examples:
            self.stdout.write("\n=== MERGED_LEGACY EXAMPLES ===")
            for row in merged_examples:
                self.stdout.write(f"  - {row}")

    def _add_example(self, examples_by_class, klass, limit, text):
        if len(examples_by_class[klass]) < limit:
            examples_by_class[klass].append(text)
