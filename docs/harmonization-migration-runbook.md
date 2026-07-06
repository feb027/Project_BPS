# Harmonization Migration Runbook

Last updated: 2026-07-05
Project: `Project_BPS`
Database: PostgreSQL `bps_publikasi`

## Purpose

Migrate extracted publication facts into a usable canonical time-series layer without corrupting the raw source layer.

The raw extraction tables stay as source evidence. Migration here means creating and validating canonical indicators/aliases and repairing obvious numeric parsing errors in controlled batches.

## Hard Rules

1. Never apply all aliases at once.
2. Always backup before a DB write.
3. Apply by master table/batch only.
4. After each apply, run coverage + time-series validation.
5. If validator finds suspicious jumps or context bleed, stop and repair before the next batch.
6. Do not force-map legacy rows when subject extraction is broken.
7. Review-band suggestions stay unapproved until manually inspected.

## Key Commands

Run from `webapp/`:

```bash
. .venv/bin/activate
```

### Coverage

```bash
python manage.py report_harmonization_coverage --master-year 2026 --examples 10
```

### Staged alias apply

Dry-run:

```bash
python manage.py apply_harmonization_batch --master-year 2026 --table-number <TABLE_NO>
```

Apply:

```bash
python manage.py apply_harmonization_batch --master-year 2026 --table-number <TABLE_NO> --apply
```

Batch dry-run:

```bash
python manage.py apply_harmonization_batch --master-year 2026 --max-tables 3
```

### Time-series validation

```bash
python manage.py validate_harmonized_timeseries --indicator-code <CANONICAL_CODE> --examples 5 --jump-ratio 10
```

Validator checks:

- selected rows after source precedence
- year coverage
- duplicate candidates from overlapping publications
- suspicious subject-level jumps
- source table distribution

### Numeric repair

Dry-run:

```bash
python manage.py repair_numeric_values --publication-year <YEAR> --table-number <TABLE_NO> --indicator '<TEXT>' --unit <UNIT> --min-ratio 10
```

Apply:

```bash
python manage.py repair_numeric_values --publication-year <YEAR> --table-number <TABLE_NO> --indicator '<TEXT>' --unit <UNIT> --min-ratio 10 --apply
```

### PostgreSQL backup

```bash
BACKUP_DIR=/home/aqua/Project_BPS_backups/db
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d-%H%M%S)
BACKUP="$BACKUP_DIR/bps_publikasi_<checkpoint>_$TS.dump"
pg_dump -Fc -f "$BACKUP" -d bps_publikasi -U aqua -p 5432
pg_restore -l "$BACKUP" >/dev/null
sha256sum "$BACKUP" | tee "$BACKUP.sha256"
ls -lh "$BACKUP"
```

## Current DB State After Batch 5AD

As of the last validated checkpoint:

```text
canonical indicators: 236
approved aliases: 284
aliases total: 284
```

Coverage:

```text
Current approved aliases:
columns=2761/4913 (56.2%)
facts=98721/162114 (60.9%)

Combined AUTO + master:
columns=3157/4913 (64.3%)
facts=109182/162114 (67.3%)

Combined REVIEW-inclusive:
columns=3626/4913 (73.8%)
facts=123462/162114 (76.2%)
```

## Backup Checkpoints Created

Pre/post batch and repair backups live outside the repo:

```text
/home/aqua/Project_BPS_backups/db/
```

Known checkpoint files:

```text
bps_publikasi_before_batch1_20260705-134919.dump
bps_publikasi_after_batch1_needs_review_20260705-135402.dump
bps_publikasi_before_numeric_repair_luas_2019_20260705-135951.dump
bps_publikasi_after_numeric_repair_luas_2019_20260705-140405.dump
bps_publikasi_before_batch2_20260705-140502.dump
bps_publikasi_before_pns_pattern_repair_20260705-140834.dump
bps_publikasi_before_numeric_repair_pns_232_20260705-141005.dump
bps_publikasi_after_batch2_validated_20260705-141108.dump
bps_publikasi_before_numeric_repair_pns_233_20260705-144218.dump
bps_publikasi_after_numeric_repair_before_alias_233_20260705-144247.dump
bps_publikasi_after_batch3a_233_validated_20260705-144636.dump
bps_publikasi_before_batch3b_241_20260705-145318.dump
bps_publikasi_before_numeric_repair_revenue_241_20260705-145600.dump
bps_publikasi_after_batch3b_241_repaired_reviewed_20260705-145858.dump
bps_publikasi_before_numeric_repair_population_311_20260705-150949.dump
bps_publikasi_after_population_repair_before_alias_311_20260705-151036.dump
bps_publikasi_before_exact_rasio_311_fix_20260705-151234.dump
bps_publikasi_after_batch3c_311_validated_20260705-151337.dump
bps_publikasi_before_batch4a_416_419_20260705-153542.dump
bps_publikasi_before_batch4b_413_20260705-154241.dump
bps_publikasi_before_batch4c_414_20260705-155021.dump
bps_publikasi_after_batch4c_414_validated_20260705-155052.dump
bps_publikasi_before_batch4d_411_repair_apply_20260705-231324.dump
bps_publikasi_after_batch4d_411_partial_validated_20260705-234122.dump
bps_publikasi_before_batch4e_413_partial_20260705-234703.dump
bps_publikasi_after_batch4e_413_partial_validated_20260705-234856.dump
bps_publikasi_before_batch4f_4110_apmapk_20260705-235337.dump
bps_publikasi_after_batch4f_4110_apmapk_validated_20260705-235410.dump
bps_publikasi_before_batch4g_416_mts_20260706-020010.dump
bps_publikasi_after_batch4g_416_mts_partial_validated_20260706-020110.dump
bps_publikasi_before_batch4h_419_ma_20260706-020551.dump
bps_publikasi_after_batch4h_419_ma_partial_validated_20260706-020817.dump
bps_publikasi_before_batch4i_415_smp_repair_apply_20260706-021519.dump
bps_publikasi_after_batch4i_415_smp_partial_validated_20260706-021721.dump
bps_publikasi_before_batch4j_417_sma_20260706-022307.dump
bps_publikasi_after_batch4j_417_sma_validated_20260706-022431.dump
bps_publikasi_before_batch4k_418_smk_20260706-023003.dump
bps_publikasi_after_batch4k_418_smk_validated_20260706-023125.dump
bps_publikasi_before_batch4l_412_ra_20260706-024032.dump
bps_publikasi_after_batch4l_412_ra_partial_validated_20260706-024154.dump
bps_publikasi_before_batch4m_4111_melek_huruf_repair_apply_20260706-024250.dump
bps_publikasi_after_batch4m_4111_melek_huruf_validated_20260706-024342.dump
bps_publikasi_before_batch4n_421_sarana_kesehatan_20260706-025652.dump
bps_publikasi_after_batch4n_421_sarana_kesehatan_validated_20260706-025821.dump
bps_publikasi_before_batch4o_422_tenaga_kesehatan_20260706-030250.dump
bps_publikasi_after_batch4o_422_tenaga_kesehatan_partial_validated_20260706-030445.dump
bps_publikasi_before_batch4p_423_fasilitas_kesehatan_20260706-030550.dump
bps_publikasi_after_batch4p_423_fasilitas_kesehatan_validated_20260706-030641.dump
bps_publikasi_before_batch4q_431_agama_penduduk_20260706-031155.dump
bps_publikasi_after_batch4q_431_agama_penduduk_partial_validated_20260706-031345.dump
bps_publikasi_before_batch4r_432_tempat_peribadatan_20260706-031443.dump
bps_publikasi_after_batch4r_432_tempat_peribadatan_partial_validated_20260706-031629.dump
bps_publikasi_before_batch4s_433_bencana_alam_20260706-031731.dump
bps_publikasi_after_batch4s_433_bencana_alam_partial_validated_20260706-031854.dump
bps_publikasi_before_batch4t_441_kemiskinan_repair_apply_20260706-032338.dump
bps_publikasi_before_batch4u_442_indeks_kemiskinan_repair_apply_20260706-032449.dump
bps_publikasi_after_batch4u_442_indeks_kemiskinan_validated_20260706-032537.dump
bps_publikasi_before_batch5a_511_lahan_sawah_repair_apply_20260706-033147.dump
bps_publikasi_after_batch5a_511_lahan_sawah_partial_validated_20260706-033325.dump
bps_publikasi_before_batch5b_512_lahan_bukan_sawah_repair_apply_20260706-033725.dump
bps_publikasi_after_batch5b_512_lahan_bukan_sawah_partial_validated_20260706-033940.dump
bps_publikasi_before_batch5c_513_luas_panen_padi_apply_no_repair_20260706-034036.dump
bps_publikasi_before_batch5c_513_custom_comma_repair_20260706-034231.dump
bps_publikasi_after_batch5c_513_luas_panen_padi_partial_validated_20260706-034341.dump
bps_publikasi_before_batch5d_514_produksi_padi_repair_apply_20260706-034440.dump
bps_publikasi_after_batch5d_514_produksi_padi_partial_validated_20260706-034545.dump
bps_publikasi_before_batch5e_515_luas_panen_palawija_apply_no_repair_20260706-034934.dump
bps_publikasi_after_batch5e_515_luas_panen_palawija_partial_validated_20260706-035121.dump
bps_publikasi_before_batch5f_516_produksi_palawija_repair_apply_20260706-035317.dump
bps_publikasi_after_batch5f_516_produksi_palawija_partial_validated_20260706-035453.dump
```

Each has a `.sha256` beside it.

## Completed Batch 1

Applied master tables:

```text
1.1.1 Luas Daerah Menurut Kecamatan, 2025
1.1.2 Tinggi Wilayah (mdpl) dan Jarak ke Ibukota (km), 2025
2.1.1 Jumlah Desa/Kelurahan Menurut Kecamatan 2021-2025
```

Created/affected canonical indicators:

```text
luas_wilayah
tinggi_wilayah
jarak_ke_ibukota
jumlah_desakelurahan
```

### Batch 1 Findings

#### `luas_wilayah` numeric scale bug

Raw PDF/extraction examples:

```text
24.667
13.633
270.882
```

For unit `km2`, these should be:

```text
246.67
136.33
2708.82
```

But old stored values were:

```text
24667
13633
270882
```

Root cause: dot-only decimal area values were interpreted as thousands.

Fixes applied:

- `normalize_numeric()` now repairs decimal-unit dot-only centesimal values.
- 40 rows in publication year 2019 table `1.1.1` repaired.

Validation after repair:

```text
luas_wilayah suspicious_jumps=0
```

Remaining known limitation:

```text
luas_wilayah missing_years=[2019, 2020, 2021]
```

Reason: legacy raw indicator `Luas` rows for 2020/2021 have broken subject extraction; rows are attached to `Kabupaten Tasikmalaya` instead of kecamatan names. Do not map these until row subjects are repaired.

#### `jumlah_desakelurahan` duplicate overlap

Publications overlap year ranges:

