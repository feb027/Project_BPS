from django.core.management.base import BaseCommand
from apps.data.models import Fakta

class Command(BaseCommand):
    def handle(self, *args, **options):
        qs = Fakta.objects.filter(
            wilayah__nama__icontains='Cisayong',
            kolom__isnull=False
        ).select_related('kolom__indikator', 'wilayah', 'tabel__bab__publikasi')

        data_points = []
        for f in qs:
            ind = f.kolom.indikator.nama if f.kolom.indikator else '-'
            if 'penduduk' in ind.lower() or 'luas' in ind.lower():
                tahun = f.tahun_lengkap
                data_points.append({
                    'tahun': tahun,
                    'indikator': ind,
                    'nilai': f.nilai_num
                })

        if not data_points:
            print("Data tidak ditemukan.")
        else:
            print(f"{'Tahun':<6} | {'Indikator':<45} | {'Nilai':<10}")
            print("-" * 70)
            for d in sorted(data_points, key=lambda x: (str(x['indikator']), str(x['tahun']))):
                print(f"{str(d['tahun']):<6} | {str(d['indikator'])[:43]:<45} | {str(d['nilai']):<10}")
