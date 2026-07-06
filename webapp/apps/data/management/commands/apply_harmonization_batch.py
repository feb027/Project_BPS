from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.data.harmonization import (
    alias_context_pattern,
    build_cross_table_suggestion,
    build_suggestion,
    canonical_code_for_master,
    find_existing_canonical,
    normalize_text,
    table_title_similarity,
)
from apps.data.management.commands.audit_table_harmonization import TableSignatureCache, split_score, table_score
from apps.data.models import CanonicalIndicator, IndicatorAlias, UnitAlias
from apps.katalog.models import KolomTabel, Publikasi, Tabel


@dataclass
class TableApplyPlan:
    master_table: Tabel
    master_columns: list[KolomTabel]
    same_table_aliases: list[tuple] = field(default_factory=list)
    cross_table_aliases: list[tuple] = field(default_factory=list)

    @property
    def write_count(self) -> int:
        return len(self.master_columns) + len(self.same_table_aliases) + len(self.cross_table_aliases)


class Command(BaseCommand):
    help = "Apply safe harmonization aliases in small per-master-table batches. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--master-year", type=int, default=2026)
        parser.add_argument("--table-number", type=str, default="", help="Apply only one master table number, e.g. 3.1")
        parser.add_argument("--max-tables", type=int, default=1, help="Batch size. Ignored when --table-number is used.")
        parser.add_argument("--min-confidence", type=float, default=0.75)
        parser.add_argument("--cross-min-confidence", type=float, default=0.70)
        parser.add_argument("--min-table-score", type=float, default=0.62)
        parser.add_argument("--split-min-score", type=float, default=0.55)
        parser.add_argument("--include-cross-auto", action="store_true", help="Also apply the tiny high-confidence cross-table auto band.")
        parser.add_argument("--apply", action="store_true", help="Write aliases. Without this flag, only prints the plan.")

    def handle(self, *args, **options):
        master_year = options["master_year"]
        table_number = options["table_number"].strip()
        max_tables = options["max_tables"]
        include_cross_auto = options["include_cross_auto"]
        apply = options["apply"]

        master_pubs = Publikasi.objects.filter(tahun_terbit=master_year)
        if not master_pubs.exists():
            raise CommandError(f"No publication found for master year {master_year}")

        plans = self._build_plans(
            master_pubs=master_pubs,
            master_year=master_year,
            table_number=table_number,
            max_tables=max_tables,
            include_cross_auto=include_cross_auto,
            min_confidence=options["min_confidence"],
            cross_min_confidence=options["cross_min_confidence"],
            min_table_score=options["min_table_score"],
            split_min_score=options["split_min_score"],
        )

        self.stdout.write(self.style.SUCCESS("=== STAGED HARMONIZATION APPLY PLAN ==="))
        self.stdout.write(f"Master year: {master_year}")
        self.stdout.write(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
        self.stdout.write(f"Tables in batch: {len(plans)}")
        self.stdout.write(f"Include cross-table auto: {include_cross_auto}")
        self.stdout.write("")

        total_master = sum(len(plan.master_columns) for plan in plans)
        total_same = sum(len(plan.same_table_aliases) for plan in plans)
        total_cross = sum(len(plan.cross_table_aliases) for plan in plans)
        self.stdout.write(f"Master self-aliases: {total_master}")
        self.stdout.write(f"Same-table AUTO aliases: {total_same}")
        self.stdout.write(f"Cross-table AUTO aliases: {total_cross}")
        self.stdout.write(f"Potential writes: {total_master + total_same + total_cross}")
        self.stdout.write("")

        for plan in plans:
            self.stdout.write(
                f"- {plan.master_table.nomor_tabel} | {plan.master_table.judul[:90]} | "
                f"master={len(plan.master_columns)} same_auto={len(plan.same_table_aliases)} "
                f"cross_auto={len(plan.cross_table_aliases)}"
            )

        if not apply:
            self.stdout.write("\nDry-run only. Re-run with --apply after backup to write this exact batch.")
            return

        result = defaultdict(int)
        for plan in plans:
            with transaction.atomic():
                table_result = self._apply_table_plan(plan, master_year)
            for key, value in table_result.items():
                result[key] += value
            self.stdout.write(
                f"APPLIED {plan.master_table.nomor_tabel}: "
                f"canonical_created={table_result['canonical_created']} aliases_written={table_result['aliases_written']} "
                f"conflicts_skipped={table_result['conflicts_skipped']}"
            )

        self.stdout.write(self.style.SUCCESS("\n=== APPLY COMPLETE ==="))
        for key in ["canonical_created", "aliases_written", "conflicts_skipped", "unchanged"]:
            self.stdout.write(f"{key}: {result[key]}")

    def _build_plans(
        self,
        *,
        master_pubs,
        master_year,
        table_number,
        max_tables,
        include_cross_auto,
        min_confidence,
        cross_min_confidence,
        min_table_score,
        split_min_score,
    ):
        master_tables_qs = (
            Tabel.objects.filter(bab__publikasi__in=master_pubs)
            .select_related("bab", "bab__publikasi")
            .order_by("nomor_tabel", "id")
        )
        if table_number:
            master_tables_qs = master_tables_qs.filter(nomor_tabel=table_number)
        else:
            max_tables = max(max_tables, 1)
        master_tables = sorted(list(master_tables_qs), key=lambda table: self._table_sort_key(table.nomor_tabel))
        if not table_number:
            master_tables = master_tables[:max_tables]
        if not master_tables:
            raise CommandError("No master tables matched the requested batch.")

        master_cols_by_table = self._columns_by_table(master_year=master_year, master=True)
        legacy_same_by_number = self._legacy_columns_by_table_number(master_year)
        cross_aliases_by_table = defaultdict(list)
        if include_cross_auto:
            cross_aliases_by_table = self._cross_auto_aliases_by_master_table(
                master_tables=master_tables,
                master_columns=master_cols_by_table,
                master_year=master_year,
                min_table_score=min_table_score,
                split_min_score=split_min_score,
                min_confidence=cross_min_confidence,
            )

        plans = []
        for master_table in master_tables:
            master_cols = master_cols_by_table.get(master_table.id, [])
            same_table_aliases = []
            seen = set()
            for master_col in master_cols:
                for legacy_col in legacy_same_by_number.get(master_table.nomor_tabel, []):
                    suggestion = build_suggestion(master_col, legacy_col, min_confidence=min_confidence)
                    if suggestion is None or suggestion.needs_review or suggestion.confidence < 0.90:
                        continue
                    key = (suggestion.canonical_code, suggestion.legacy_column_id, suggestion.table_title_pattern)
                    if key in seen:
                        continue
                    seen.add(key)
                    same_table_aliases.append((suggestion, master_col, legacy_col))

            plans.append(
                TableApplyPlan(
                    master_table=master_table,
                    master_columns=master_cols,
                    same_table_aliases=same_table_aliases,
                    cross_table_aliases=cross_aliases_by_table.get(master_table.id, []),
                )
            )
        return plans

    def _table_sort_key(self, table_number: str):
        parts = []
        for part in table_number.replace("-", ".").split("."):
            try:
                parts.append((0, int(part)))
            except ValueError:
                parts.append((1, part))
        return parts

    def _apply_table_plan(self, plan, master_year):
        result = defaultdict(int)
        canonical_by_master_col = {}
        for master_col in plan.master_columns:
            canonical = find_existing_canonical(master_col)
            if canonical is None:
                canonical, created = CanonicalIndicator.objects.get_or_create(
                    code=canonical_code_for_master(master_col),
                    defaults={
                        "name": master_col.indikator.nama,
                        "topic": master_col.tabel.bab.nama,
                        "description": f"Canonical dari publikasi master {master_year}, tabel {master_col.tabel.nomor_tabel}: {master_col.tabel.judul}",
                        "default_unit": self._unit_for_column(master_col),
                        "preferred_direction": "neutral",
                        "is_active": True,
                    },
                )
                if created:
                    result["canonical_created"] += 1
            canonical_by_master_col[master_col.id] = canonical
            self._write_alias(
                result=result,
                canonical=canonical,
                raw_indicator=master_col.indikator,
                alias_text=master_col.indikator.nama,
                table_title_pattern=alias_context_pattern(master_col, master_col.indikator.nama),
                confidence=Decimal("1.00"),
                approved=True,
                match_type="manual",
                notes=f"Self-alias dari staged apply master year {master_year}.",
            )

        for suggestion, master_col, legacy_col in plan.same_table_aliases + plan.cross_table_aliases:
            canonical = canonical_by_master_col.get(master_col.id) or find_existing_canonical(master_col)
            if canonical is None:
                continue
            self._write_alias(
                result=result,
                canonical=canonical,
                raw_indicator=legacy_col.indikator,
                alias_text=suggestion.alias_text,
                table_title_pattern=suggestion.table_title_pattern,
                confidence=Decimal(str(round(suggestion.confidence, 2))),
                approved=True,
                match_type="contextual" if suggestion.table_title_pattern else "fuzzy",
                notes=(
                    f"AUTO staged apply master {master_year}: master_col={master_col.id}, legacy_col={legacy_col.id}, "
                    f"reasons={','.join(suggestion.reasons)}"
                ),
            )
        return result

    def _write_alias(self, *, result, canonical, raw_indicator, alias_text, table_title_pattern, confidence, approved, match_type, notes):
        normalized_alias = normalize_text(alias_text)
        normalized_pattern = normalize_text(table_title_pattern)
        existing = IndicatorAlias.objects.filter(
            normalized_alias=normalized_alias,
            table_title_pattern=normalized_pattern,
            topic_hint="",
        ).first()
        if existing and existing.canonical_indicator_id != canonical.id:
            result["conflicts_skipped"] += 1
            return
        alias, created = IndicatorAlias.objects.update_or_create(
            normalized_alias=normalized_alias,
            table_title_pattern=normalized_pattern,
            topic_hint="",
            defaults={
                "canonical_indicator": canonical,
                "raw_indicator": raw_indicator,
                "alias_text": alias_text,
                "unit_alias": None,
                "match_type": match_type,
                "confidence": confidence,
                "is_approved": approved,
                "notes": notes,
            },
        )
        result["aliases_written" if created else "unchanged"] += 1

    def _unit_for_column(self, col):
        raw_unit = normalize_text(col.satuan or col.indikator.satuan or "")
        if not raw_unit:
            return None
        alias = UnitAlias.objects.filter(normalized_alias=raw_unit).select_related("canonical_unit").first()
        return alias.canonical_unit if alias else None

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

    def _legacy_columns_by_table_number(self, master_year: int) -> dict[str, list[KolomTabel]]:
        result: dict[str, list[KolomTabel]] = defaultdict(list)
        for col in (
            KolomTabel.objects.exclude(tabel__bab__publikasi__tahun_terbit=master_year)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
            .order_by("tabel__nomor_tabel", "urutan", "id")
        ):
            result[col.tabel.nomor_tabel].append(col)
        return result

    def _cross_auto_aliases_by_master_table(self, *, master_tables, master_columns, master_year, min_table_score, split_min_score, min_confidence):
        legacy_by_year: dict[int, list[Tabel]] = defaultdict(list)
        for table in (
            Tabel.objects.exclude(bab__publikasi__tahun_terbit=master_year)
            .select_related("bab", "bab__publikasi")
            .prefetch_related("kolom_set", "kolom_set__indikator")
        ):
            legacy_by_year[table.bab.publikasi.tahun_terbit].append(table)
        legacy_columns = self._columns_by_table(master_year=master_year, master=False)
        cache = TableSignatureCache()
        result: dict[int, list[tuple]] = defaultdict(list)
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
                            if suggestion is None or suggestion.needs_review or suggestion.confidence < 0.90:
                                continue
                            if best is None or suggestion.confidence > best.confidence:
                                best = suggestion
                        if best is None:
                            continue
                        key = (best.canonical_code, best.legacy_column_id, best.table_title_pattern, best.legacy_table_id)
                        if key in seen:
                            continue
                        seen.add(key)
                        legacy_col = next(col for col in legacy_columns[legacy.id] if col.id == best.legacy_column_id)
                        result[master.id].append((best, master_col, legacy_col))
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
