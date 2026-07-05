from django.core.management.base import BaseCommand
from django.test import Client
from apps.katalog.models import Tabel
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        c = Client()
        from django.db.models import Count
        for tabel in Tabel.objects.annotate(c=Count('fakta_set')).order_by('-c')[:10]:
            start = time.time()
            c.get(f'/data/tabel/{tabel.pk}/isi/')
            duration = time.time() - start
            if duration > 1.0:
                print(f"Tabel isi {tabel.pk} ({tabel.nomor_tabel}) took {duration:.2f}s")
                
        print("Done testing isi.")