```text
2020 publication: 2015–2019
2021 publication: 2016–2020
2022 publication: 2017–2021
2023 publication: 2017–2022
2024 publication: 2018–2023
2026 publication: 2021–2025
```

Fix:

- canonical time-series now deduplicates by canonical + subject + year and chooses the newest publication source.
- validator reports duplicate candidates separately.

Validation:

```text
jumlah_desakelurahan suspicious_jumps=0
```

## Completed Batch 2

Applied master tables:

```text
2.2.1 DPRD menurut partai politik dan jenis kelamin
2.3.1 PNS menurut jabatan dan jenis kelamin
2.3.2 PNS menurut tingkat pendidikan dan jenis kelamin
```

Created/affected canonical indicators include:

```text
anggota_dprd_laki_laki
anggota_dprd_perempuan
anggota_dprd_jumlah
t2_3_1_anggota_pns_laki_laki
t2_3_1_anggota_pns_perempuan
t2_3_1_anggota_pns_jumlah
t2_3_2_anggota_pns_laki_laki
t2_3_2_anggota_pns_perempuan
t2_3_2_anggota_pns_jumlah
```

### Batch 2 Findings

#### PNS context bleed

Problem:

`2.3.2` PNS education aliases matched `2.3.3` PNS rank table because context pattern was too short:

```text
pegawai negeri sipil tingkat
```

Fixes:

- `title_pattern()` now keeps 5 meaningful tokens instead of 4.
- Existing DB aliases for `t2_3_2_*` were tightened to:

```text
pegawai negeri sipil tingkat pendidikan
```

This prevents matching `tingkat kepangkatan`.

#### PNS 2.3.2 numeric scale bug

Rows in `2.3.2` with unit `jiwa` were stored 1000x too small:

```text
5.745 -> stored 5.745, should be 5745
6.401 -> stored 6.401, should be 6401
12.146 -> stored 12.146, should be 12146
```

Fix:

- 6 rows repaired via `repair_numeric_values`.

Validation after repair:

```text
t2_3_2_anggota_pns_laki_laki suspicious_jumps=0
t2_3_2_anggota_pns_perempuan suspicious_jumps=0
t2_3_2_anggota_pns_jumlah suspicious_jumps=0
```

#### PNS 2.3.1 remaining jump

Some `2.3.1` PNS by jabatan categories still show jumps such as Eselon II.a dropping from ~61 to 1.

Manual evidence showed raw rows genuinely contain that change, not a parser bug. Treat this as real data/category shift unless later source inspection proves otherwise.

## Completed Batch 3A

Applied master table:

```text
2.3.3 PNS menurut tingkat kepangkatan dan jenis kelamin
```

Created canonical indicators:

```text
t2_3_3_anggota_pns_laki_laki
t2_3_3_anggota_pns_perempuan
t2_3_3_anggota_pns_jumlah
```

### Batch 3A Findings

#### PNS 2.3.3 numeric scale bug

Read-only dry-run initially showed 29 candidate repairs, but one was a false-positive:

```text
id=100435 raw='1.1576' stored=11576.0000
```

Do not run broad repair for table `2.3.3`.

Safe targeted command used:

```bash
python manage.py repair_numeric_values --table-number 2.3.3 --unit Jiwa --min-ratio 10 --apply
```

This repaired 28 rows with actual unit `Jiwa/jiwa`, e.g.:

```text
1,010 -> 1010
5,980 -> 5980
3.039 -> 3039
4.411 -> 4411
14.900 -> 14900
```

False-positive `id=100435` was explicitly checked after repair and stayed unchanged:

```text
id=100435 1.1576 11576.0000
```

Alias pattern for the three new canonical indicators is specific and approved:

```text
pegawai negeri sipil tingkat kepangkatan
```

Validation after apply:

```text
t2_3_3_anggota_pns_laki_laki selected_rows=171 missing_years=[] suspicious_jumps=1
t2_3_3_anggota_pns_perempuan selected_rows=166 missing_years=[] suspicious_jumps=0
t2_3_3_anggota_pns_jumlah selected_rows=210 missing_years=[] suspicious_jumps=1
```

The remaining jump is exactly ratio 10 for category `3. I/C (Juru)` from 10 to 1. Raw evidence confirms the source rows contain this change; treat it as real category movement, not parser error.

## Completed Batch 3B

Applied master table:

```text
2.4.1 Realisasi Pendapatan Pemerintah Kabupaten Tasikmalaya
```

Created canonical indicator:

```text
realisasi_pendapatan_pemerintah_kabupaten_tasikmalaya
```

### Batch 3B Findings

#### Canonical-code collision was expected

The 2026 master has two columns with the same raw indicator label but different years:

```text
2024 Realisasi Pendapatan Pemerintah Kabupaten Tasikmalaya
2025 Realisasi Pendapatan Pemerintah Kabupaten Tasikmalaya
```

Both map to one canonical indicator because year is stored on the fact/column, not in the indicator code. Read-only inspection confirmed the raw indicator id is only used by table `2.4.1`, so a blank alias pattern is acceptable here.

#### Revenue numeric scale repair

Initial validation after alias apply showed large 1000x jumps for older revenue rows. Root cause: older `ribu rupiah` rows such as:

```text
74.276.945,180
2.160.615.166,635
1.508.324.968,000
```

were stored as if they were full rupiah instead of thousand-rupiah evidence. The repair command was extended with explicit targeting flags:

```bash
--title-contains
--raw-regex
--scale-factor
```

Safe targeted repair used:

```bash
python manage.py repair_numeric_values \
  --table-number 2.4.1 \
  --title-contains 'ribu rupiah' \
  --raw-regex ',[0-9]{3}$' \
  --scale-factor 1000 \
  --min-ratio 10 \
  --apply
```

This repaired 102 rows.

Two malformed OCR rows were then repaired by exact id using `nilai_num * 1000`:

```text
id=113124 raw='1.193.428.349,582.45'
id=113126 raw='378.640,840.45'
```

Validation after repair:

```text
selected_rows=397
years=2018..2025
missing_years=[]
duplicate_candidates=45
suspicious_jumps=9
```

Remaining jumps are revenue/APBD category shifts or hierarchy differences, e.g. `Pembentukan Dana Cadangan`, `Pendapatan Hibah`, `Retribusi Daerah`, `Pembiayaan Netto`, and `Lain-lain PAD yang Sah`. Raw evidence was inspected; no broad 1000x parser class remains for the `,[0-9]{3}$` legacy pattern.

Validation/tests after Batch 3B:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

## Completed Batch 3C

Applied master table:

```text
3.1.1 Penduduk/laju/distribusi/kepadatan/rasio jenis kelamin
```

Created canonical indicators:

```text
jumlah_penduduk_menurut_kecamatan
laju_pertumbuhan_penduduk_per_tahun_2020_2025_menurut_kecama
persentase_penduduk_menurut_kecamatan
```

Existing canonical indicators reused:

```text
kepadatan_penduduk
rasio_jenis_kelamin_penduduk
```

### Batch 3C Findings

#### Targeted numeric repairs

Safe targeted repairs applied:

```text
Jumlah Penduduk + jiwa: 117 rows
Persentase Penduduk + %: 39 rows
Rasio Jenis Kelamin: 39 rows
```

The broad `Kepadatan Penduduk + km2` repair was deliberately skipped. It still shows 30 dry-run candidates such as:

```text
raw='1.253' stored=1253 -> normalize would propose 12.53
```

These are false-positive density values; validator confirms `kepadatan_penduduk` is clean.

#### Exact rasio total repair

One remaining anomaly after targeted repair:

```text
id=115486 Kabupaten Tasikmalaya 2019 raw='3.767,350000000001' stored=3767.3500
```

Neighbouring source row totals:

```text
Laki-Laki=913795
Perempuan=882701
```

Exact repair used:

```text
913795 / 882701 * 100 = 103.52
```

Final validators after Batch 3C:

```text
jumlah_penduduk_menurut_kecamatan selected_rows=356 suspicious_jumps=0
laju_pertumbuhan_penduduk_per_tahun_2020_2025_menurut_kecama selected_rows=80 suspicious_jumps=0
persentase_penduduk_menurut_kecamatan selected_rows=279 suspicious_jumps=0
kepadatan_penduduk selected_rows=278 suspicious_jumps=0
rasio_jenis_kelamin_penduduk selected_rows=279 suspicious_jumps=0
```

Notes:

- `jumlah_penduduk_menurut_kecamatan` includes older 2010/2017/2018 rows from the 2019 publication plus 2020+ rows; missing years before 2020 are expected.
- `laju_pertumbuhan_penduduk_per_tahun_2020_2025_menurut_kecama` remains separate from older `laju_pertumbuhan_penduduk`; do not merge manually until canonical policy for period-specific growth-rate indicators is reviewed.
- `apply_harmonization_batch` reported `conflicts_skipped=1`; no validation issue remained after targeted repairs.

Validation/tests after Batch 3C:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

## Current Code Changes Relevant to Migration

Core modules:

```text
webapp/apps/data/harmonization.py
webapp/apps/data/timeseries.py
webapp/apps/data/utils.py
```

Management commands:

```text
webapp/apps/data/management/commands/apply_harmonization_batch.py
webapp/apps/data/management/commands/repair_numeric_values.py
webapp/apps/data/management/commands/report_harmonization_coverage.py
webapp/apps/data/management/commands/suggest_indicator_aliases.py
webapp/apps/data/management/commands/suggest_cross_table_aliases.py
webapp/apps/data/management/commands/validate_harmonized_timeseries.py
```

Tests:

```text
webapp/apps/data/tests.py
```

Regression coverage includes:

- `24.667 km2 -> 246.67`
- `270.882 km2 -> 2708.82`
- duplicate canonical grain prefers newest publication source
- PNS title pattern keeps distinguishing tokens `pendidikan` / `kepangkatan`

## Latest Ad-Hoc Verification

Script prefix:

```text
/tmp/hermes-verify-*.sh
```

Last successful verification checked:

```text
python manage.py check
python manage.py test apps.data
repair_numeric_values luas dry-run -> Candidate repairs: 0
repair_numeric_values PNS dry-run -> Candidate repairs: 0
validate_harmonized_timeseries luas_wilayah -> suspicious_jumps=0
validate_harmonized_timeseries t2_3_2_anggota_pns_jumlah -> suspicious_jumps=0
```

## Next Planned Batch

Do not use `--max-tables` blindly for the next apply. Batch 3C completed; choose the next master table only after dry-run and numeric-risk inspection.

Next target table is not selected yet.

### Attempted Batch 4A — Rolled Back

Subagent Group C initially marked `4.1.6` and `4.1.9` as possible `SAFE_APPLY`, so parent executed the normal gated flow:

```text
backup -> dry-run -> apply 4.1.6 -> apply 4.1.9 -> validate
```

Pre-apply backup:

```text
bps_publikasi_before_batch4a_416_419_20260705-153542.dump
```

Validation failed after alias apply:

