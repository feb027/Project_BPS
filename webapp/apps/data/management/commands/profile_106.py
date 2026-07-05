from django.core.management.base import BaseCommand
from django.test import Client
import time
import cProfile
import pstats
import io

class Command(BaseCommand):
    def handle(self, *args, **options):
        c = Client()
        pr = cProfile.Profile()
        pr.enable()
        
        c.get('/data/tabel/106/')
        
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumtime')
        ps.print_stats(20)
        print(s.getvalue())
