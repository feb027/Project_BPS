from django.core.management.base import BaseCommand
from apps.data.models import Fakta

class Command(BaseCommand):
    help = 'Mengecek anomali data (lonjakan/penurunan drastis) dan menandainya'

    def handle(self, *args, **options):
        self.stdout.write('Memulai pengecekan anomali data...')
        
        fakta_qs = Fakta.objects.filter(nilai_num__isnull=False).order_by('kolom_id', 'wilayah_id', 'rincian_id', 'tahun')
        
        last_fakta = None
        anomali_ditemukan = 0
        batch = []
        
        for f in fakta_qs.iterator(chunk_size=5000):
            if (last_fakta 
                and last_fakta.kolom_id == f.kolom_id 
                and last_fakta.wilayah_id == f.wilayah_id 
                and last_fakta.rincian_id == f.rincian_id
                and last_fakta.tahun is not None
                and f.tahun is not None
                and f.tahun > last_fakta.tahun):
                
                if last_fakta.nilai_num != 0:
                    perubahan = abs((f.nilai_num - last_fakta.nilai_num) / last_fakta.nilai_num)
                    if perubahan > 0.5: # > 50%
                        if f.flag != 'perlu_cek':
                            f.flag = 'perlu_cek'
                            batch.append(f)
            last_fakta = f
            
            if len(batch) >= 1000:
                Fakta.objects.bulk_update(batch, ['flag'])
                anomali_ditemukan += len(batch)
                self.stdout.write(f'Menemukan {anomali_ditemukan} anomali...')
                batch = []
                
        if batch:
            Fakta.objects.bulk_update(batch, ['flag'])
            anomali_ditemukan += len(batch)
            
        self.stdout.write(self.style.SUCCESS(f'Selesai! {anomali_ditemukan} data ditandai sebagai anomali (Perlu Cek).'))
