from django.contrib import admin

from .models import Fakta


@admin.register(Fakta)
class FaktaAdmin(admin.ModelAdmin):
    list_display = ("tabel", "wilayah", "rincian", "tahun", "nilai_num", "nilai_teks", "flag")
    list_filter = ("flag", "tahun", "tabel__bab__publikasi")
    search_fields = ("tabel__nomor_tabel", "wilayah__nama", "rincian__nama", "nilai_teks")
    autocomplete_fields = ("tabel", "kolom", "wilayah", "rincian")
    list_select_related = ("tabel", "wilayah", "rincian")