```text
t4_1_6_murid suspicious_jumps=58
t4_1_9_guru suspicious_jumps=2
t4_1_9_guru_jumlah suspicious_jumps=3
t4_1_9_guru_swasta suspicious_jumps=1
t4_1_9_murid suspicious_jumps=10
t4_1_9_murid_jumlah suspicious_jumps=2
t4_1_9_murid_swasta suspicious_jumps=2
```

Since this batch only created aliases/canonical indicators and did not change fact values, parent rolled back the batch by deleting the affected `t4_1_6_*` and `t4_1_9_*` canonical indicators plus their aliases.

Post-rollback counts returned to Batch 3C state:

```text
canonical=28
approved_aliases=48
remaining t4_1_6=0
remaining t4_1_9=0
```

Do not re-apply `4.1.6` or `4.1.9` until education-table alias semantics are fixed. Likely issues:

- duplicate grains from overlapping sources are large for education tables;
- broad self-aliases such as `Murid` can mix total/current-year rows with Negeri/Swasta/Jumlah layouts;
- some validators expose real source structure drift rather than simple numeric scale bugs.

### Attempted Batch 4B — Rolled Back

Subagent B2 marked `4.1.3` and `4.1.4` as possible `SAFE_APPLY`. Parent only applied `4.1.3` first, then validated before touching `4.1.4`.

Pre-apply backup:

```text
bps_publikasi_before_batch4b_413_20260705-154241.dump
```

Validation failed for `4.1.3`:

```text
t4_1_3_guru_swasta suspicious_jumps=7
t4_1_3_murid_swasta suspicious_jumps=3
```

Examples included `Kabupaten Tasikmalaya` or kecamatan rows dropping to `1` and then returning to hundreds/thousands. This suggests source/extraction/classification problems in Negeri/Swasta detail rows, not a simple numeric-normalizer issue.

Rollback performed by deleting all `t4_1_3_*` canonical indicators plus their aliases. `4.1.4` was not applied.

Post-rollback counts returned to Batch 3C state:

```text
canonical=28
approved_aliases=48
remaining t4_1_3=0
remaining t4_1_4=0
```

Do not apply education tables using only subagent `SAFE_APPLY` labels. Parent validation is mandatory and has now rejected `4.1.3`, `4.1.6`, and `4.1.9`.

### Completed Batch 4C

Applied master table:

```text
4.1.4 Madrasah Ibtidaiyah (MI) under Kementerian Agama
```

Created canonical indicators:

```text
t4_1_4_sekolah
t4_1_4_guru
t4_1_4_murid
```

Pre-apply backup:

```text
bps_publikasi_before_batch4c_414_20260705-155021.dump
```

Post-validated backup:

```text
bps_publikasi_after_batch4c_414_validated_20260705-155052.dump
sha256=7018e2bef2c14512fa45996f334f66e311a5c95ab49673c1743789dd1a78adf5
```

Validation after apply:

```text
t4_1_4_sekolah selected_rows=320 suspicious_jumps=0
t4_1_4_guru selected_rows=320 suspicious_jumps=0
t4_1_4_murid selected_rows=320 suspicious_jumps=0
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

Education root-cause note from rejected batches:

- Some small Guru/Murid Swasta values are real for small kecamatan.
- Some rejected jumps come from publication revisions/structure changes, not simple parsing. Example `4.1.3` total row in publication 2025 has `Guru Swasta=1`, while publication 2026 has `Guru Swasta=241` for the next/year-overlap series.
- Treat education tables as source-sensitive; only accept when parent validator returns clean or source evidence supports the jump.

### Completed Batch 4D — Partial Accepted

Applied master table:

```text
4.1.1 Taman Kanak-Kanak (TK) under Kementerian Pendidikan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4d_411_repair_apply_20260705-231324.dump
sha256=133e99f7acac1a48f485fd9b72e9e39511e882796e6cda17e8ac1d14f9afc971
```

Targeted numeric repair applied before aliasing:

```text
publication_year=2024 table=4.1.1 indicator=Murid raw-regex='^[0-9]{1,3},[0-9]{3}$'
updated_rows=4
ids=176104,176105,176106,176107
```

The repair changed Singaparna `Murid Swasta/Jumlah` values parsed as `1.057` / `1.060` into `1057` / `1060`. Follow-up dry-run returned `Candidate repairs: 0`.

Initial `4.1.1` apply created 12 canonical indicators, but parent validation rejected two:

```text
guru_asn_swasta suspicious_jumps=18
guru_asn_jumlah suspicious_jumps=17
```

Those two canonical indicators and their aliases were deleted. Root cause is source/methodology discontinuity rather than separator parsing: 2024 publication rows often show `Guru ASN Swasta=1`, while 2026 publication rows for overlapping/next years show tens to thousands.

Accepted canonical indicators after partial rollback:

```text
t4_1_1_sekolah_negeri suspicious_jumps=0
t4_1_1_sekolah_swasta suspicious_jumps=0
t4_1_1_sekolah_jumlah suspicious_jumps=0
guru_non_asn_negeri suspicious_jumps=0
guru_non_asn_swasta suspicious_jumps=0
guru_non_asn_jumlah suspicious_jumps=0
guru_asn_negeri suspicious_jumps=0
t4_1_1_murid_negeri suspicious_jumps=0
t4_1_1_murid_swasta suspicious_jumps=0
t4_1_1_murid_jumlah suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4d_411_partial_validated_20260705-234122.dump
sha256=55841b526ed87f6b6efa21775b8340e5d4341e03ae956b5b0b5ec24f2f316199
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

Post-Batch 4D counts:

```text
canonical=41
approved_aliases=61
aliases_total=61
```

### Completed Batch 4E — Partial Accepted

Applied master table:

```text
4.1.3 Sekolah Dasar (SD) under Kementerian Pendidikan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4e_413_partial_20260705-234703.dump
sha256=4996bb2fee2fcf0952b963414c329ae98b404c18be4966b5acee472882957c3f
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.1.3 --min-ratio 10
Candidate repairs: 0
```

Initial apply created 9 canonical indicators. Parent validation rejected two:

```text
t4_1_3_guru_swasta suspicious_jumps=7
t4_1_3_murid_swasta suspicious_jumps=3
```

Those two canonical indicators and their aliases were deleted. Root cause matches the education-table source/methodology discontinuity pattern from Batch 4B.

Accepted canonical indicators after partial rollback:

```text
t4_1_3_sekolah_negeri suspicious_jumps=0
t4_1_3_sekolah_swasta suspicious_jumps=0
t4_1_3_sekolah_jumlah suspicious_jumps=0
t4_1_3_guru_negeri suspicious_jumps=0
t4_1_3_guru_jumlah suspicious_jumps=0
t4_1_3_murid_negeri suspicious_jumps=0
t4_1_3_murid_jumlah suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4e_413_partial_validated_20260705-234856.dump
sha256=3e0fb5217a2a074d915864414956f1aa21136dd33337e06a2daa7f1cc8cf1ae1
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

Post-Batch 4E counts:

```text
canonical=48
approved_aliases=68
aliases_total=68
```

### Completed Batch 4F

Applied master table:

```text
4.1.10 APM/APK by education level
```

Pre-apply backup:

```text
bps_publikasi_before_batch4f_4110_apmapk_20260705-235337.dump
sha256=068f7a52550fb7db48e0916af3353c11f3f1ecbe15bbfebe8e51f69c09394222
```

Targeted numeric repair applied before aliasing:

```text
publication_year=2024 table=4.1.10 indicator='Angka Partisipasi Murni' unit=APM
updated_rows=3
ids=8475,8480,8485
```

The repair corrected percent values parsed as `9979`, `8642`, `6270` into `99.79`, `86.42`, `62.70`. Follow-up dry-run returned `Candidate repairs: 0`.

Created/accepted canonical indicators:

```text
angka_partisipasi_kasar selected_rows=30 suspicious_jumps=0
angka_partisipasi_murni selected_rows=16 suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4f_4110_apmapk_validated_20260705-235410.dump
sha256=70de9135662d7255e7a47f60288ccca2831d569b39717fb8e14d469b849d622c
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

Post-Batch 4F counts:

```text
canonical=50
approved_aliases=70
aliases_total=70
```

### Completed Batch 4G — Partial Accepted

Applied master table:

```text
4.1.6 Madrasah Tsanawiyah (MTs) under Kementerian Agama
```

Pre-apply backup:

```text
bps_publikasi_before_batch4g_416_mts_20260706-020010.dump
sha256=fd95398b461d1bc017bffa51c7d9fbbec9a058451a3c57f547831f444a9b4af3
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.1.6 --min-ratio 10
Candidate repairs: 0
```

Initial apply created 3 canonical indicators. Parent validation rejected one:

```text
t4_1_6_murid suspicious_jumps=58
```

That canonical indicator and its alias were deleted. The accepted indicators are:

```text
t4_1_6_sekolah selected_rows=320 suspicious_jumps=0
t4_1_6_guru selected_rows=320 suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4g_416_mts_partial_validated_20260706-020110.dump
sha256=4343515b53a8178719a0cd8d857e92c0a6be6bbad985957bb7b7078f4acd809c
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

Post-Batch 4G counts:

```text
canonical=52
approved_aliases=72
aliases_total=72
```

### Completed Batch 4H — Partial Accepted

Applied master table:

```text
4.1.9 Madrasah Aliyah (MA) under Kementerian Agama
```

Pre-apply backup:

```text
bps_publikasi_before_batch4h_419_ma_20260706-020551.dump
sha256=825917a06a97d65181a9d6445e88db0324b14b7206b1d40adb5c7a000167693c
```

Broad numeric repair was intentionally skipped for this batch because candidates were legacy `Rasio Murid-Guru %` rows, not current MA master aliases.

Initial apply created 9 canonical indicators. Parent validation rejected six:

```text
t4_1_9_guru_swasta suspicious_jumps=1
t4_1_9_guru_jumlah suspicious_jumps=3
t4_1_9_murid_swasta suspicious_jumps=2
t4_1_9_murid_jumlah suspicious_jumps=2
t4_1_9_guru suspicious_jumps=2
t4_1_9_murid suspicious_jumps=10
```

Those canonical indicators and aliases were deleted. The accepted indicators are:

```text
t4_1_9_sekolah selected_rows=137 suspicious_jumps=0
t4_1_9_guru_negeri selected_rows=55 suspicious_jumps=0
t4_1_9_murid_negeri selected_rows=56 suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4h_419_ma_partial_validated_20260706-020817.dump
sha256=533b87d0d6d26ec48af882d9a13b1dea2255ef5ba716f899673c16ba0b55b4c5
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 15 tests OK
```

Post-Batch 4H counts:

```text
canonical=55
approved_aliases=75
aliases_total=75
```

### Secondary-school context-pattern fix before Batch 4I

Changed `apps/data/harmonization.py:title_pattern()` default from 5 to 6 meaningful tokens so SMP/SMA/SMK title patterns retain their distinguishing level token:

```text
4.1.5 -> sekolah guru murid sekolah menengah pertama
4.1.7 -> sekolah guru murid sekolah menengah atas
4.1.8 -> sekolah guru murid sekolah menengah kejuruan
```

Added regression test:

```text
test_title_pattern_keeps_secondary_school_level_token
```

Validation:

```text
python manage.py test apps.data -> 16 tests OK
```

### Completed Batch 4I — Partial Accepted

Applied master table:

```text
4.1.5 Sekolah Menengah Pertama (SMP) under Kementerian Pendidikan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4i_415_smp_repair_apply_20260706-021519.dump
sha256=3f4337c27edadcd7c719f588eddab8b7cccb85fb845783c512c97a1f4c4fa631
```

Targeted numeric repairs applied before aliasing:

```text
publication_year=2026 table=4.1.5 indicator=Guru raw-regex='^[0-9]{1,3}\.[0-9]{3}$' updated_rows=6
publication_year=2026 table=4.1.5 indicator=Murid raw-regex='^[0-9]{1,3}\.[0-9]{3}$' updated_rows=6
```

Initial apply created 9 canonical indicators. Parent validation rejected four:

```text
t4_1_5_guru_negeri suspicious_jumps=2
t4_1_5_guru_swasta suspicious_jumps=23
t4_1_5_guru_jumlah suspicious_jumps=2
t4_1_5_murid_swasta suspicious_jumps=3
```

Those canonical indicators and aliases were deleted. The accepted indicators are:

```text
t4_1_5_sekolah_negeri selected_rows=320 suspicious_jumps=0
t4_1_5_sekolah_swasta selected_rows=296 suspicious_jumps=0
t4_1_5_sekolah_jumlah selected_rows=320 suspicious_jumps=0
t4_1_5_murid_negeri selected_rows=319 suspicious_jumps=0
t4_1_5_murid_jumlah selected_rows=319 suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4i_415_smp_partial_validated_20260706-021721.dump
sha256=2b8f44afdcb5c3a36fb7cf90acfb505f940e1e4a58df03698d8b6c008a8518e2
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 4I counts:

