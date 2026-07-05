from django.core.management.base import BaseCommand
from apps.katalog.models import Bab, Tabel, Publikasi
from django.db.models import Count
import time
from django.db import connection

class Command(BaseCommand):
    def handle(self, *args, **options):
        # 1. Test Bab
        bab = Bab.objects.annotate(c=Count('tabel_set')).order_by('-c').first()
        if bab:
            print(f"Max bab: {bab.nama}, tables: {bab.c}")
            start = time.time()
            tabel_list = list(bab.tabel_set.annotate(jml=Count('fakta_set')).order_by('nomor_tabel'))
            print(f"Time to fetch tabel_list: {time.time() - start}")

        # 2. Test Publikasi
        pub = Publikasi.objects.annotate(c=Count('bab_set')).order_by('-c').first()
        if pub:
            print(f"Max pub: {pub.judul}, babs: {pub.c}")
            start = time.time()
            bab_list = list(pub.bab_set.annotate(jml_tabel=Count("tabel_set")).order_by("nomor"))
            print(f"Time to fetch bab_list: {time.time() - start}")
            
        # 3. Print slow queries
        for q in connection.queries:
            if float(q['time']) > 0.05:
                print(f"Slow query ({q['time']}s): {q['sql'][:200]}")
