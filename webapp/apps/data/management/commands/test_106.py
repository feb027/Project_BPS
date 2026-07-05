from apps.katalog.models import Tabel
tabel = Tabel.objects.get(pk=106)
print(f"Table 106: {tabel.nomor_tabel} - {tabel.judul}")
print(f"tipe_baris: {tabel.tipe_baris}")
print(f"bab: {tabel.bab.nama}")
print(f"kolom count: {tabel.kolom_set.count()}")
print(f"fakta count: {tabel.fakta_set.count()}")

import time
start = time.time()
print("Fetching next_tabel...", end='')
nx = tabel.next_tabel
print(f" {time.time() - start:.2f}s")

start = time.time()
print("Fetching prev_tabel...", end='')
pv = tabel.prev_tabel
print(f" {time.time() - start:.2f}s")

from apps.data.models import Fakta
start = time.time()
print("Fetching fakta list...", end='')
fakta = list(Fakta.objects.filter(tabel=tabel).select_related("wilayah", "rincian", "kolom"))
print(f" {time.time() - start:.2f}s")
