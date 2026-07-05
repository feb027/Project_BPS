from rest_framework import serializers
from apps.katalog.models import Tabel, KolomTabel
from apps.referensi.models import Indikator, Wilayah, Rincian
from apps.data.models import Fakta

class IndikatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indikator
        fields = ['id', 'nama']

class TabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tabel
        fields = ['id', 'nomor_tabel', 'nama_ringkas', 'judul', 'sumber', 'tahun_data']

class FaktaTimeSeriesSerializer(serializers.ModelSerializer):
    """
    Serializer khusus untuk output grafik Time Series.
    Menghindari N+1 dengan bergantung pada View untuk memanggil select_related.
    """
    wilayah_nama = serializers.CharField(source='wilayah.nama', read_only=True, default="-")
    rincian_nama = serializers.CharField(source='rincian.nama', read_only=True, default="-")
    tahun = serializers.IntegerField(source='tahun_lengkap', read_only=True)
    nilai = serializers.DecimalField(source='nilai_num', max_digits=24, decimal_places=4, read_only=True)

    class Meta:
        model = Fakta
        fields = ['id', 'tahun', 'nilai', 'nilai_teks', 'wilayah_nama', 'rincian_nama', 'flag']
