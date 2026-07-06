from collections import Counter
from decimal import Decimal
import time

from django.core.management.base import BaseCommand
from django.db import connection

from apps.data.utils import decimal_differs, normalize_numeric, normalize_text


class Command(BaseCommand):
    help = "Audit fakta data quality for canonical time-series readiness. Read-only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sample",
            type=int,
            default=5000,
            help="Number of nilai_teks rows to inspect for numeric checks. Use 0 for all rows.",
        )
        parser.add_argument(
            "--examples",
            type=int,
            default=10,
            help="Maximum examples to print per section.",
        )

    def handle(self, *args, **options):
        start_time = time.time()
        sample_size = options["sample"]
        example_limit = options["examples"]

        self.stdout.write(self.style.SUCCESS("=== DATA QUALITY AUDIT ==="))
        self.stdout.write("Mode: read-only")
        self.stdout.write(f"Numeric sample: {'ALL' if sample_size == 0 else sample_size}")

        with connection.cursor() as cursor:
            self._print_core_counts(cursor)
            self._print_duplicate_grains(cursor, example_limit)
            self._print_numeric_issues(cursor, sample_size, example_limit)
            self._print_contextual_alias_risk(cursor, example_limit)
            self._print_year_coverage(cursor)

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"\n=== AUDIT COMPLETE ({elapsed:.2f}s) ==="))

    def _print_core_counts(self, cursor):
        self.stdout.write(self.style.NOTICE("\n=== CORE COUNTS ==="))
        cursor.execute(
            """
            SELECT 'fakta' AS item, COUNT(*) FROM data_fakta
            UNION ALL SELECT 'publikasi', COUNT(*) FROM katalog_publikasi
            UNION ALL SELECT 'tabel', COUNT(*) FROM katalog_tabel
            UNION ALL SELECT 'kolom_tabel', COUNT(*) FROM katalog_kolomtabel
            UNION ALL SELECT 'indikator', COUNT(*) FROM referensi_indikator
            UNION ALL SELECT 'wilayah', COUNT(*) FROM referensi_wilayah
            UNION ALL SELECT 'rincian', COUNT(*) FROM referensi_rincian
            ORDER BY 1
            """
        )
        for item, count in cursor.fetchall():
            self.stdout.write(f"{item:<14} {count:>10}")

    def _print_duplicate_grains(self, cursor, example_limit):
        self.stdout.write(self.style.NOTICE("\n=== DUPLICATE GRAIN CHECK ==="))
        cursor.execute(
            """
            WITH fakta_context AS (
                SELECT
                    f.id,
                    f.tabel_id,
                    f.kolom_id,
                    f.wilayah_id,
                    f.rincian_id,
                    COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) AS effective_year
                FROM data_fakta f
                LEFT JOIN katalog_kolomtabel k ON k.id = f.kolom_id
                JOIN katalog_tabel t ON t.id = f.tabel_id
                JOIN katalog_bab b ON b.id = t.bab_id
                JOIN katalog_publikasi p ON p.id = b.publikasi_id
            ), duplicates AS (
                SELECT
                    tabel_id,
                    kolom_id,
                    wilayah_id,
                    rincian_id,
                    effective_year,
                    COUNT(*) AS cnt,
                    MIN(id) AS first_id
                FROM fakta_context
                GROUP BY 1,2,3,4,5
                HAVING COUNT(*) > 1
            )
            SELECT COUNT(*), COALESCE(SUM(cnt), 0), COALESCE(MAX(cnt), 0)
            FROM duplicates
            """
        )
        duplicate_groups, rows_in_duplicates, max_group = cursor.fetchone()
        self.stdout.write(f"Duplicate grain groups: {duplicate_groups}")
        self.stdout.write(f"Rows in duplicate groups: {rows_in_duplicates}")
        self.stdout.write(f"Largest duplicate group: {max_group}")

        if duplicate_groups:
            cursor.execute(
                """
                WITH fakta_context AS (
                    SELECT
                        f.id,
                        f.tabel_id,
                        f.kolom_id,
                        f.wilayah_id,
                        f.rincian_id,
                        COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) AS effective_year,
                        t.nomor_tabel,
                        t.judul AS table_title,
                        i.nama AS indicator_name,
                        w.nama AS wilayah_name,
                        r.nama AS rincian_name
                    FROM data_fakta f
                    LEFT JOIN katalog_kolomtabel k ON k.id = f.kolom_id
                    LEFT JOIN referensi_indikator i ON i.id = k.indikator_id
                    LEFT JOIN referensi_wilayah w ON w.id = f.wilayah_id
                    LEFT JOIN referensi_rincian r ON r.id = f.rincian_id
                    JOIN katalog_tabel t ON t.id = f.tabel_id
                    JOIN katalog_bab b ON b.id = t.bab_id
                    JOIN katalog_publikasi p ON p.id = b.publikasi_id
                )
                SELECT
                    nomor_tabel,
                    table_title,
                    indicator_name,
                    COALESCE(wilayah_name, rincian_name, '-') AS subject_name,
                    effective_year,
                    COUNT(*) AS cnt
                FROM fakta_context
                GROUP BY 1,2,3,4,5, tabel_id, kolom_id, wilayah_id, rincian_id
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC, nomor_tabel
                LIMIT %s
                """,
                [example_limit],
            )
            self.stdout.write("Examples:")
            for nomor, title, indicator, subject, year, count in cursor.fetchall():
                self.stdout.write(f"  - {count}x | {year} | {nomor} | {indicator} | {subject} | {title[:90]}")

    def _print_numeric_issues(self, cursor, sample_size, example_limit):
        self.stdout.write(self.style.NOTICE("\n=== NUMERIC NORMALIZATION CHECK ==="))
        limit_sql = "" if sample_size == 0 else "LIMIT %s"
        params = [] if sample_size == 0 else [sample_size]
        cursor.execute(
            f"""
            SELECT
                f.id,
                f.nilai_teks,
                f.nilai_num,
                COALESCE(k.satuan, i.satuan, '') AS unit,
                i.nama AS indicator_name,
                t.nomor_tabel,
                t.judul AS table_title
            FROM data_fakta f
            LEFT JOIN katalog_kolomtabel k ON k.id = f.kolom_id
            LEFT JOIN referensi_indikator i ON i.id = k.indikator_id
            JOIN katalog_tabel t ON t.id = f.tabel_id
            WHERE COALESCE(f.nilai_teks, '') <> ''
            ORDER BY f.id
            {limit_sql}
            """,
            params,
        )
        rows = cursor.fetchall()

        status_counter = Counter()
        differing_examples = []
        parseable_missing_num = []
        unparseable_examples = []

        for fakta_id, nilai_teks, nilai_num, unit, indicator, nomor, title in rows:
            normalized, status = normalize_numeric(nilai_teks, unit)
            status_counter[status] += 1

            if normalized is not None and nilai_num is None and len(parseable_missing_num) < example_limit:
                parseable_missing_num.append((fakta_id, nilai_teks, normalized, unit, indicator, nomor, title))
            if status == "unparseable" and len(unparseable_examples) < example_limit:
                unparseable_examples.append((fakta_id, nilai_teks, unit, indicator, nomor, title))
            if decimal_differs(normalized, nilai_num) and len(differing_examples) < example_limit:
                differing_examples.append((fakta_id, nilai_teks, nilai_num, normalized, unit, indicator, nomor, title))

        self.stdout.write(f"Rows inspected: {len(rows)}")
        for status, count in status_counter.most_common():
            self.stdout.write(f"{status:<14} {count:>10}")
        self.stdout.write(f"Stored nilai_num differs from normalized sample examples: {len(differing_examples)} shown")
        self.stdout.write(f"Parseable text but nilai_num NULL examples: {len(parseable_missing_num)} shown")
        self.stdout.write(f"Unparseable examples: {len(unparseable_examples)} shown")

        if differing_examples:
            self.stdout.write("\nDiffering examples:")
            for fakta_id, raw, stored, normalized, unit, indicator, nomor, title in differing_examples:
                self.stdout.write(
                    f"  - id={fakta_id} raw={raw!r} stored={stored} normalized={normalized} "
                    f"unit={unit!r} | {nomor} | {indicator} | {title[:70]}"
                )

        if parseable_missing_num:
            self.stdout.write("\nParseable text with NULL numeric examples:")
            for fakta_id, raw, normalized, unit, indicator, nomor, title in parseable_missing_num:
                self.stdout.write(
                    f"  - id={fakta_id} raw={raw!r} normalized={normalized} unit={unit!r} "
                    f"| {nomor} | {indicator} | {title[:70]}"
                )

        if unparseable_examples:
            self.stdout.write("\nUnparseable examples:")
            for fakta_id, raw, unit, indicator, nomor, title in unparseable_examples:
                self.stdout.write(f"  - id={fakta_id} raw={raw!r} unit={unit!r} | {nomor} | {indicator} | {title[:70]}")

    def _print_contextual_alias_risk(self, cursor, example_limit):
        self.stdout.write(self.style.NOTICE("\n=== CONTEXTUAL ALIAS RISK ==="))
        cursor.execute(
            """
            SELECT
                i.nama AS indicator_name,
                COUNT(*) AS rows,
                COUNT(DISTINCT t.id) AS tables,
                COUNT(DISTINCT b.nama) AS topics
            FROM data_fakta f
            JOIN katalog_kolomtabel k ON k.id = f.kolom_id
            JOIN referensi_indikator i ON i.id = k.indikator_id
            JOIN katalog_tabel t ON t.id = f.tabel_id
            JOIN katalog_bab b ON b.id = t.bab_id
            GROUP BY i.id, i.nama
            HAVING COUNT(DISTINCT t.id) > 1
            ORDER BY tables DESC, rows DESC
            LIMIT %s
            """,
            [example_limit],
        )
        self.stdout.write("Raw indicator names reused across multiple table contexts:")
        for indicator, rows, tables, topics in cursor.fetchall():
            indicator_norm = normalize_text(indicator)
            generic = indicator_norm in {"jumlah", "total", "laki laki", "perempuan", "laki laki perempuan"}
            marker = " [GENERIC: needs table_title_pattern]" if generic else ""
            self.stdout.write(f"  - {indicator}: {rows} rows, {tables} tables, {topics} topics{marker}")

    def _print_year_coverage(self, cursor):
        self.stdout.write(self.style.NOTICE("\n=== EFFECTIVE YEAR COVERAGE ==="))
        cursor.execute(
            """
            WITH effective AS (
                SELECT COALESCE(f.tahun, k.tahun, t.tahun_data, p.tahun_terbit - 1) AS effective_year
                FROM data_fakta f
                LEFT JOIN katalog_kolomtabel k ON k.id = f.kolom_id
                JOIN katalog_tabel t ON t.id = f.tabel_id
                JOIN katalog_bab b ON b.id = t.bab_id
                JOIN katalog_publikasi p ON p.id = b.publikasi_id
            )
            SELECT
                COUNT(*) AS total_rows,
                COUNT(effective_year) AS rows_with_year,
                COUNT(*) - COUNT(effective_year) AS rows_without_year,
                MIN(effective_year) AS min_year,
                MAX(effective_year) AS max_year,
                COUNT(DISTINCT effective_year) AS distinct_years
            FROM effective
            """
        )
        total, with_year, without_year, min_year, max_year, distinct_years = cursor.fetchone()
        self.stdout.write(f"Rows: {total}")
        self.stdout.write(f"Rows with effective year: {with_year}")
        self.stdout.write(f"Rows without effective year: {without_year}")
        self.stdout.write(f"Year range: {min_year}..{max_year} ({distinct_years} distinct)")
