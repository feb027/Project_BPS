from django.core.management.base import BaseCommand
from django.test import Client
from apps.katalog.models import Tabel
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        c = Client()
        for tabel in Tabel.objects.order_by('id'):
            print(f"Testing {tabel.pk}...", end='', flush=True)
            start = time.time()
            try:
                c.get(f'/data/tabel/{tabel.pk}/')
            except Exception as e:
                print(f" Error: {e}", flush=True)
                continue
                
            duration = time.time() - start
            print(f" {duration:.2f}s", flush=True)
