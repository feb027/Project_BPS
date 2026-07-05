import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.append('c:\\projects\\Project_BPS\\webapp')
django.setup()

from apps.data.models import Fakta
import re

qs = Fakta.objects.filter(nilai_num__isnull=True).exclude(nilai_teks__in=['-', 'NA', 'N/A', 'n/a', '...', ''])
count = 0
for f in qs[:50]:
    print(f.nilai_teks)
        
print("Total fixable:", count)
