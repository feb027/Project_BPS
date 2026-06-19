from django.contrib import admin

from .models import Bab, KolomTabel, Publikasi, Tabel


class BabInline(admin.TabularInline):
    model = Bab
    extra = 0


class KolomTabelInline(admin.TabularInline):
    model = KolomTabel
    extra = 0
    autocomplete_fields = ("indikator",)


@admin.register(Publikasi)
class PublikasiAdmin(admin.ModelAdmin):
    list_display = ("judul", "tahun_terbit", "wilayah_cakupan", "jenis")
    list_filter = ("jenis", "tahun_terbit")
    search_fields = ("judul",)
    inlines = [BabInline]


@admin.register(Bab)
class BabAdmin(admin.ModelAdmin):
    list_display = ("nomor", "nama", "publikasi")
    list_filter = ("publikasi",)
    search_fields = ("nama",)


@admin.register(Tabel)
class TabelAdmin(admin.ModelAdmin):
    list_display = ("nomor_tabel", "nama_ringkas", "judul", "bab", "tipe_baris", "status_verifikasi")
    list_editable = ("nama_ringkas",)
    list_filter = ("tipe_baris", "status_verifikasi", "bab__publikasi")
    search_fields = ("nomor_tabel", "judul", "nama_ringkas")
    inlines = [KolomTabelInline]


@admin.register(KolomTabel)
class KolomTabelAdmin(admin.ModelAdmin):
    list_display = ("tabel", "urutan", "indikator", "satuan", "tahun", "tipe_nilai")
    list_filter = ("tipe_nilai",)
    search_fields = ("tabel__nomor_tabel", "indikator__nama")
    autocomplete_fields = ("tabel", "indikator")
