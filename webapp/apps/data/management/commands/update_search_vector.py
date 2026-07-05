from django.core.management.base import BaseCommand
from django.contrib.postgres.search import SearchVector
from apps.data.models import Fakta

class Command(BaseCommand):
    help = 'Memperbarui SearchVector untuk semua Fakta'

    def handle(self, *args, **options):
        self.stdout.write('Memulai update search_vector untuk Fakta...')
        
        vector = (
            SearchVector("kolom__indikator__nama", weight="A")
            + SearchVector("wilayah__nama", weight="A")
            + SearchVector("tabel__judul", weight="B")
            + SearchVector("tabel__nama_ringkas", weight="B")
            + SearchVector("rincian__nama", weight="C")
            + SearchVector("nilai_teks", weight="D")
        )
        
        # Lakukan update secara massal
        qs = Fakta.objects.annotate(vector=vector)
        batch = []
        count = 0
        for f in qs.iterator(chunk_size=5000):
            f.search_vector = f.vector
            batch.append(f)
            if len(batch) >= 5000:
                Fakta.objects.bulk_update(batch, ['search_vector'])
                count += len(batch)
                self.stdout.write(f'Updated {count} records...')
                batch = []
        
        if batch:
            Fakta.objects.bulk_update(batch, ['search_vector'])
            count += len(batch)
            self.stdout.write(f'Updated {count} records...')
        
        self.stdout.write(self.style.SUCCESS('Selesai memperbarui search_vector!'))
