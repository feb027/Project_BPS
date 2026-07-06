from collections import Counter
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.data.harmonization import (
    alias_context_pattern,
    build_suggestion,
    canonical_code_for_master,
    find_existing_canonical,
    is_generic_indicator,
    normalize_text,
)
from apps.data.models import CanonicalIndicator, IndicatorAlias, UnitAlias
from apps.katalog.models import KolomTabel, Publikasi


class Command(BaseCommand):
    help = "Suggest legacy indicator aliases against a master publication year. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--master-year", type=int, default=2026)
        parser.add_argument("--min-confidence", type=float, default=0.75)
        parser.add_argument("--examples", type=int, default=30)
        parser.add_argument("--apply", action="store_true", help="Create/update CanonicalIndicator and IndicatorAlias rows.")
        parser.add_argument("--include-review", action="store_true", help="When applying, also write review-band suggestions (<0.90) as unapproved aliases.")

    def handle(self, *args, **options):
        master_year = options["master_year"]
        min_confidence = options["min_confidence"]
        examples = options["examples"]
        apply = options["apply"]
        include_review = options["include_review"]

        master_pubs = Publikasi.objects.filter(tahun_terbit=master_year)
        if not master_pubs.exists():
            raise CommandError(f"No publication found for master year {master_year}")

        master_cols = list(
            KolomTabel.objects.filter(tabel__bab__publikasi__in=master_pubs)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
            .order_by("tabel__nomor_tabel", "urutan", "id")
        )
        legacy_cols = list(
            KolomTabel.objects.exclude(tabel__bab__publikasi__tahun_terbit=master_year)
            .select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "indikator")
            .order_by("tabel__nomor_tabel", "urutan", "id")
        )

        suggestions = []
        seen = set()
        for master_col in master_cols:
            same_table_legacy = [col for col in legacy_cols if col.tabel.nomor_tabel == master_col.tabel.nomor_tabel]
            for legacy_col in same_table_legacy:
                suggestion = build_suggestion(master_col, legacy_col, min_confidence=min_confidence)
                if suggestion is None:
                    continue
                key = (
                    suggestion.canonical_code,
                    normalize_text(suggestion.alias_text),
                    suggestion.table_title_pattern,
                    legacy_col.indikator_id,
                )
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append((suggestion, master_col, legacy_col))

        confidence_counter = Counter(
            "auto" if s.confidence >= 0.90 and not s.needs_review else "review"
            for s, _, _ in suggestions
        )
        generic_counter = Counter(is_generic_indicator(legacy_col.indikator.nama) for _, _, legacy_col in suggestions)

        self.stdout.write(self.style.SUCCESS("=== INDICATOR ALIAS SUGGESTIONS ==="))
        self.stdout.write(f"Master year: {master_year}")
        self.stdout.write(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
        self.stdout.write(f"Min confidence: {min_confidence:.2f}")
        self.stdout.write(f"Suggestions total: {len(suggestions)}")
        self.stdout.write(f"Auto-band suggestions: {confidence_counter['auto']}")
        self.stdout.write(f"Needs-review suggestions: {confidence_counter['review']}")
        self.stdout.write(f"Generic/year-like aliases: {generic_counter[True]}")

        if suggestions:
            self.stdout.write("\n=== EXAMPLES ===")
            for suggestion, master_col, legacy_col in suggestions[:examples]:
                mode = "AUTO" if suggestion.confidence >= 0.90 and not suggestion.needs_review else "REVIEW"
                self.stdout.write(
                    f"  - {mode} {suggestion.confidence:.2f} -> {suggestion.canonical_code} | "
                    f"alias={suggestion.alias_text!r} pattern={suggestion.table_title_pattern!r} | "
                    f"MASTER {master_col.tabel.nomor_tabel}#{master_col.urutan} {master_col.indikator.nama!r} | "
                    f"LEGACY {legacy_col.tabel.bab.publikasi.tahun_terbit} {legacy_col.tabel.nomor_tabel}#{legacy_col.urutan} {legacy_col.indikator.nama!r} | "
                    f"{','.join(suggestion.reasons)}"
                )

        if not apply:
            self.stdout.write("\nDry-run only. Re-run with --apply to write approved high-confidence aliases.")
            return

        with transaction.atomic():
            created_indicators = 0
            written_aliases = 0
            skipped_review = 0
            for suggestion, master_col, legacy_col in suggestions:
                is_auto = suggestion.confidence >= 0.90 and not suggestion.needs_review
                if not is_auto and not include_review:
                    skipped_review += 1
                    continue

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
                        created_indicators += 1
                    # Master self-alias supaya master column ikut tercatat.
                    self._write_alias(
                        canonical=canonical,
                        raw_indicator=master_col.indikator,
                        alias_text=master_col.indikator.nama,
                        table_title_pattern=alias_context_pattern(master_col, master_col.indikator.nama),
                        confidence=Decimal("1.00"),
                        approved=True,
                        match_type="manual",
                        notes=f"Self-alias dari master year {master_year}.",
                    )

                self._write_alias(
                    canonical=canonical,
                    raw_indicator=legacy_col.indikator,
                    alias_text=suggestion.alias_text,
                    table_title_pattern=suggestion.table_title_pattern,
                    confidence=Decimal(str(round(suggestion.confidence, 2))),
                    approved=is_auto,
                    match_type="contextual" if suggestion.table_title_pattern else "fuzzy",
                    notes=(
                        f"Suggested dari master {master_year}: master_col={master_col.id}, legacy_col={legacy_col.id}, "
                        f"reasons={','.join(suggestion.reasons)}"
                    ),
                )
                written_aliases += 1

        self.stdout.write(self.style.SUCCESS("\n=== APPLY COMPLETE ==="))
        self.stdout.write(f"Canonical indicators created: {created_indicators}")
        self.stdout.write(f"Aliases written: {written_aliases}")
        self.stdout.write(f"Review-band skipped: {skipped_review}")

    def _unit_for_column(self, col):
        raw_unit = normalize_text(col.satuan or col.indikator.satuan or "")
        if not raw_unit:
            return None
        alias = UnitAlias.objects.filter(normalized_alias=raw_unit).select_related("canonical_unit").first()
        return alias.canonical_unit if alias else None

    def _write_alias(self, *, canonical, raw_indicator, alias_text, table_title_pattern, confidence, approved, match_type, notes):
        IndicatorAlias.objects.update_or_create(
            normalized_alias=normalize_text(alias_text),
            table_title_pattern=normalize_text(table_title_pattern),
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