```text
canonical=60
approved_aliases=80
aliases_total=80
```

### Completed Batch 4J

Applied master table:

```text
4.1.7 Sekolah Menengah Atas (SMA) under Kementerian Pendidikan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4j_417_sma_20260706-022307.dump
sha256=af269b99512ef3bc5b790ed724e80ec23b055e60669526490a1c2f2bab5d6e10
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.1.7 --min-ratio 10
Candidate repairs: 0
```

All created indicators validated clean:

```text
t4_1_7_sekolah_negeri suspicious_jumps=0
t4_1_7_sekolah_swasta suspicious_jumps=0
t4_1_7_sekolah_jumlah suspicious_jumps=0
t4_1_7_guru_negeri suspicious_jumps=0
t4_1_7_guru_swasta suspicious_jumps=0
t4_1_7_guru_jumlah suspicious_jumps=0
t4_1_7_murid_negeri suspicious_jumps=0
t4_1_7_murid_swasta suspicious_jumps=0
t4_1_7_murid_jumlah suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4j_417_sma_validated_20260706-022431.dump
sha256=ae8e00c25305f2bc5e9d2ce3e0412fe66c7bad0bf2ede405d4b81cd6e212623c
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 4J counts:

```text
canonical=69
approved_aliases=89
aliases_total=89
```

### Completed Batch 4K

Applied master table:

```text
4.1.8 Sekolah Menengah Kejuruan (SMK) under Kementerian Pendidikan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4k_418_smk_20260706-023003.dump
sha256=db1dc487c3526d979c7b4e1c9b01d1c980d9597423fa4eaa5810298521c16016
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.1.8 --min-ratio 10
Candidate repairs: 0
```

All created indicators validated clean:

```text
t4_1_8_sekolah_negeri suspicious_jumps=0
t4_1_8_sekolah_swasta suspicious_jumps=0
t4_1_8_sekolah_jumlah suspicious_jumps=0
t4_1_8_guru_negeri suspicious_jumps=0
t4_1_8_guru_swasta suspicious_jumps=0
t4_1_8_guru_jumlah suspicious_jumps=0
t4_1_8_murid_negeri suspicious_jumps=0
t4_1_8_murid_swasta suspicious_jumps=0
t4_1_8_murid_jumlah suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4k_418_smk_validated_20260706-023125.dump
sha256=8e0f65861a3bb4b317ca99ea265a8af22699aa43534ab9726037038efc419ed3
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 4K counts:

```text
canonical=78
approved_aliases=98
aliases_total=98
```

### Completed Batch 4L — Partial Accepted

Applied master table:

```text
4.1.2 Raudatul Athfal (RA) under Kementerian Agama
```

Pre-apply backup:

```text
bps_publikasi_before_batch4l_412_ra_20260706-024032.dump
sha256=ba2ce31bb3cd9a829fe67c3f9074af95158f3f70d131ca8598463f9095449218
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.1.2 --min-ratio 10
Candidate repairs: 0
```

Initial apply created 3 canonical indicators. Parent validation rejected one:

```text
t4_1_2_murid suspicious_jumps=3
```

That canonical indicator and alias were deleted. The accepted indicators are:

```text
t4_1_2_sekolah selected_rows=280 suspicious_jumps=0
t4_1_2_guru selected_rows=280 suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4l_412_ra_partial_validated_20260706-024154.dump
sha256=9ba504e1df6b1e645514e4c6da800afaa25098fc6390b75698cd263e27fa2274
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

### Completed Batch 4M

Applied master table:

```text
4.1.11 Melek Huruf by age group and sex
```

Pre-apply backup:

```text
bps_publikasi_before_batch4m_4111_melek_huruf_repair_apply_20260706-024250.dump
sha256=ab08b028c9f9e071af689723d96c61c3af499c2b307f9616b3397755839570d6
```

Targeted numeric repair applied before aliasing:

```text
table=4.1.11 indicator=Perempuan unit=%
id=123550 raw='16.10' stored=1610 -> 16.10
updated_rows=1
```

All created indicators validated clean:

```text
persentase_penduduk_melek_huruf_jumlah suspicious_jumps=0
persentase_penduduk_melek_huruf_laki_laki suspicious_jumps=0
persentase_penduduk_melek_huruf_perempuan suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4m_4111_melek_huruf_validated_20260706-024342.dump
sha256=3e76f902de68e3a2ce8c27fbb9a465823ca220de37281e7100149441290bdcac
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 4M counts:

```text
canonical=83
approved_aliases=103
aliases_total=103
```

### Bab 4.1 Safe Completion Status After Batch 4M

All `4.1.x` master tables have now been processed at least once. Safe aliases were kept; indicators with source-level jumps were intentionally left unmapped instead of forcing unsafe aliases.

DONE tables:

```text
4.1.4 MI
4.1.7 SMA
4.1.8 SMK
4.1.10 APM/APK
4.1.11 Melek Huruf
```

PARTIAL tables and held indicators:

```text
4.1.1 TK: Guru ASN Swasta, Guru ASN Jumlah
4.1.2 RA: Murid
4.1.3 SD: Guru Swasta, Murid Swasta
4.1.5 SMP: Guru Negeri, Guru Swasta, Guru Jumlah, Murid Swasta
4.1.6 MTs: Murid
4.1.9 MA: Guru, Murid, Guru Swasta, Guru Jumlah, Murid Swasta, Murid Jumlah
```

Read-only source audit summary for held indicators:

```text
4.1.1 Guru ASN Swasta/Jumlah: many 2023->2024 jumps such as 1 -> 43; not a numeric separator candidate.
4.1.2 Murid: Pancatengah 2023=1068 -> 2024=1 -> 2025=1041; selected source raw='1'. Needs source/PDF review.
4.1.3 Guru Swasta/Murid Swasta: mixed source discontinuities; e.g. kabupaten total 2023=1 -> 2024=241 and subject-level drops.
4.1.5 Guru/Murid held columns: selected newest sources contain isolated subject drops such as Karangjaya 348 -> 20 -> 281 and Jatiwaras 224 -> 14 -> 161.
4.1.6 Murid: broad source discontinuity with 58 jumps; examples include Sukarame 39 -> 3133 and older 2498 -> 104 -> 2998.
4.1.9 Guru/Murid held columns: many jumps are source/year discontinuities or plain integer rows, not separator-normalization candidates.
```

Rule: do not force-map the held indicators until source/PDF extraction is repaired or a manual source decision is made. They are intentionally excluded from approved aliases.

Plain-language interpretation for future work:

```text
Bab 4.1 is not "empty" or simply "unfinished". Every 4.1 master table has been attempted.
The remaining gaps are held because the selected time-series would be misleading if mapped now:
- some rows contain raw values like 1 in the middle of thousand-scale student series;
- some category series jump from one-digit values to hundreds/thousands across publication years;
- several jumps are plain integer source rows, not decimal/thousand separator parse bugs;
- education tables mix school-year, category, status, and source-publication structures, so a matching column label alone is not enough evidence.

Therefore, continue other chapters using safe alias apply. Return to held 4.1 indicators only after PDF/source extraction repair or an explicit manual decision.
```

### Completed Batch 4N

Applied master table:

```text
4.2.1 Desa/Kelurahan with health facilities by kecamatan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4n_421_sarana_kesehatan_20260706-025652.dump
sha256=959e9db7d45bd49a1d9d49ed5f3e655b905335514c1664667bac26d73e85c368
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.2.1 --min-ratio 10
Candidate repairs: 0
```

Created/accepted canonical indicators:

```text
apotek suspicious_jumps=0
balai_kesehatan no numeric rows after filters; all master rows are '-'/'..'
klinik_pratama suspicious_jumps=0
klinik_utama suspicious_jumps=0
poliklinik suspicious_jumps=0
puskesmas suspicious_jumps=0
puskesmas_pembantu suspicious_jumps=0
t4_2_1_rumah_sakit_khusus suspicious_jumps=0
t4_2_1_rumah_sakit_umum suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4n_421_sarana_kesehatan_validated_20260706-025821.dump
sha256=3bf3c01b09f23242a0d0143746ee2928eefc9ecf13a36a497714accfb96da49b
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 4N counts:

```text
canonical=92
approved_aliases=112
aliases_total=112
```

### Completed Batch 4O — Partial Accepted

Applied master table:

```text
4.2.2 Tenaga kesehatan by kecamatan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4o_422_tenaga_kesehatan_20260706-030250.dump
sha256=6706277b6599a35021681f67a8ed53563b07e37e1634ebb648e6836874841ebc
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.2.2 --min-ratio 10
Candidate repairs: 0
```

Initial apply created 5 canonical indicators. Parent validation rejected two:

```text
dokter suspicious_jumps=2
perawat suspicious_jumps=4
```

Those canonical indicators and aliases were deleted. The accepted indicators are:

```text
bidan selected_rows=239 suspicious_jumps=0
dokter_gigi selected_rows=68 suspicious_jumps=0
tenaga_kefarmasian selected_rows=198 suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4o_422_tenaga_kesehatan_partial_validated_20260706-030445.dump
sha256=6d59447657bb04166d76d589ddc20f3da44772e88d1e34d1fd5d97efb2ece690
```

### Completed Batch 4P

Applied master table:

```text
4.2.3 Health facilities by kecamatan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4p_423_fasilitas_kesehatan_20260706-030550.dump
sha256=3138bd4ca68534d0b99b1820b201605915541a092d48366bcc6de91ecbbc79d3
```

Dry-run numeric repair:

```text
repair_numeric_values --table-number 4.2.3 --min-ratio 10
Candidate repairs: 0
```

All created indicators validated clean:

```text
puskesmas_non_rawat_inap suspicious_jumps=0
puskesmas_rawat_inap suspicious_jumps=0
t4_2_3_rumah_sakit_khusus suspicious_jumps=0
t4_2_3_rumah_sakit_umum suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4p_423_fasilitas_kesehatan_validated_20260706-030641.dump
sha256=30a37ac4a5c99f3f2c6bb06800c7a25fcf3e22770c068b196a124e32b79cc764
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Bab 4.2 safe status:

