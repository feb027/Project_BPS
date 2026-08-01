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
        fields = ['id', 'nomor_tabel', 'nama_ringkas', 'judul', 'sumber', 'tahun_data', 'tipe_baris']
class FaktaTimeSeriesSerializer(serializers.ModelSerializer):
    """
    Serializer khusus untuk output grafik Time Series.
    Menghindari N+1 dengan bergantung pada View untuk memanggil select_related.

    Nihil ("-") diperlakukan sebagai 0 agar garis time-series menyambung
    (bukan putus/null). Flag 'tidak_tersedia' sudah di-exclude di view.
    """

    wilayah_nama = serializers.CharField(source='wilayah.nama', read_only=True, default="-")
    rincian_nama = serializers.SerializerMethodField()
    tahun = serializers.IntegerField(source='tahun_lengkap', read_only=True)
    nilai = serializers.SerializerMethodField()

    def get_rincian_nama(self, obj):
        from apps.pencarian.api_views import _resolve_rincian_alias
        raw = obj.rincian.nama if obj.rincian else "-"
        title = obj.tabel.judul if obj.tabel_id else ""
        return _resolve_rincian_alias(raw, title)

    def get_nilai(self, obj):
        # nihil / null -> 0 supaya chart tidak putus
        return float(obj.nilai_num or 0)

    class Meta:
        model = Fakta
        fields = ['id', 'tahun', 'nilai', 'nilai_teks', 'wilayah_nama', 'rincian_nama', 'flag']
