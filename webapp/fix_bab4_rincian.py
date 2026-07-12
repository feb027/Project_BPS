"""
Cleanup normalisasi subject (Rincian) untuk Bab 4.1 Pendidikan.
Gabungkan varian label jenjang ke kanonik bersih.

Dry-run: DRY=True. Eksekusi: DRY=False.
"""
from apps.referensi.models import Rincian
from apps.data.models import Fakta

# mapping: kanonik_nama -> [list id rincian lama yang di-merge]
MAP = {
    "SD/MI":        [1158, 2104, 300, 969],
    "SMP/MTs":      [2128, 2292, 1159, 2105, 301, 970],
    "SMA/SMK/MA":   [1160, 2106, 2127, 302, 971],
}

print(f"=== CLEANUP RINCIAN 4.1.x | DRY={DRY} ===")
total_pindah = 0
for kanonik_nama, lama_ids in MAP.items():
    # buat/ambil kanonik
    kanonik, _ = Rincian.objects.get_or_create(nama=kanonik_nama, kelompok="")
    print(f"\nKanonik '{kanonik_nama}' (id {kanonik.id}):")
    for rid in lama_ids:
        try:
            lama = Rincian.objects.get(id=rid)
        except Rincian.DoesNotExist:
            print(f"  id {rid}: tidak ada (skip)"); continue
        n = Fakta.objects.filter(rincian=lama).count()
        if n == 0:
            print(f"  id {rid} '{lama.nama}': kosong (hapus)")
            if not DRY:
                lama.delete()
            continue
        # pindah fakta ke kanonik
        if not DRY:
            Fakta.objects.filter(rincian=lama).update(rincian=kanonik)
            # jangan hapus bila rincian lama adalah kanonik itu sendiri
            if lama.id != kanonik.id and Fakta.objects.filter(rincian=lama).count() == 0:
                lama.delete()
        total_pindah += n
        print(f"  id {rid} '{lama.nama}': {n} fakta -> '{kanonik_nama}'")

print(f"\n>>> {'DRY RUN' if DRY else 'EKSEKUSI'} | total fakta dipindah: {total_pindah}")
