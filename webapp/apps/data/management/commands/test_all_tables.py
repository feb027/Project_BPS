from django.core.management.base import BaseCommand
from django.test import Client
from apps.katalog.models import Tabel
import time
import sys

class Command(BaseCommand):
    def handle(self, *args, **options):
        c = Client()
        print("Testing all tables...", flush=True)
        count = 0
        slow_tables = []
        for tabel in Tabel.objects.all():
            start = time.time()
            try:
                c.get(f'/data/tabel/{tabel.pk}/')
            except Exception as e:
                print(f"Error on tabel {tabel.pk}: {e}", flush=True)
                
            duration = time.time() - start
            if duration > 1.0:
                print(f"Tabel {tabel.pk} ({tabel.nomor_tabel}) took {duration:.2f}s", flush=True)
                slow_tables.append(tabel.pk)
            count += 1
            if count % 100 == 0:
                print(f"Tested {count} tables...", flush=True)
                
        print(f"Done testing. Slow tables: {slow_tables}", flush=True)
