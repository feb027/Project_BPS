from decimal import Decimal

from django.db import migrations


def normalize(value):
    value = (value or "").strip().lower()
    replacements = {
        "²": "2",
        "-": " ",
        "_": " ",
        "/": " ",
        "(": " ",
        ")": " ",
        ",": " ",
        ".": " ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return " ".join(value.split())


UNITS = [
    {
        "code": "jiwa",
        "name": "Jiwa",
        "symbol": "jiwa",
        "description": "Jumlah orang/penduduk dalam satuan jiwa.",
        "aliases": [
            ("jiwa", Decimal("1"), "Satuan penduduk default."),
            ("Jiwa", Decimal("1"), "Variasi kapitalisasi."),
            ("orang", Decimal("1"), "Alias orang."),
            ("penduduk", Decimal("1"), "Alias konteks penduduk."),
            ("ribu", Decimal("1000"), "Ribu jiwa; nilai mentah dikali 1000."),
            ("ribu jiwa", Decimal("1000"), "Ribu jiwa; nilai mentah dikali 1000."),
        ],
    },
    {
        "code": "persen",
        "name": "Persen",
        "symbol": "%",
        "description": "Persentase.",
        "aliases": [
            ("%", Decimal("1"), "Simbol persen."),
            ("persen", Decimal("1"), "Teks persen."),
            ("Persen", Decimal("1"), "Variasi kapitalisasi."),
        ],
    },
    {
        "code": "km2",
        "name": "Kilometer Persegi",
        "symbol": "km²",
        "description": "Luas area dalam kilometer persegi.",
        "aliases": [
            ("km2", Decimal("1"), "ASCII km2."),
            ("km²", Decimal("1"), "Simbol km persegi."),
            ("km", Decimal("1"), "Alias dari data jalan/area yang perlu review konteks."),
        ],
    },
    {
        "code": "per_100_perempuan",
        "name": "Per 100 Perempuan",
        "symbol": "per 100 perempuan",
        "description": "Rasio jenis kelamin: laki-laki per 100 perempuan.",
        "aliases": [
            ("per 100 perempuan", Decimal("1"), "Satuan rasio jenis kelamin."),
            ("per 100", Decimal("1"), "Alias singkat."),
        ],
    },
]

INDICATORS = [
    {
        "code": "jumlah_penduduk",
        "name": "Jumlah Penduduk",
        "topic": "Kependudukan",
        "unit": "jiwa",
        "description": "Total penduduk pada wilayah dan tahun tertentu.",
        "aliases": [
            ("Jumlah Penduduk", "", "exact"),
            ("Penduduk Jumlah", "", "exact"),
            ("Penduduk - Jumlah", "", "exact"),
            ("[Penduduk] Jumlah", "", "exact"),
            ("Jumlah", "penduduk", "contextual"),
        ],
    },
    {
        "code": "jumlah_penduduk_laki_laki",
        "name": "Jumlah Penduduk Laki-laki",
        "topic": "Kependudukan",
        "unit": "jiwa",
        "description": "Jumlah penduduk laki-laki pada wilayah dan tahun tertentu.",
        "aliases": [
            ("Penduduk Laki-laki", "", "exact"),
            ("Penduduk - Laki-Laki", "", "exact"),
            ("[Penduduk] Laki-Laki", "", "exact"),
            ("Jumlah Penduduk Laki-laki Menurut Kecamatan", "", "exact"),
            ("Laki-Laki", "penduduk", "contextual"),
            ("Laki-laki", "penduduk", "contextual"),
        ],
    },
    {
        "code": "jumlah_penduduk_perempuan",
        "name": "Jumlah Penduduk Perempuan",
        "topic": "Kependudukan",
        "unit": "jiwa",
        "description": "Jumlah penduduk perempuan pada wilayah dan tahun tertentu.",
        "aliases": [
            ("Penduduk Perempuan", "", "exact"),
            ("Penduduk - Perempuan", "", "exact"),
            ("[Penduduk] Perempuan", "", "exact"),
            ("Jumlah Penduduk Perempuan Menurut Kecamatan", "", "exact"),
            ("Perempuan", "penduduk", "contextual"),
        ],
    },
    {
        "code": "kepadatan_penduduk",
        "name": "Kepadatan Penduduk",
        "topic": "Kependudukan",
        "unit": "km2",
        "description": "Kepadatan penduduk per kilometer persegi.",
        "aliases": [
            ("Kepadatan Penduduk per km", "", "exact"),
            ("Kepadatan Penduduk per km2", "", "exact"),
            ("Kepadatan Penduduk per km2 Menurut Kecamatan", "", "exact"),
        ],
    },
    {
        "code": "laju_pertumbuhan_penduduk",
        "name": "Laju Pertumbuhan Penduduk",
        "topic": "Kependudukan",
        "unit": "persen",
        "description": "Laju pertumbuhan penduduk per tahun.",
        "aliases": [
            ("Laju Pertumbuhan Penduduk per Tahun", "", "exact"),
            ("Laju Pertumbuhan Penduduk per Tahun 2020–2022", "", "exact"),
            ("Laju Pertumbuhan Penduduk per Tahun 2020-2023 Menurut Kecamatan", "", "exact"),
            ("[Laju Pertumbuhan Penduduk per] Tahun 2020–2023", "", "exact"),
        ],
    },
    {
        "code": "rasio_jenis_kelamin_penduduk",
        "name": "Rasio Jenis Kelamin Penduduk",
        "topic": "Kependudukan",
        "unit": "per_100_perempuan",
        "description": "Rasio laki-laki per 100 perempuan.",
        "aliases": [
            ("Rasio Jenis Kelamin Penduduk", "", "exact"),
            ("Rasio Jenis Kelamin Penduduk Menurut Kecamatan", "", "exact"),
        ],
    },
    {
        "code": "jumlah_penduduk_miskin",
        "name": "Jumlah Penduduk Miskin",
        "topic": "Kemiskinan",
        "unit": "jiwa",
        "description": "Jumlah penduduk miskin. Alias ribu penduduk menggunakan unit multiplier 1000 bila tersedia.",
        "aliases": [
            ("Jumlah Penduduk Miskin", "", "exact"),
            ("[Jumlah Penduduk] Miskin", "", "exact"),
            ("Penduduk Miskin Jumlah", "", "exact"),
        ],
    },
    {
        "code": "persentase_penduduk_miskin",
        "name": "Persentase Penduduk Miskin",
        "topic": "Kemiskinan",
        "unit": "persen",
        "description": "Persentase penduduk miskin.",
        "aliases": [
            ("Persentase Penduduk Miskin", "", "exact"),
            ("[Persentase Penduduk] Miskin", "", "exact"),
            ("Penduduk Miskin Persentase", "", "exact"),
        ],
    },
]


def seed_units(apps, schema_editor):
    CanonicalUnit = apps.get_model("data", "CanonicalUnit")
    UnitAlias = apps.get_model("data", "UnitAlias")

    units_by_code = {}
    for item in UNITS:
        unit, _ = CanonicalUnit.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "symbol": item["symbol"],
                "description": item["description"],
            },
        )
        units_by_code[item["code"]] = unit
        for alias_text, multiplier, notes in item["aliases"]:
            UnitAlias.objects.update_or_create(
                normalized_alias=normalize(alias_text),
                defaults={
                    "canonical_unit": unit,
                    "alias_text": alias_text,
                    "multiplier": multiplier,
                    "notes": notes,
                },
            )
    return units_by_code