```text
4.2.1 DONE
4.2.2 PARTIAL: held Dokter, Perawat due source-level jumps; no numeric-repair candidates.
4.2.3 DONE
```

Post-Batch 4P counts:

```text
canonical=99
approved_aliases=120
aliases_total=120
```

### Completed Batch 4Q — Partial Accepted

Applied master table:

```text
4.3.1 Population by religion
```

Accepted indicators:

```text
budha suspicious_jumps=0
islam suspicious_jumps=0
katolik suspicious_jumps=0
t4_3_1_lainnya suspicious_jumps=0
```

Held/rolled back indicators:

```text
hindu: Kabupaten Tasikmalaya 2024=3 -> 2025=39; no numeric-repair candidates.
protestan: Ciawi 2024=1 -> 2025=203 and other minority-count source jumps; no numeric-repair candidates.
```

Post-validated backup:

```text
bps_publikasi_after_batch4q_431_agama_penduduk_partial_validated_20260706-031345.dump
sha256=b2ab0601f43ff94c3bd0374af16466eab04f0d14a6252e4c3f98b57f8094d58a
```

### Completed Batch 4R — Partial Accepted

Applied master table:

```text
4.3.2 Places of worship by kecamatan
```

Accepted indicators:

```text
gereja_katholik suspicious_jumps=0
gereja_protestan suspicious_jumps=0
masjid suspicious_jumps=0
pura suspicious_jumps=0
vihara suspicious_jumps=0
```

Held/rolled back indicator:

```text
mushola: Mangunreja/Sukarame source-level jumps such as 3 -> 54 -> 5; no numeric-repair candidates.
```

Post-validated backup:

```text
bps_publikasi_after_batch4r_432_tempat_peribadatan_partial_validated_20260706-031629.dump
sha256=3766ccbdeb192cdf9be6524541675035384d283c32feae3fda5d852c1ac46bbd
```

### Completed Batch 4S — Partial Accepted

Applied master table:

```text
4.3.3 Villages affected by natural disasters
```

Accepted indicator:

```text
banjir suspicious_jumps=0
```

Held/rolled back indicator:

```text
tanah_longsor: Gunungtanjung/Cikatomas source-level jumps such as 17 -> 1 and 1 -> 15; no numeric-repair candidates.
```

Post-validated backup:

```text
bps_publikasi_after_batch4s_433_bencana_alam_partial_validated_20260706-031854.dump
sha256=da779e5d9730bc6c7f774940c145878219731d4bfdd18b51d4a6ad0e50265163
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Bab 4.3 safe status:

```text
4.3.1 PARTIAL: held Protestan, Hindu
4.3.2 PARTIAL: held Mushola
4.3.3 PARTIAL: held Tanah Longsor
```

Post-Batch 4S counts:

```text
canonical=109
approved_aliases=130
aliases_total=130
```

### Completed Batch 4T

Applied master table:

```text
4.4.1 Garis Kemiskinan, jumlah, and persentase penduduk miskin
```

Pre-apply backup:

```text
bps_publikasi_before_batch4t_441_kemiskinan_repair_apply_20260706-032338.dump
sha256=214bde76259faea47d9c22ea363bd309cd4c4f977db7ebdc4987598a6c1b43f2
```

Targeted numeric repair applied before aliasing:

```text
table=4.4.1 indicator='Jumlah Penduduk Miskin' unit=ribu
updated_rows=12
examples: 2081 -> 208.1, 1956 -> 195.6, 1894 -> 189.4
```

Created/accepted indicator:

```text
garis_kemiskinan suspicious_jumps=0
```

### Completed Batch 4U

Applied master table:

```text
4.4.2 Indeks Kedalaman Kemiskinan and Indeks Keparahan Kemiskinan
```

Pre-apply backup:

```text
bps_publikasi_before_batch4u_442_indeks_kemiskinan_repair_apply_20260706-032449.dump
sha256=59fb2951681d82575be18443644fd780d170218fe410f3ee39d9100ef21b567b
```

Targeted numeric repair applied before aliasing:

```text
table=4.4.2 indicator='Indeks Kedalaman Kemiskinan'
updated_rows=3
examples: 84 -> 0.84, 83 -> 0.83
```

All created indicators validated clean:

```text
indeks_kedalaman_kemiskinan suspicious_jumps=0
indeks_keparahan_kemiskinan suspicious_jumps=0
```

Post-validated backup:

```text
bps_publikasi_after_batch4u_442_indeks_kemiskinan_validated_20260706-032537.dump
sha256=96193806dcbafc7c782c7da97cf0e273ffa3a66f856b3f371790d0b2ecbd289a
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Bab 4 safe status after Batch 4U:

```text
DONE tables: 9
PARTIAL tables: 10
NOT_STARTED tables: 0

Bab 4.1: safe-complete; remaining held indicators require source/PDF repair.
Bab 4.2: 4.2.1 DONE, 4.2.2 PARTIAL (Dokter, Perawat held), 4.2.3 DONE.
Bab 4.3: all attempted; Protestan/Hindu, Mushola, Tanah Longsor held due source-level jumps.
Bab 4.4: DONE.
```

Post-Batch 4U counts:

```text
canonical=112
approved_aliases=133
aliases_total=133
```

### Completed Batch 5A — Partial Accepted

Applied master table:

```text
5.1.1 Luas lahan sawah by irrigation type
```

Numeric repair applied first:

```text
table=5.1.1 all candidates, updated_rows=36
examples: 2,040 -> 2040; 29,126 -> 29126
```

Accepted indicator:

```text
luas_area_jumlah suspicious_jumps=0
```

Held/rolled back indicators:

```text
irigasi: source-level Gunungtanjung jump 47 -> 616; no further repair candidates.
non_irigasi: multiple source-level jumps such as Sukaraja 1688 -> 74; no further repair candidates.
```

Post-validated backup:

```text
bps_publikasi_after_batch5a_511_lahan_sawah_partial_validated_20260706-033325.dump
sha256=66647c414044844f9a91068172bcb101e62b82babe83b0e778de8465eb24e2a8
```

### Completed Batch 5B — Partial Accepted

Applied master table:

```text
5.1.2 Luas lahan tegal/kebun, ladang/huma, and temporarily unused land
```

Numeric repair applied first:

```text
table=5.1.2 all candidates, updated_rows=70
examples: 2,911 -> 2911; 6,969 -> 6969
```

Accepted indicators:

```text
ditanami_pohon_hutan suspicious_jumps=0
hutan_negara suspicious_jumps=0
padang_penggembalaan suspicious_jumps=0
```

Held/rolled back indicators:

```text
tegal_kebun, ladang_huma, perkebunan, sementara_tidak_diusahakan, t5_1_2_lainnya: source-level jumps remain after repair.
```

Post-validated backup:

```text
bps_publikasi_after_batch5b_512_lahan_bukan_sawah_partial_validated_20260706-033940.dump
sha256=e4b262b87d74750cce38a29d0ae447d1082078c781268b3e55b8224b00ea054c
```

### Completed Batch 5C — Partial Accepted

Applied master table:

```text
5.1.3 Luas panen padi sawah and padi ladang
```

Important repair note:

```text
Skipped generic repair suggestions that would turn dot-thousands values such as 4.790 into 47.9.
Applied targeted custom comma-thousands repair for publication 2022 table 5.1.3 only.
updated_rows=41
examples: 5,208 -> 5208; 117,,923 -> 117923
```

Accepted indicator:

```text
luas_panen_padi_sawah suspicious_jumps=0
```

Held/rolled back indicator:

```text
luas_panen_padi_ladang: source-level volatility remains after safe comma repair.
```

Post-validated backup:

```text
bps_publikasi_after_batch5c_513_luas_panen_padi_partial_validated_20260706-034341.dump
sha256=a897f0d7e2692e2ab01db7a01d5620932ad5923e89dec03f801ae1dc07e28240
```

### Completed Batch 5D — Partial Accepted

Applied master table:

```text
5.1.4 Produksi padi sawah and padi ladang
```

Numeric repair applied first:

```text
table=5.1.4 all candidates, updated_rows=45
examples: 36,122 -> 36122; 53,576 -> 53576
```

Accepted indicator:

```text
produksi_padi_sawah suspicious_jumps=0
```

Held/rolled back indicator:

```text
produksi_padi_ladang: source-level jumps remain after repair.
```

Post-validated backup:

```text
bps_publikasi_after_batch5d_514_produksi_padi_partial_validated_20260706-034545.dump
sha256=da0160abb059216e780f2fc751a72b7db1b7d988e333277f0bb97f2e657d675c
```

### Completed Batch 5E — Partial Accepted

Applied master table:

```text
5.1.5 Luas panen jagung/kedelai/kacang/ubi
```

Important repair note:

```text
Skipped generic dot-thousands repair suggestions, e.g. 1.417 ha should remain 1417 ha rather than 14.17 ha.
```

Accepted indicator:

```text
luas_panen_kacang_hijau suspicious_jumps=0
```

Held/rolled back indicators:

```text
luas_panen_jagung, luas_panen_kedelai, luas_panen_kacang_tanah, luas_panen_ubi_kayu, luas_panen_ubi_jalar: source-level jumps.
```

Post-validated backup:

```text
bps_publikasi_after_batch5e_515_luas_panen_palawija_partial_validated_20260706-035121.dump
sha256=1e08addb5d0b0d7b299db8e5f1779be915c88c23f24546cbee1cb50e54377205
```

### Completed Batch 5F — Partial Accepted

Applied master table:

```text
5.1.6 Produksi jagung/kedelai/kacang/ubi
```

Numeric repair applied first:

```text
table=5.1.6 all candidates, updated_rows=41
examples: 4,101 -> 4101; 14,250 -> 14250
```

Accepted indicators:

```text
produksi_jagung suspicious_jumps=0
produksi_kacang_hijau suspicious_jumps=0
```

Held/rolled back indicators:

```text
produksi_kedelai, produksi_kacang_tanah, produksi_ubi_kayu, produksi_ubi_jalar: source-level jumps.
```

Post-validated backup:

