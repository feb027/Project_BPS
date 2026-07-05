import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.katalog.models import Publikasi, Tabel
from apps.katalog.sync_views import norm_title

pub_2026 = Publikasi.objects.filter(tahun_terbit=2026).first()
pub_2025 = Publikasi.objects.filter(tahun_terbit=2025).first()

if pub_2026 and pub_2025:
    tables_2026 = Tabel.objects.filter(bab__publikasi=pub_2026)
    tables_2025 = Tabel.objects.filter(bab__publikasi=pub_2025)
    
    dict_2025 = {norm_title(t.judul): t for t in tables_2025}
    
    synced_tables = 0
    unsynced_tables = []
    
    for t26 in tables_2026:
        n26 = norm_title(t26.judul)
        if n26 in dict_2025:
            t25 = dict_2025[n26]
            # Check if columns are synced (i.e., share the same Indikator IDs)
            inds_26 = set(t26.kolom_set.values_list('indikator_id', flat=True))
            inds_25 = set(t25.kolom_set.values_list('indikator_id', flat=True))
            
            # If there's an overlap, it means some columns are synced
            if inds_26.intersection(inds_25):
                synced_tables += 1
            else:
                unsynced_tables.append(t26.judul)
        else:
            unsynced_tables.append(t26.judul)

    print(f"Total Tables in 2026: {tables_2026.count()}")
    print(f"Synced Tables (share indicators with 2025): {synced_tables}")
    print(f"Unsynced Tables: {len(unsynced_tables)}")
    
    print("\nSample of Unsynced Tables:")
    for t in unsynced_tables[:10]:
        print(f"- {t}")
