from apps.katalog.models import Tabel
from django.db.models import Count
top_kolom = Tabel.objects.annotate(c=Count('kolom_set')).order_by('-c').first()
print(f"Max columns in a table: {top_kolom.c} (Tabel ID: {top_kolom.id})")
