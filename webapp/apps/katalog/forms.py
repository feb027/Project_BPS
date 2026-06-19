from django import forms

from .models import Bab, Publikasi, Tabel


class PublikasiForm(forms.ModelForm):
    class Meta:
        model = Publikasi
        fields = ["judul", "tahun_terbit", "wilayah_cakupan", "jenis", "catatan"]


class BabForm(forms.ModelForm):
    class Meta:
        model = Bab
        fields = ["nomor", "nama"]


class TabelForm(forms.ModelForm):
    class Meta:
        model = Tabel
        fields = ["nomor_tabel", "nama_ringkas", "judul", "judul_en", "tipe_baris",
                  "sumber", "tahun_data"]
        widgets = {
            "judul": forms.Textarea(attrs={"rows": 2}),
            "judul_en": forms.Textarea(attrs={"rows": 2}),
        }
