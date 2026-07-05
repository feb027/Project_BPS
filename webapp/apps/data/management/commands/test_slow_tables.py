from django.core.management.base import BaseCommand
from django.test import Client
from apps.katalog.models import Tabel
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        c = Client()
        for tabel in Tabel.objects.order_by('id'):
            start = time.time()
            try:
                c.get(f'/data/tabel/{tabel.pk}/')
            except Exception as e:
                print(f"Error on tabel {tabel.pk}: {e}", flush=True)
                
            duration = time.time() - start
            if duration > 0.5:
                print(f"SLOW: Tabel {tabel.pk} ({tabel.nomor_tabel}) took {duration:.2f}s", flush=True)