def seed_indicators(apps, units_by_code):
    CanonicalIndicator = apps.get_model("data", "CanonicalIndicator")
    IndicatorAlias = apps.get_model("data", "IndicatorAlias")
    Indikator = apps.get_model("referensi", "Indikator")
    UnitAlias = apps.get_model("data", "UnitAlias")

    for item in INDICATORS:
        indicator, _ = CanonicalIndicator.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "topic": item["topic"],
                "description": item["description"],
                "default_unit": units_by_code.get(item["unit"]),
                "preferred_direction": "neutral",
                "is_active": True,
            },
        )
        default_unit_alias = (
            UnitAlias.objects.filter(canonical_unit=units_by_code.get(item["unit"]), multiplier=Decimal("1")).order_by("id").first()
            if item.get("unit")
            else None
        )
        for alias_text, table_title_pattern, match_type in item["aliases"]:
            raw_indicator = Indikator.objects.filter(nama__iexact=alias_text).order_by("id").first()
            IndicatorAlias.objects.update_or_create(
                normalized_alias=normalize(alias_text),
                table_title_pattern=normalize(table_title_pattern),
                topic_hint="",
                defaults={
                    "canonical_indicator": indicator,
                    "raw_indicator": raw_indicator,
                    "alias_text": alias_text,
                    "unit_alias": default_unit_alias,
                    "match_type": match_type,
                    "confidence": Decimal("1.00") if match_type == "exact" else Decimal("0.85"),
                    "is_approved": True,
                    "notes": "Seed awal harmonisasi kependudukan. Alias contextual hanya boleh dipakai saat judul tabel cocok.",
                },
            )


def forwards(apps, schema_editor):
    units_by_code = seed_units(apps, schema_editor)
    seed_indicators(apps, units_by_code)


def backwards(apps, schema_editor):
    CanonicalIndicator = apps.get_model("data", "CanonicalIndicator")
    CanonicalUnit = apps.get_model("data", "CanonicalUnit")
    IndicatorAlias = apps.get_model("data", "IndicatorAlias")
    UnitAlias = apps.get_model("data", "UnitAlias")

    indicator_codes = [item["code"] for item in INDICATORS]
    unit_codes = [item["code"] for item in UNITS]

    IndicatorAlias.objects.filter(canonical_indicator__code__in=indicator_codes).delete()
    CanonicalIndicator.objects.filter(code__in=indicator_codes).delete()
    UnitAlias.objects.filter(canonical_unit__code__in=unit_codes).delete()
    CanonicalUnit.objects.filter(code__in=unit_codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("data", "0005_canonicalunit_canonicalindicator_harmonizationreview_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
