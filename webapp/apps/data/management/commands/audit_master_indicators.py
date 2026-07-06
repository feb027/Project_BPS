from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from apps.data.harmonization import is_generic_indicator, normalize_text, score_column_match
from apps.katalog.models import KolomTabel, Publikasi


class Command(BaseCommand):
    help = "Audit master publication indicators/columns for cross-year harmonization. Read-only."

    def add_arguments(self, parser):
        parser.add_argument("--master-year", type=int, default=2026)
        parser.add_argument("--examples", type=int, default=20)

    def handle(self, *args, **options):
        master_year = options["master_year"]
        examples = options["examples"]

        master_pubs = Publikasi.objects.filter(tahun_terbit=master_year)
        if not master_pubs.exists():
            self.stderr.write(self.style.ERROR(f"No publication found for master year {master_year}"))
            return

        master_cols = (
            KolomTabel.objects.filter(tabel__bab__publikasi__in=master_pubs)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
            .order_by("tabel__nomor_tabel", "urutan", "id")
        )
        legacy_cols = (
            KolomTabel.objects.exclude(tabel__bab__publikasi__tahun_terbit=master_year)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
            .order_by("tabel__nomor_tabel", "urutan", "id")
        )

        master_count = master_cols.count()
        legacy_count = legacy_cols.count()
        table_count = master_cols.values("tabel_id").distinct().count()
        indicator_count = master_cols.values("indikator_id").distinct().count()

        label_counter = Counter(normalize_text(col.indikator.nama) for col in master_cols)
        repeated_labels = {label: count for label, count in label_counter.items() if count > 1}
        generic_count = sum(1 for col in master_cols if is_generic_indicator(col.indikator.nama))

        legacy_by_table = defaultdict(list)
        for col in legacy_cols:
            legacy_by_table[col.tabel.nomor_tabel].append(col)

        exact_label = 0
        same_table_candidates = 0
        high_confidence = 0
        needs_review = 0
        no_candidate = 0
        example_rows = []

        for master_col in master_cols:
            candidates = legacy_by_table.get(master_col.tabel.nomor_tabel, [])
            if not candidates:
                no_candidate += 1
                continue
            same_table_candidates += 1

            best_col = None
            best_score = 0.0
            best_reasons = ()
            for legacy_col in candidates:
                score, reasons = score_column_match(master_col, legacy_col)
                if score > best_score:
                    best_col = legacy_col
                    best_score = score
                    best_reasons = reasons

            if best_col is None:
                no_candidate += 1
                continue
            if normalize_text(master_col.indikator.nama) == normalize_text(best_col.indikator.nama):
                exact_label += 1
            if best_score >= 0.90:
                high_confidence += 1
            elif best_score >= 0.75:
                needs_review += 1

            if len(example_rows) < examples:
                example_rows.append((master_col, best_col, best_score, best_reasons))

        self.stdout.write(self.style.SUCCESS("=== MASTER INDICATOR AUDIT ==="))
        self.stdout.write(f"Master year: {master_year}")
        self.stdout.write(f"Master publications: {master_pubs.count()}")
        self.stdout.write(f"Master tables: {table_count}")
        self.stdout.write(f"Master columns: {master_count}")
        self.stdout.write(f"Master distinct raw indicators: {indicator_count}")
        self.stdout.write(f"Legacy columns: {legacy_count}")
        self.stdout.write(f"Repeated master labels: {len(repeated_labels)}")
        self.stdout.write(f"Generic/year-like master labels: {generic_count}")
        self.stdout.write("")
        self.stdout.write("=== LEGACY MATCH READINESS ===")
        self.stdout.write(f"Master columns with same table number in legacy: {same_table_candidates}")
        self.stdout.write(f"Best candidate exact label: {exact_label}")
        self.stdout.write(f"Best candidate high confidence >=0.90: {high_confidence}")
        self.stdout.write(f"Best candidate review band 0.75..0.89: {needs_review}")
        self.stdout.write(f"No same-table legacy candidate: {no_candidate}")

        if repeated_labels:
            self.stdout.write("\n=== REPEATED MASTER LABELS (need table context) ===")
            for label, count in sorted(repeated_labels.items(), key=lambda item: (-item[1], item[0]))[:examples]:
                self.stdout.write(f"  - {label}: {count} columns")

        if example_rows:
            self.stdout.write("\n=== BEST MATCH EXAMPLES ===")
            for master_col, legacy_col, score, reasons in example_rows:
                self.stdout.write(
                    f"  - score={score:.2f} {','.join(reasons)} | "
                    f"MASTER {master_col.tabel.nomor_tabel}#{master_col.urutan} {master_col.indikator.nama!r} "
                    f"<- LEGACY {legacy_col.tabel.bab.publikasi.tahun_terbit} {legacy_col.tabel.nomor_tabel}#{legacy_col.urutan} {legacy_col.indikator.nama!r}"
                )