```text
bps_publikasi_after_batch5f_516_produksi_palawija_partial_validated_20260706-035453.dump
sha256=2048597532476710a1cc7fc51a6643918959c321829c549819bcdbf6531a31ab
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Bab 5.1 safe status after Batch 5F:

```text
5.1.1 PARTIAL: accepted 1/3
5.1.2 PARTIAL: accepted 3/8
5.1.3 PARTIAL: accepted 1/2
5.1.4 PARTIAL: accepted 1/2
5.1.5 PARTIAL: accepted 1/6
5.1.6 PARTIAL: accepted 2/6
```

Post-Batch 5F counts:

```text
canonical=121
approved_aliases=144
aliases_total=144
```

### Batch 5G — Applied, Anomalies Recorded for Later Review

Applied master table:

```text
5.2.1 Luas panen tanaman sayuran by kecamatan and crop type
```

Operator decision from user:

```text
From Batch 5G onward, do not stop/rollback solely for volatile jumps. Apply safe dry-run aliases, defer ambiguous repairs, and record jump/duplicate anomalies for manual cleanup after all tables are covered.
```

Repair decision:

```text
Generic repair suggestions were deferred because values such as 17.000, 41.202, and 155.688 in vegetable/harvest tables are ambiguous without checking source PDF/table semantics.
```

Applied result:

```text
canonical_created=10
aliases_written=17
conflicts_skipped=20
unchanged=74
```

Anomalies to review later:

```text
luas_panen_bawang_merah: duplicate_candidates=709 suspicious_jumps=13
luas_panen_buncis: duplicate_candidates=143 suspicious_jumps=11
luas_panen_cabai_besar: duplicate_candidates=142 suspicious_jumps=4
luas_panen_cabai_keriting: duplicate_candidates=33 suspicious_jumps=2
luas_panen_cabai_rawit: duplicate_candidates=218 suspicious_jumps=1
luas_panen_kacang_panjang: duplicate_candidates=127 suspicious_jumps=1
luas_panen_kubis: duplicate_candidates=46 suspicious_jumps=1
luas_panen_bawang_putih, luas_panen_kentang: sparse/missing years but suspicious_jumps=0
luas_panen_tomat: suspicious_jumps=0
```

Pre-apply backup:

```text
bps_publikasi_before_batch5g_521_luas_panen_sayuran_apply_no_repair_20260706-040805.dump
sha256=1115505a69e887007a932634241d50ca7f9503f23fdb70b8fc85e70aa58078a7
```

Post-validated backup:

```text
bps_publikasi_after_batch5g_521_luas_panen_sayuran_applied_anomalies_recorded_20260706-040932.dump
sha256=07a58edbcb18cebbafe4125484aae6e40d0cba175c122d0171c39f4825952c97
```

### Batch 5H — Applied, Anomalies Recorded for Later Review

Applied master table:

```text
5.2.2 Produksi tanaman sayuran by kecamatan and crop type
```

Repair/unit decision:

```text
Generic numeric repair was deferred. Some older rows use source unit `ton` while master 2026 label is `kuintal`; conversion/normalization must be reviewed manually after all tables are covered.
```

Applied result:

```text
canonical_created=10
aliases_written=16
conflicts_skipped=4
unchanged=58
```

Anomalies to review later:

```text
produksi_bawang_merah: duplicate_candidates=709 suspicious_jumps=14
produksi_buncis: duplicate_candidates=98 suspicious_jumps=8
produksi_cabai_besar: duplicate_candidates=105 suspicious_jumps=18
produksi_cabai_keriting: duplicate_candidates=33 suspicious_jumps=2
produksi_cabai_rawit: duplicate_candidates=216 suspicious_jumps=3
produksi_kacang_panjang: duplicate_candidates=128 suspicious_jumps=2
produksi_kubis: duplicate_candidates=22 suspicious_jumps=3
produksi_tomat: duplicate_candidates=114 suspicious_jumps=20
produksi_bawang_putih, produksi_kentang: sparse/missing years but suspicious_jumps=0
```

Pre-apply backup:

```text
bps_publikasi_before_batch5h_522_produksi_sayuran_apply_no_repair_20260706-041041.dump
sha256=f9522c1b367e79407941331fefd814158c6cde8f39d6123550d34606dd6fa579
```

Post-validated backup:

```text
bps_publikasi_after_batch5h_522_produksi_sayuran_applied_anomalies_recorded_20260706-041216.dump
sha256=e1f6e79cf76f82093fe4c25adc12d26f000b496a5cf1ebfd2edcd94daf11a690
```

### Batch 5I — Applied, Anomalies Recorded for Later Review

Applied master table:

```text
5.2.3 Luas panen tanaman sayuran dan buah-buahan semusim by crop type
```

Repair decision:

```text
Generic repair suggestions were deferred. This table uses repeated generic label `Luas Panen`; it was mapped as table-scoped canonical `t5_2_3_luas_panen` and should be manually reviewed by crop/year context later.
```

Applied result:

```text
canonical_created=1
aliases_written=1
conflicts_skipped=0
unchanged=3
```

Anomalies to review later:

```text
t5_2_3_luas_panen: duplicate_candidates=107 suspicious_jumps=2
```

Pre-apply backup:

```text
bps_publikasi_before_batch5i_523_luas_panen_semusim_apply_no_repair_20260706-041329.dump
sha256=bd2425fc22360cc94dbe095ecb2d1f0136f71e4b38bf8303415f346b05ecdaf2
```

Post-validated backup:

```text
bps_publikasi_after_batch5i_523_luas_panen_semusim_applied_anomalies_recorded_20260706-041410.dump
sha256=b8776dd7a0ba6ae9fc271edc89014a22ebaf2a17f0b116bccfe798177879e690
```

### Batch 5J — Applied, Numeric Repair + Anomalies Recorded

Applied master table:

```text
5.2.4 Produksi tanaman sayuran dan buah-buahan semusim by crop type
```

Numeric repair applied:

```text
updated_rows=24
examples: 21351 -> 2135.1; 16,008.31 parsed 16.0083 -> 16008.31
unit ton↔kuintal semantics still require manual review later.
```

Applied result:

```text
canonical_created=1
aliases_written=1
conflicts_skipped=0
unchanged=3
```

Anomalies to review later:

```text
t5_2_4_produksi: duplicate_candidates=108 suspicious_jumps=14
```

Pre-apply backup:

```text
bps_publikasi_before_batch5j_524_produksi_semusim_repair_apply_20260706-041447.dump
sha256=0998bd9043116f9ac5107244abbfb20aab6be9c178ea986ae627d404863386c0
```

### Held Table 5.3.1 — Luas Areal Tanaman Perkebunan

Status: **HELD / do not apply aliases yet**.

PDF-backed findings:

```text
2021 PDF page 352, Table 5.3.1 title: (ha), 2019 dan 2020.
Vision evidence: Cipatujah Kelapa/Coconut 2019=2.605, 2020=2.603; Kelapa Sawit columns are '-'/'-'.
DB issue: publication 2021 table_id=703 labels every first 12 columns as `Luas Areal Kelapa Sawit`, so DB row id=133934 raw='2.605' is mislabeled as Kelapa Sawit even though PDF shows it belongs to Kelapa/Coconut.

2022 PDF page 353, Table 5.3.1 title: (Ribu ha), 2020 dan 2021 / Thousand ha.
Vision evidence: Cipatujah Kelapa Sawit 2021=0; Kelapa/Coconut 2020=2.603, 2021=1.788.
DB issue: unit_alias remains `ha`, so scale/unit policy must be handled explicitly before aliasing.

Repair warning: dry-run proposed `2.605 -> 26.05`, but vision confirms the printed 2021 ha value means 2605 ha. This repair is a false positive.
```

Decision:

```text
Skip 5.3.1 in safe pass.
Needs source-PDF/vision-driven extraction repair or narrow per-year/per-column alias policy.
Do not apply same-table aliases until 2021 column labels and 2022/2023 Ribu ha unit semantics are corrected.
```

### Held Table 5.3.2 — Produksi Perkebunan

Status: **HELD / do not apply aliases yet**.

PDF-backed findings:

```text
2022 PDF page 359, Table 5.3.2 title: (Ribu ton), 2020 dan 2021 / Thousand ton.
Vision evidence: Cipatujah Kelapa Sawit 2020='-', 2021='-'; Kelapa/Coconut 2020=3.5560, 2021=3.645.
DB issue: publication 2022 stores the unit alias as `ton`; numeric values such as raw='3.5560' are stored as 35560.0000, and generic repair proposes 3.5560. Correct canonical handling requires explicit unit policy (Ribu ton -> ton or keep Ribu ton), not blind parser repair.

2021 DB issue: publication 2021 table_id=704 labels the first 12 columns as `Produksi Kelapa Sawit`, mirroring the 5.3.1 extraction-label failure; raw='3.560' and '3.556,00' belong to Kelapa/Coconut in the source layout, not Kelapa Sawit.
```

Decision:

```text
Skip 5.3.2 in safe pass.
Requires PDF/vision-backed extraction repair and explicit Ribu ton scale policy before aliasing.
```

### Completed Batch 5K–5T — Bab 5.2 Safe Coverage Pass

Applied remaining Bab 5.2 tables:

```text
5.2.5  Luas Panen Tanaman Biofarmaka by kecamatan
5.2.6  Produksi Tanaman Biofarmaka by kecamatan
5.2.7  Luas Panen Biofarmaka aggregate
5.2.8  Produksi Biofarmaka aggregate
5.2.9  Luas Panen Tanaman Hias by kecamatan
5.2.10 Produksi Tanaman Hias by kecamatan
5.2.11 Luas Panen Tanaman Hias aggregate
5.2.12 Produksi Tanaman Hias aggregate
5.2.13 Produksi Buah-buahan by kecamatan
5.2.14 Produksi Buah/Sayuran Tahunan aggregate
```

Numeric repairs applied:

```text
5.2.13: updated_rows=675; decimal parser repair such as 12777 -> 127.77 for raw '127.77'.
5.2.14: updated_rows=21; thousands/decimal parser repair such as 41.5164 -> 41516.39 for raw '41,516.39'.
```

Deferred/manual-review policy:

```text
Volatile jumps, duplicate candidates, sparse years, generic labels (`Luas Panen`, `Produksi`), and unit semantics are now recorded for later PDF-backed cleanup rather than rolled back immediately.
Use `references/django-publication-pdf-vision-verification.md`: locate PDF page -> render to image -> inspect with Hermes vision -> compare exact DB row -> repair only with source proof.
```

Bab 5.2 runtime coverage after Batch 5T:

```text
5.2.1  DONE 20/20
5.2.2  DONE 20/20
5.2.3  DONE 4/4
5.2.4  DONE 4/4
5.2.5  DONE 12/12
5.2.6  DONE 12/12
5.2.7  DONE 4/4
5.2.8  DONE 4/4
5.2.9  DONE 12/12
5.2.10 DONE 14/14
5.2.11 DONE 4/4
5.2.12 DONE 4/4
5.2.13 DONE 16/16
5.2.14 DONE 2/2
```

Post-validated backup:

```text
bps_publikasi_after_batch5t_5214_bab52_complete_applied_anomalies_recorded_20260706-044131.dump
sha256=5ec7636488976ce1368f0c6a73cccf3636518c70ab851099e0256daa5862d927
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 5T counts:

