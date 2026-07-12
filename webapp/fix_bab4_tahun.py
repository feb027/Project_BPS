"""
Perbaiki tahun_data + fakta.tahun untuk sub-bab Bab 4 Pendidikan.
Aturan: tahun data = publikasi.tahun_terbit - 1 (Susenas/statistik BPS Tasikmalaya).

Penggunaan:
  python manage.py shell -c "NOMOR='4.1.1'; DRY=True; exec(open('fix_bab4_tahun.py').read())"
  python manage.py shell -c "NOMOR='4.1.1'; DRY=False; exec(open('fix_bab4_tahun.py').read())"
"""
from apps.katalog.models import Tabel
from apps.data.models import Fakta

assert NOMOR.startswith("4.1."), "Hanya untuk sub-bab 4.1.x"

tabs = list(
    Tabel.objects.filter(bab__nomor=4, nomor_tabel=NOMOR).select_related("bab__publikasi")
)
print(f"=== FIX TAHUN {NOMOR} | {len(tabs)} edisi ===")

total_fakta = 0
for t in sorted(tabs, key=lambda x: x.bab.publikasi.tahun_terbit):
    pub = t.bab.publikasi.tahun_terbit
    baru = pub - 1
    faks = Fakta.objects.filter(tabel=t)
    n = faks.count()
    ubah = faks.exclude(tahun=baru).count()
    tabel_ubah = t.tahun_data != baru
    print(
        f"  pub {pub} | tabel {t.id} | thn_data {t.tahun_data}->{baru if tabel_ubah else t.tahun_data} | "
        f"fakta {n} | ubah {ubah}"
    )
    if not DRY:
        if tabel_ubah:
            t.tahun_data = baru
            t.save(update_fields=["tahun_data"])
        if ubah:
            faks.exclude(tahun=baru).update(tahun=baru)
            # sinkron kolom.tahun juga biar konsisten
            for k in t.kolom_set.all():
                if k.tahun != baru:
                    k.tahun = baru
                    k.save(update_fields=["tahun"])
    total_fakta += ubah

print(f"\n>>> {'DRY RUN' if DRY else 'EKSEKUSI'} | fakta di-set tahun: {total_fakta}")
