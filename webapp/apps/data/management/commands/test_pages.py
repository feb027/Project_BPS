from django.core.management.base import BaseCommand
from django.test import Client
from apps.katalog.models import Publikasi, Bab, Tabel
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        c = Client()
        
        # Test all publikasi
        for pub in Publikasi.objects.all():
            start = time.time()
            c.get(f'/data/pub/{pub.pk}/')
            duration = time.time() - start
            if duration > 1.0:
                print(f"Publikasi {pub.pk} ({pub.tahun_terbit}) took {duration:.2f}s")
                
        # Test all bab
        for bab in Bab.objects.all():
            start = time.time()
            c.get(f'/data/bab/{bab.pk}/')
            duration = time.time() - start
            if duration > 1.0:
                print(f"Bab {bab.pk} ({bab.nama}) took {duration:.2f}s")
                
        # Test top 5 tabel (by fakta count)
        from django.db.models import Count
        for tabel in Tabel.objects.annotate(c=Count('fakta_set')).order_by('-c')[:5]:
            start = time.time()
            c.get(f'/data/tabel/{tabel.pk}/')
            duration = time.time() - start
            if duration > 1.0:
                print(f"Tabel {tabel.pk} ({tabel.nomor_tabel}) took {duration:.2f}s")
                
        print("Done testing.")
