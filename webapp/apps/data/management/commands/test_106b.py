from django.core.management.base import BaseCommand
from django.test import Client

class Command(BaseCommand):
    def handle(self, *args, **options):
        c = Client()
        print("Getting /data/tabel/106/ ...")
        c.get('/data/tabel/106/')
        print("Done!")
