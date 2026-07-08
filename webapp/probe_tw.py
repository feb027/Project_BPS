import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from apps.referensi.models import Indikator
from apps.data.models import Fakta
from apps.katalog.models import Tabel

print("=== indicators containing 'tinggi wilayah' ===")
for ind in Indikator.objects.filter(nama__icontains="tinggi wilayah"):
    print(ind.id, repr(ind.nama), "| satuan:", repr(ind.satuan))

print("\n=== tables nomor 11.2 ===")
for t in Tabel.objects.filter(nomor_tabel="11.2"):
    print(t.id, t.nomor_tabel, "|", t.judul[:70])

print("\n=== a sample fakta for nomor 11.2 (by table join) ===")
t = Tabel.objects.filter(nomor_tabel="11.2").first()
if t:
    rows = Fakta.objects.filter(tabel=t, nilai_num__isnull=False).select_related('wilayah','rincian','kolom__indikator').order_by('tahun','id')[:8]
    for f in rows:
        print(f.id, "year=", f.tahun_lengkap, "wilayah=", f.wilayah.nama if f.wilayah else None,
              "rincian=", (f.rincian.nama if f.rincian else None),
              "ind=", f.kolom.indikator.nama if f.kolom and f.kolom.indikator else None,
              "nilai=", f.nilai_num, "sat=", f.kolom.satuan if f.kolom else None)
    print("distinct wilayah count:", Fakta.objects.filter(tabel=t, nilai_num__isnull=False).values('wilayah_id').distinct().count())
    print("distinct rincian count:", Fakta.objects.filter(tabel=t, nilai_num__isnull=False).values('rincian_id').distinct().count())
