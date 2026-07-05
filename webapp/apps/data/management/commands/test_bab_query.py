from django.core.management.base import BaseCommand
from django.db import connection
from apps.katalog.models import Bab
from django.db.models import Count
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        bab = Bab.objects.first()
        start = time.time()
        print(f"Executing query for bab {bab.pk}...")
        list(bab.tabel_set.annotate(from_django=Count("fakta_set")).order_by("nomor_tabel"))
        print(f"Query took {time.time() - start:.2f}s")
        print(connection.queries[-1])
