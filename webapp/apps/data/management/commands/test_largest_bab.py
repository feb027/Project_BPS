from django.core.management.base import BaseCommand
from django.db import connection
from apps.katalog.models import Bab
from django.db.models import Count
from django.test import Client
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        bab = Bab.objects.annotate(c=Count('tabel')).order_by('-c').first()
        print(f"Bab {bab.pk} has {bab.c} tables.")
        
        c = Client()
        start = time.time()
        c.get(f'/data/bab/{bab.pk}/')
        print(f"Page load took {time.time() - start:.2f}s")
