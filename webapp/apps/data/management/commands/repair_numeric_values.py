from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.data.models import Fakta
from apps.data.utils import decimal_differs, normalize_numeric


class Command(BaseCommand):
    help = "Repair stored nilai_num from nilai_teks using current numeric normalization rules. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--publication-year", type=int, default=0)
        parser.add_argument("--table-number", type=str, default="")
        parser.add_argument("--indicator", type=str, default="", help="Case-insensitive substring of raw indicator name.")
        parser.add_argument("--unit", type=str, default="", help="Exact normalized unit-ish substring, e.g. km2.")
        parser.add_argument("--title-contains", type=str, default="", help="Case-insensitive substring of table title.")
        parser.add_argument("--raw-regex", type=str, default="", help="Regex filter for raw nilai_teks.")
        parser.add_argument(
            "--scale-factor",
            type=str,
            default="1",
            help="Multiply normalized value before comparing/applying, e.g. 1000 for legacy ribu-rupiah rows.",
        )
        parser.add_argument("--min-ratio", type=float, default=0.0, help="Only repair when max(old,new)/min(old,new) is >= this value.")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--examples", type=int, default=20)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        qs = Fakta.objects.select_related("tabel", "tabel__bab", "tabel__bab__publikasi", "kolom", "kolom__indikator", "wilayah", "rincian")
        if options["publication_year"]:
            qs = qs.filter(tabel__bab__publikasi__tahun_terbit=options["publication_year"])
        if options["table_number"]:
            qs = qs.filter(tabel__nomor_tabel=options["table_number"])
        if options["indicator"]:
            qs = qs.filter(kolom__indikator__nama__icontains=options["indicator"])
        if options["unit"]:
            qs = qs.filter(kolom__satuan__icontains=options["unit"])
        if options["title_contains"]:
            qs = qs.filter(tabel__judul__icontains=options["title_contains"])
        if options["raw_regex"]:
            qs = qs.filter(nilai_teks__regex=options["raw_regex"])
        qs = qs.exclude(nilai_teks="").order_by("tabel__bab__publikasi__tahun_terbit", "tabel__nomor_tabel", "id")
        if options["limit"]:
            qs = qs[: options["limit"]]

        min_ratio = Decimal(str(options["min_ratio"])) if options["min_ratio"] else Decimal("0")
        scale_factor = Decimal(str(options["scale_factor"]))
        repairs = []
        skipped_ratio = 0
        for fakta in qs:
            raw_unit = (fakta.kolom.satuan or fakta.kolom.indikator.satuan or "") if fakta.kolom_id else ""
            normalized, status = normalize_numeric(fakta.nilai_teks, raw_unit)
            if normalized is not None and scale_factor != Decimal("1"):
                normalized *= scale_factor
                status = f"{status}*{scale_factor}"
            if normalized is None or not decimal_differs(normalized, fakta.nilai_num):
                continue
            ratio = self._ratio(fakta.nilai_num, normalized)
            if min_ratio and ratio < min_ratio:
                skipped_ratio += 1
                continue
            repairs.append((fakta, normalized, status, ratio))

        self.stdout.write(self.style.SUCCESS("=== NUMERIC VALUE REPAIR ==="))
        self.stdout.write(f"Mode: {'APPLY' if options['apply'] else 'DRY-RUN'}")
        self.stdout.write(f"Candidate repairs: {len(repairs)}")
        self.stdout.write(f"Skipped by ratio: {skipped_ratio}")
        self.stdout.write("")
        for fakta, normalized, status, ratio in repairs[: options["examples"]]:
            subject = fakta.wilayah.nama if fakta.wilayah_id else (fakta.rincian.nama if fakta.rincian_id else "-")
            self.stdout.write(
                f"  - id={fakta.id} ratio={ratio} {status} | {fakta.tabel.bab.publikasi.tahun_terbit} "
                f"{fakta.tabel.nomor_tabel} {subject} | raw={fakta.nilai_teks!r} stored={fakta.nilai_num} -> {normalized} | "
                f"{fakta.kolom.indikator.nama} {fakta.kolom.satuan}"
            )

        if not options["apply"]:
            self.stdout.write("\nDry-run only. Re-run with --apply to update nilai_num.")
            return

        with transaction.atomic():
            for fakta, normalized, status, ratio in repairs:
                fakta.nilai_num = normalized
                fakta.save(update_fields=["nilai_num", "diubah_pada"])
        self.stdout.write(self.style.SUCCESS(f"\nUpdated rows: {len(repairs)}"))

    def _ratio(self, old, new):
        if old in (None, 0) or new in (None, 0):
            return Decimal("0")
        old = abs(Decimal(str(old)))
        new = abs(Decimal(str(new)))
        low = min(old, new)
        if low == 0:
            return Decimal("0")
        return (max(old, new) / low).quantize(Decimal("0.01"))
