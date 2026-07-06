from django.contrib import admin

from .models import (
    CanonicalIndicator,
    CanonicalUnit,
    Fakta,
    HarmonizationReview,
    IndicatorAlias,
    UnitAlias,
)


@admin.register(Fakta)
class FaktaAdmin(admin.ModelAdmin):
    list_display = ("tabel", "wilayah", "rincian", "tahun", "nilai_num", "nilai_teks", "flag")
    list_filter = ("flag", "tahun", "tabel__bab__publikasi")
    search_fields = ("tabel__nomor_tabel", "wilayah__nama", "rincian__nama", "nilai_teks")
    autocomplete_fields = ("tabel", "kolom", "wilayah", "rincian")
    list_select_related = ("tabel", "wilayah", "rincian")


@admin.register(CanonicalUnit)
class CanonicalUnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol")
    search_fields = ("code", "name", "symbol")


@admin.register(UnitAlias)
class UnitAliasAdmin(admin.ModelAdmin):
    list_display = ("alias_text", "canonical_unit", "multiplier")
    list_filter = ("canonical_unit",)
    search_fields = ("alias_text", "normalized_alias", "canonical_unit__code", "canonical_unit__name")
    autocomplete_fields = ("canonical_unit",)


@admin.register(CanonicalIndicator)
class CanonicalIndicatorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "topic", "default_unit", "is_active")
    list_filter = ("topic", "is_active", "default_unit")
    search_fields = ("code", "name", "description")
    autocomplete_fields = ("default_unit",)


@admin.register(IndicatorAlias)
class IndicatorAliasAdmin(admin.ModelAdmin):
    list_display = ("alias_text", "table_title_pattern", "canonical_indicator", "match_type", "confidence", "is_approved")
    list_filter = ("match_type", "is_approved", "canonical_indicator__topic")
    search_fields = (
        "alias_text",
        "normalized_alias",
        "table_title_pattern",
        "topic_hint",
        "canonical_indicator__code",
        "canonical_indicator__name",
    )
    autocomplete_fields = ("canonical_indicator", "raw_indicator", "unit_alias")


@admin.register(HarmonizationReview)
class HarmonizationReviewAdmin(admin.ModelAdmin):
    list_display = ("object_type", "raw_value", "suggested_indicator", "suggested_unit", "confidence", "status", "diubah_pada")
    list_filter = ("object_type", "status")
    search_fields = ("raw_value", "suggested_value", "notes")
    autocomplete_fields = ("raw_indicator", "raw_table", "suggested_indicator", "suggested_unit", "reviewer")
