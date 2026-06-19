from django.contrib import admin

from .models import Indikator, Rincian, Wilayah


@admin.register(Wilayah)
class WilayahAdmin(admin.ModelAdmin):
    list_display = ("nama", "jenis", "parent", "kode_bps")
    list_filter = ("jenis",)
    search_fields = ("nama", "kode_bps")
    autocomplete_fields = ("parent",)


@admin.register(Indikator)
class IndikatorAdmin(admin.ModelAdmin):
    list_display = ("nama", "satuan", "tipe_nilai")
    list_filter = ("tipe_nilai",)
    search_fields = ("nama",)


@admin.register(Rincian)
class RincianAdmin(admin.ModelAdmin):
    list_display = ("nama", "kelompok")
    list_filter = ("kelompok",)
    search_fields = ("nama",)
