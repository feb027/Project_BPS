"""
Impor CSV format LONG ke database.

Contoh:
  py manage.py import_long_csv ../output/bab1_geografi_long.csv \
      --publikasi "Kabupaten Tasikmalaya Dalam Angka 2026" --tahun 2026
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.data.services import ingest_long_rows
from apps.katalog.models import Publikasi


class Command(BaseCommand):
    help = "Impor satu file CSV format long ke dalam database."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument("--publikasi", required=True, help="Judul publikasi")
        parser.add_argument("--tahun", type=int, required=True, help="Tahun terbit")

    def handle(self, *args, **opts):
        path = Path(opts["csv_path"])
        if not path.exists():
            raise CommandError(f"File tidak ditemukan: {path}")

        publikasi, dibuat = Publikasi.objects.get_or_create(
            judul=opts["publikasi"], tahun_terbit=opts["tahun"],
        )
        kata = "dibuat" if dibuat else "dipakai"
        self.stdout.write(f"Publikasi {kata}: {publikasi}")

        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

        hasil = ingest_long_rows(rows, publikasi=publikasi)
        self.stdout.write(self.style.SUCCESS(
            f"Selesai. Fakta baru={hasil.fakta_baru}, diperbarui={hasil.fakta_diperbarui}, "
            f"tabel={hasil.tabel}, indikator={hasil.indikator}, "
            f"wilayah={hasil.wilayah}, rincian={hasil.rincian}"
        ))
