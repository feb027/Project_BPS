"""
Merge indikator duplikat konsep di 4.1.8 (SMK) ke kanonik.
Map: old -> canonical
 451 'Guru'            -> 852 'Guru Jumlah'
 452 'Murid'           -> 855 'Murid Jumlah'
 450 'Sekolah'         -> 846 'Sekolah Jumlah'
 1485 'Rasio Murid- Guru' -> 1117 'Rasio Murid-Guru'
Untuk Rasio: set satuan kolom lama ke '%' biar 1 series.
"""
from apps.referensi.models import Indikator
from apps.katalog.models import KolomTabel

MAP = {451: 852, 452: 855, 450: 846, 1485: 1117}
# satuan target untuk pasangan yang beda unit
SATUAN = {1485: "%"}

print(f"=== MERGE INDIKATOR 4.1.8 | DRY={DRY} ===")
for old_id, new_id in MAP.items():
    old = Indikator.objects.get(id=old_id)
    new = Indikator.objects.get(id=new_id)
    n_kol = KolomTabel.objects.filter(indikator=old).count()
    n_fakta = sum(
        KolomTabel.objects.filter(indikator=old).aggregate(models.Count("fakta_set"))[
            "fakta_set__count"
        ]
        for _ in [0]
    ) if False else None
    print(f"  {old.nama!r} ({old_id}) -> {new.nama!r} ({new_id}) | kolom={n_kol}")
    if not DRY:
        # set satuan kolom lama bila perlu
        if old_id in SATUAN:
            KolomTabel.objects.filter(indikator=old).exclude(satuan=SATUAN[old_id]).update(
                satuan=SATUAN[old_id]
            )
        KolomTabel.objects.filter(indikator=old).update(indikator=new)
        old.delete()
print(">>> selesai")