```text
canonical=181
approved_aliases=227
aliases_total=227
```

### Completed Batch 5U–5V — Bab 5.3 Safe Pass

Safe-applied tables:

```text
5.3.3 Luas Areal Tanaman Perkebunan Rakyat aggregate — DONE 5/5
5.3.4 Produksi Perkebunan Rakyat aggregate — DONE 5/5
```

Held tables:

```text
5.3.1 Luas Areal Tanaman Perkebunan by kecamatan — HELD for PDF-backed extraction/unit repair.
5.3.2 Produksi Perkebunan by kecamatan — HELD for PDF-backed extraction/unit repair.
```

Evidence and repairs:

```text
5.3.3: vision-confirmed PDF 2026 page 268, unit ha. Updated_rows=35.
Examples: Karet 149.61, Kelapa 25,694.30, Lada 444.50.
Validator: luas_areal selected_rows=70, years=2021..2025, duplicate_candidates=16, suspicious_jumps=0.

5.3.4: Hermes vision unavailable (connection error), fallback PDF text extraction page 269 confirmed unit ton and exact raw values.
Updated_rows=35.
Examples: Karet 229.97, Kelapa 27,574.35, Kopi Robusta 1,390.10, Lada 314.83.
Validator: t5_3_4_produksi selected_rows=64, years=2021..2025, duplicate_candidates=16, suspicious_jumps=0.
```

Backups:

```text
pre 5.3.3: bps_publikasi_before_batch5u_533_luas_areal_perkebunan_aggregate_pdf_repair_apply_20260706-045558.dump
sha256=63d9deb0d596d3807744022f1a1cf77bd243c7d8a59948f88705cff9ec95c4b7

post 5.3.3: bps_publikasi_after_batch5u_533_luas_areal_aggregate_pdf_repair_applied_20260706-045700.dump
sha256=6b2d5b43f76c7eda4bd1c51c3918dfc056de63ada3308685ee2a1e94975c02b4

pre 5.3.4: bps_publikasi_before_batch5v_534_produksi_perkebunan_aggregate_text_repair_apply_20260706-050304.dump
sha256=0346cadd2ffea6467809364fae81dd2ea54773224610805e7c1bab97bb245be0

post 5.3 safe pass: bps_publikasi_after_batch5v_534_bab53_safe_pass_applied_holds_recorded_20260706-050407.dump
sha256=e22beea4707899887631bfbb3c416f32abbf482cee60a35ba28229925b1936d2
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 5V counts:

```text
canonical=183
approved_aliases=229
aliases_total=229
```

### Completed Batch 5W–5Y — Bab 5.4 Livestock Safe Pass

Applied tables:

```text
5.4.1 Populasi Ternak — DONE 12/12
5.4.2 Populasi Unggas — DONE 8/8
5.4.3 Hasil Produksi Peternakan — DONE 4/4
```

PDF/vision-backed repairs:

```text
5.4.1: updated_rows=232. Vision-confirmed 2022 page 365 and 2026 page 272: comma values are livestock counts, e.g. Cipatujah Sapi Potong 6,304 -> 6304; Kambing 1,546 -> 1546; Domba 16,763 -> 16763.
5.4.2: updated_rows=299. Vision-confirmed 2022 page 369: Cipatujah Ayam Kampung 110,527 -> 110527; Ayam Petelur 25,760 -> 25760.
5.4.3: updated_rows=369. Vision-confirmed 2022 pages 373 and 375: decimal ton values, e.g. Sapi Potong 13.73 -> 13.73; Kambing 22.99 -> 22.99; Domba 40.24 -> 40.24.
```

Validators:

```text
5.4.1: all six livestock indicators selected_rows=63..321, years=2018..2025; suspicious_jumps remain for source-volatility/manual PDF review except sapi_perah and sapi_potong.
5.4.2: four poultry indicators selected_rows=297..321, years=2018..2025; suspicious_jumps recorded for later review.
5.4.3: hasil_produksi selected_rows=59, years=2021..2025, duplicate_candidates=36, suspicious_jumps=9.
```

Backups:

```text
pre 5.4.1: bps_publikasi_before_batch5w_541_populasi_ternak_pdf_repair_apply_20260706-051018.dump
sha256=1fc49ea2314813b3ad963ae91f7a458158de174695e14b1ac30f7a15d93603d1

post 5.4.1: bps_publikasi_after_batch5w_541_populasi_ternak_pdf_repair_applied_anomalies_recorded_20260706-051124.dump
sha256=bf6d270dcf063dfda983be71b00ffe9e56b46c2419bf91fe6f3cffbb54b686eb

pre 5.4.2: bps_publikasi_before_batch5x_542_populasi_unggas_pdf_repair_apply_20260706-051255.dump
sha256=fa5317d099581946ff4fc4d6db7ebd76805d073b3e3fb92e7db7da8d3a07bebc

post 5.4.2: bps_publikasi_after_batch5x_542_populasi_unggas_pdf_repair_applied_anomalies_recorded_20260706-051353.dump
sha256=79bd988026fff34f6f90e1cf6f825ac16be63abd99bfd801ccae3ad0af0d47ce

pre 5.4.3: bps_publikasi_before_batch5y_543_produksi_peternakan_pdf_repair_apply_20260706-051548.dump
sha256=5f9b94d287febe6a34ebd05577a8453e1091a23532b2866343942c6a5dc04686

post 5.4 complete: bps_publikasi_after_batch5y_543_bab54_complete_pdf_repairs_applied_anomalies_recorded_20260706-051632.dump
sha256=f5465c18d6532a6cc9db5721877cd92252d2c52c9bcc51b0f84643fa9a759f88
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 5Y counts:

```text
canonical=194
approved_aliases=241
aliases_total=241
```

### Completed Batch 5Z–5AB — Bab 5.5 Fishery Safe Pass

Applied tables:

```text
5.5.1 Produksi Perikanan Laut — DONE 2/2, alias-only; false numeric repairs skipped.
5.5.2 Produksi Budidaya Perikanan — DONE 6/6.
5.5.3 Produksi Benih Ikan — DONE 2/2, master-only because old table number drifted.
```

PDF/vision-backed decisions and repairs:

```text
5.5.1: numeric repair skipped intentionally. Vision-confirmed PDF 2026 page 279: values like 23.386 mean 23386 ton (dot thousands), but 0,426 means 0.426 ton (comma decimal). Generic repair candidates 0,426 -> 426 are false positives.
5.5.2: updated_rows=90. Vision-confirmed PDF 2022 pages 386/388: 1200.00 means 1200.00 ton; 5,200 means 5200 ton.
5.5.3: updated_rows=177. Vision-confirmed PDF 2022 pages 390/392: 100.00 / 90.00 / 10.00 are decimal ton values; 1,370 means 1370 ton. Alias applied only to 2026 master because 2022 table number 5.5.3 is different concept (aquaculture commodities, ton), while 2026 5.5.3 is fish seed production (000 ekor).
```

Validators:

```text
5.5.1: t5_5_1_produksi selected_rows=148, years=2019..2025, duplicate_candidates=65, suspicious_jumps=34.
5.5.2: fish commodity validators are noisy (suspicious_jumps 32..82 except udang_vannamei 0), recorded for later PDF/manual review.
5.5.3: t5_5_3_produksi selected_rows=65, years=2019..2025, duplicate_candidates=6, suspicious_jumps=4.
```

Backups:

```text
pre 5.5.1: bps_publikasi_before_batch5z_551_perikanan_laut_alias_only_false_repair_skipped_20260706-052207.dump
sha256=b2a50e64a2c6b920c5badb752dbe391f7f43f40fb92a6cc455f7f1b45f93073c

post 5.5.1: bps_publikasi_after_batch5z_551_perikanan_laut_alias_only_false_repairs_recorded_20260706-052249.dump
sha256=f2102aac25cbf7fbb4fe0a0e6bfd89b4575b4c4b3ac7f7b4f31e1e0fff8526e6

pre 5.5.2: bps_publikasi_before_batch5aa_552_budidaya_perikanan_pdf_repair_apply_20260706-052424.dump
sha256=f52f08c2be81bb2ff859c02883b3b03f0a445fb3f08e8946f9adebf74a33b345

post 5.5.2: bps_publikasi_after_batch5aa_552_budidaya_perikanan_pdf_repair_applied_anomalies_recorded_20260706-052528.dump
sha256=478e13d36ad38d3edc7fe916574d652f43c9c4232dac19d96c048c5c22ec891a

pre 5.5.3: bps_publikasi_before_batch5ab_553_benih_ikan_master_only_pdf_repair_apply_20260706-054742.dump
sha256=974b665cd4191bf3bace6ecb0828f170ed1c9b49e7445dd797a3f207d4fbf247

post Bab 5 safe pass: bps_publikasi_after_batch5ab_553_bab55_complete_bab5_safe_pass_20260706-054822.dump
sha256=e9ceca72a087972ee83d7b9e9051a34277332ad57910a2e11cafece191f6b7b1
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Post-Batch 5AB counts:

```text
canonical=202
approved_aliases=249
aliases_total=249
```

Bab 5 master-year runtime coverage after safe pass:

```text
DONE=22 tables
PARTIAL=6 tables (5.1.1–5.1.6; earlier Bab 5.1 partials)
HELD/NOT_STARTED=2 tables (5.3.1 and 5.3.2; source extraction/unit issues)
```

### Completed Batch 5AD — Bab 5.1 Safe Alias-Only + Time-series Resolver Fix

Resolved remaining Bab 5 partials:

```text
5.1.1 Luas Lahan Sawah Menurut Jenis Pengairan — DONE 3/3
5.1.2 Luas Lahan Tegal/Kebun/Ladang/etc. — DONE 8/8
5.1.3 Luas Panen Padi Sawah/Padi Ladang — DONE 2/2
5.1.4 Produksi Padi Sawah/Padi Ladang — DONE 2/2
5.1.5 Luas Panen Palawija — DONE 6/6
5.1.6 Produksi Palawija — DONE 6/6
```

Numeric decision:

```text
No numeric repairs applied for 5.1.1–5.1.6. Generic repair suggestions in 5.1.3/5.1.5 were false-positive thousands parsing, e.g. `4.790 ha` = 4,790 ha, not 47.90 ha; `1.417 ha` = 1,417 ha, not 14.17 ha.
```

Apply results:

```text
5.1.1: canonical_created=2, aliases_written=2, conflicts_skipped=0, unchanged=18
5.1.2: canonical_created=5, aliases_written=5, conflicts_skipped=0, unchanged=25
5.1.3: canonical_created=1, aliases_written=1, conflicts_skipped=0, unchanged=13
5.1.4: canonical_created=1, aliases_written=1, conflicts_skipped=0, unchanged=13
5.1.5: canonical_created=5, aliases_written=5, conflicts_skipped=0, unchanged=37
5.1.6: canonical_created=4, aliases_written=4, conflicts_skipped=0, unchanged=38
```

Resolver fix:

```text
Fixed apps.data.timeseries._build_alias_filter so approved aliases match all raw Indikator rows sharing the alias normalized label. This prevents whitespace/punctuation variants such as `Produksi Jagung` vs `Produksi  Jagung` from silently dropping years.
Regression test added: test_alias_matches_normalized_indicator_name_variants.
Before fix, produksi_jagung validator only selected 31 rows from 2023; after fix it selects 250 rows across 2019..2025.
```

Validators/highlights:

```text
produksi_jagung selected_rows=250 years=2019..2025 duplicate_candidates=0 suspicious_jumps=21
luas_panen_jagung selected_rows=254 years=2019..2025 duplicate_candidates=0 suspicious_jumps=33
All Bab 5 master-year runtime coverage: DONE=30 tables, PARTIAL=0, HELD=0.
```

Backups:

```text
pre 5.1 safe alias-only: bps_publikasi_before_batch5ad_51_safe_alias_only_20260706-061618.dump
sha256=4ef9814ba4b369cdb20b98762ac2b6f97cd84834be214f3181f30632817e2153

post 5.1 safe alias-only + resolver fixed: bps_publikasi_after_batch5ad_51_complete_alias_only_resolver_fixed_20260706-062142.dump
sha256=094a12bd2b0f2aa48db9de5259c6d8f88b1f3879c600376953497e40a2471725
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 17 tests OK
```

### Completed Batch 5AC — Held Bab 5.3.1/5.3.2 Resolved

Resolved formerly held plantation tables:

```text
5.3.1 Luas Areal Tanaman Perkebunan — DONE 16/16
5.3.2 Produksi Perkebunan — DONE 16/16
```

PDF/vision-backed fixes:

```text
Label fixes: 21 KolomTabel indicator repairs.
- 2021 5.3.1: extraction labeled columns 3–12 as Luas Areal Kelapa Sawit; PDF pages 352/354/356 confirm true groups Kelapa, Karet, Kopi, Kakao, Lada pairs for 2019/2020.
- 2021 5.3.2: extraction labeled columns 3–12 as Produksi Kelapa Sawit; PDF page 358 and continued pages confirm true groups Kelapa, Karet, Kopi, Kakao, Lada pairs for 2019/2020.
- 2023 5.3.1: column 7 was generic `Kopi/ Coffee`; corrected to Luas Areal Kopi.

Ribu-unit numeric fixes: 375 Fakta repairs.
- 2022/2023 5.3.1 titles are `(Ribu ha)/(Thousand ha)`, but canonical/table unit is ha. Source values converted as printed_value * 1000. Vision examples: 2022 Cipatujah Kelapa `2.603` => 2603 ha; 2023 Cipatujah Kelapa `1,790` => 1790 ha.
- 2022/2023 5.3.2 titles are `(Ribu ton)/(Thousand ton)`, but canonical/table unit is ton. Source values converted as printed_value * 1000. Vision examples: 2022 Cipatujah Kelapa `3.5560` => 3556.0 ton; 2023 Cipatujah Kelapa `3,602` => 3602 ton.

2026 dot-decimal repairs: 145 Fakta repairs for 5.3.1.
- PDF 2026 continued Table 5.3.1 uses dot decimals in Kakao/Lada/Teh/Tembakau sections. Vision-confirmed Cipatujah values `0.32`, `1.30`, `4.23`, `7.35` are ha values, not 32/130/423/735.
- Mixed forms are parsed by separator order: `1.798,00` = Indonesian decimal comma; `1,003.13` = US-style thousands+decimal.
```

Apply results:

```text
5.3.1: canonical_created=8, aliases_written=9, conflicts_skipped=5, unchanged=81. Runtime coverage after apply: 16/16.
5.3.2: canonical_created=8, aliases_written=8, conflicts_skipped=0, unchanged=78. Runtime coverage after apply: 16/16.
Residual custom target drift: 0 for 2022/2023 Ribu ha/ton and 0 for 2026 dot-decimal repairs.
```

Validators after Batch 5AC:

```text
luas_areal_kakao selected_rows=223 years=2018..2025 duplicate_candidates=165 suspicious_jumps=7
luas_areal_karet selected_rows=161 years=2018..2025 duplicate_candidates=106 suspicious_jumps=22
luas_areal_kelapa selected_rows=315 years=2018..2025 duplicate_candidates=233 suspicious_jumps=0
luas_areal_kelapa_sawit selected_rows=60 years=2018..2025 duplicate_candidates=50 suspicious_jumps=0
luas_areal_kopi selected_rows=281 years=2018..2025 duplicate_candidates=189 suspicious_jumps=15
luas_areal_lada selected_rows=184 years=2018..2025 duplicate_candidates=96 suspicious_jumps=13
luas_areal_teh selected_rows=53 years=2023..2025 duplicate_candidates=16 suspicious_jumps=2
luas_areal_tembakau selected_rows=18 years=2023..2025 duplicate_candidates=6 suspicious_jumps=0
produksi_kakao selected_rows=187 years=2018..2025 duplicate_candidates=138 suspicious_jumps=1
produksi_karet selected_rows=123 years=2018..2025 duplicate_candidates=91 suspicious_jumps=23
produksi_kelapa selected_rows=313 years=2018..2025 duplicate_candidates=234 suspicious_jumps=1
produksi_kelapa_sawit selected_rows=18 years=2018..2025 duplicate_candidates=14 suspicious_jumps=0
produksi_kopi selected_rows=257 years=2018..2025 duplicate_candidates=185 suspicious_jumps=67
produksi_lada selected_rows=202 years=2018..2025 duplicate_candidates=49 suspicious_jumps=0
produksi_tebu selected_rows=2 years=2023..2024 duplicate_candidates=0 suspicious_jumps=0
produksi_teh selected_rows=34 years=2023..2024 duplicate_candidates=0 suspicious_jumps=0
```

Backups:

```text
pre 5.3.1/5.3.2 held repair: bps_publikasi_before_batch5ac_531_532_held_pdf_repair_apply_20260706-060754.dump
sha256=f4279627df9e926c191f41eccfabbe7c0553a0a598f2709fbe2ded2f2dc4b731

post 5.3.1/5.3.2 held repair: bps_publikasi_after_batch5ac_531_532_held_resolved_pdf_repairs_applied_20260706-061040.dump
sha256=205182a5f55fc4ac59b1de297c21456284682554bced41c0bf3107c40bb8ec85
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

Bab 5 runtime coverage after Batch 5AC:

```text
DONE=24 tables
PARTIAL=6 tables (5.1.1–5.1.6)
HELD=0 tables in Bab 5.3/5.5 safe pass
```

### Completed Batch 1A — Bab 1 Verified Clean

Bab 1 master-year tables:

```text
1.1.1 Luas Daerah Menurut Kecamatan, 2025 — DONE 1/1
1.1.2 Tinggi Wilayah (mdpl) dan Jarak ke Ibukota (km), 2025 — DONE 2/2
```

Findings:

```text
Dry-run showed potential writes but apply produced canonical_created=0 and aliases_written=0; all 20 potential writes were unchanged.
No numeric repair candidates for either table.
No PDF/vision repair needed because validators were clean and no ambiguous numeric candidates appeared.
```

Validators:

```text
jarak_ke_ibukota: selected_rows=277, years=2019..2025, duplicate_candidates=39, suspicious_jumps=0
luas_wilayah: selected_rows=200, years=2018..2025, missing_years=[2019, 2020, 2021], duplicate_candidates=20, suspicious_jumps=0
tinggi_wilayah: selected_rows=319, years=2018..2025, duplicate_candidates=39, suspicious_jumps=0
```

Backups:

```text
pre Bab 1: bps_publikasi_before_batch1a_bab1_safe_apply_20260706-055334.dump
sha256=fe60d6a000d0829a3f40131841cc030897a6c873a258bb219e0d83218bc8e69e

post Bab 1: bps_publikasi_after_batch1a_bab1_verified_clean_20260706-055419.dump
sha256=caf891863a95ce8bdc644dcf914fc641f6da77d645fa93774f4b1acfcfef737b
```

Tests/checks:

```text
python manage.py check -> OK
python manage.py test apps.data -> 16 tests OK
```

### Historical Read-only Scout Finding for Completed Batch 3C

#### Table `3.1.1` — Penduduk/laju/distribusi/kepadatan/rasio

Dry-run result:

```text
master=5
same_auto=10
cross_auto=0
potential writes=15
```

Risks:

- contains existing canonical indicators `kepadatan_penduduk` and `rasio_jenis_kelamin_penduduk`
- review-band suggestions include unsafe weak matches; never include review-band blindly
- broad numeric repair is unsafe

Numeric repair dry-run:

```text
repair_numeric_values --table-number 3.1.1 --min-ratio 10
Candidate repairs: 225
Skipped by ratio: 2
```

Targeted findings:

```text
Jumlah Penduduk + jiwa: 117 candidates
Persentase Penduduk + %: 39 candidates
Rasio Jenis Kelamin: 39 candidates
Laju Pertumbuhan + %: 0 candidates
Kepadatan Penduduk + km2: 30 candidates, likely unsafe false-positive
```

Critical caution:

- Do not run broad `repair_numeric_values --table-number 3.1.1 --apply`.
- Do not repair `Kepadatan Penduduk` blindly; current validator for `kepadatan_penduduk` is already clean.
- `rasio_jenis_kelamin_penduduk` currently has scale issues; handle it separately and carefully.

Recommended validators after any `3.1.1` work:

```bash
python manage.py validate_harmonized_timeseries --indicator-code jumlah_penduduk_menurut_kecamatan --examples 10 --jump-ratio 10
python manage.py validate_harmonized_timeseries --indicator-code laju_pertumbuhan_penduduk_per_tahun_2020_2025_menurut_kecama --examples 10 --jump-ratio 10
python manage.py validate_harmonized_timeseries --indicator-code persentase_penduduk_menurut_kecamatan --examples 10 --jump-ratio 10
python manage.py validate_harmonized_timeseries --indicator-code kepadatan_penduduk --examples 10 --jump-ratio 10
python manage.py validate_harmonized_timeseries --indicator-code rasio_jenis_kelamin_penduduk --examples 10 --jump-ratio 10
```

Historical result: `3.1.1` was completed as Batch 3C with targeted repairs only; broad density repair was skipped.

Before applying:

1. Dry-run each table individually.
2. Use subagents only for read-only risk scouting if helpful.
3. Backup DB.
4. Apply one table or a very small batch.
5. Validate all canonical codes touched by that table.
6. Repair numeric/context issues if validator flags them.
7. Backup post-validated state.

## Subagent Policy

Use subagents for parallel read-only work:

- inspect next batch dry-run risk
- search likely numeric repair candidates
- summarize suspicious validator output
- review docs/status consistency

Do not use subagents for direct DB writes, backups, or apply commands. The parent agent should keep side-effect order deterministic:

```text
backup -> apply -> validate -> repair -> backup
```

Reason: subagents return asynchronously and are self-reported. DB mutation needs verified, ordered, parent-controlled output.
