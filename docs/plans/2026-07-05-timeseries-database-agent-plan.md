# Time-Series Canonical Database Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after user approval.

**Goal:** Membuat layer database dan API yang bisa menjawab query seperti “data penduduk Cisayong 2020-2026” dengan seri waktu yang jelas, unit benar, sumber publikasi/tabel terlihat, dan data bermasalah masuk review queue.

**Architecture:** Pertahankan tabel lama sebagai operational/source layer. Tambahkan layer canonical di atasnya: canonical indicator, alias, unit normalization, observation view/table, quality flags, dan review queue. API React membaca layer canonical, bukan langsung `data_fakta` mentah.

**Tech Stack:** Django 5.2, PostgreSQL 17, pg_trgm, Django REST Framework, React/Vite frontend.

---

## 0. Skill & Agent Setup

Skills yang dipakai:

- `hermes-agent` — panduan penggunaan Hermes, delegation, spawning agent, toolsets.
- `subagent-driven-development` — eksekusi task dengan fresh subagent + 2-stage review.
- `writing-plans` — plan bite-sized, exact files, exact verification.
- `bps-webapi-etl-audit` — audit BPS ETL/tidy data/PostgreSQL.
- `software-delivery-and-review` — review full-stack, security, API, UI.
- `ai-agent-architecture-patterns` — desain orchestration controller/subagent.

OpenSpace skill search untuk query “PostgreSQL tidy data canonical indicators time series...” tidak menemukan skill baru yang lebih relevan; hasilnya mostly unrelated. Jadi local skills di atas cukup.

Subagent yang sudah/akan dipakai untuk planning:

1. **DB Profiler** — audit data PostgreSQL untuk readiness time-series.
2. **Code/API Auditor** — audit Django/React path untuk search + chart.
3. **Agent Orchestrator Planner** — desain fase implementasi + gates + subagent roles.

---

## 1. Current Database Audit Summary

### Core counts

```text
fakta: 162114
publikasi: 9
tabel: 776
kolom_tabel: 4913
indikator: 1395
wilayah: 86
rincian: 2185
```

### Time coverage

```text
total facts: 162114
fakta.tahun filled: 125737
kolom.tahun filled: 125981
tabel.tahun_data filled: 19134
effective_tahun filled via fallback: 162114
range effective_tahun: 2010-2026
distinct effective years: 16
```

Effective year rule used for audit:

```sql
coalesce(f.tahun, kolom.tahun, tabel.tahun_data, publikasi.tahun_terbit - 1)
```

### Example: Cisayong + Penduduk

Region exists:

```text
id=32, nama=Cisayong, jenis=kecamatan
```

Current raw data can answer part of:

```text
Jumlah Penduduk Menurut Kecamatan, Cisayong, 2020-2025
```

Observed values:

```text
2020: 60.324 / 60324
2021: 60,126 / parsed as 60.126  <-- numeric parse problem
2022: 61.974 / 61974
2023: 62.158 / 62158
2024: 62.772 / 62772
2025: 63.761 / 63761
```

Important note: publication 2026 contains effective data year 2025. So if user asks 2020-2026, app should show 2020-2025 and clearly state **2026 data belum tersedia / publikasi 2026 memuat data 2025** unless another source provides 2026.

### Data quality issues found

1. **Indicator fragmentation**

Examples of separate raw indicators that should map to canonical concepts:

```text
Jumlah Penduduk Menurut Kecamatan
Jumlah Penduduk Laki-laki Menurut Kecamatan
Jumlah Penduduk Perempuan Menurut Kecamatan
Penduduk Menurut Kecamatan - Laki-Laki
Penduduk Menurut Kecamatan - Perempuan
[Penduduk] Jumlah
[Penduduk] Laki-Laki
[Penduduk] Perempuan
```

2. **Numeric parsing inconsistent**

Suspicious counts:

```text
comma thousands but parsed small: 1373
 dot thousands but parsed small: 695
 decimal-looking but parsed huge: 1743
```

Concrete examples:

```text
60,126 -> nilai_num 60.126, should likely be 60126 for jiwa
3.19 -> nilai_num 319, should likely be 3.19 for percent
102.79 -> nilai_num 10279, should likely be 102.79 for ratio
```

3. **Duplicate grain exists**

```text
duplicate grain groups by tabel+kolom+wilayah+rincian+tahun: 13
rows in duplicate groups: 26
max duplicate group size: 2
```

4. **Search vector mostly filled but not complete**

```text
data_fakta total: 162114
with search_vector: 161947
```

---

## 2. Current Code/API Audit Summary

### Backend API now

Endpoints:

```text
GET /pencarian/api/search/?q=...
GET /pencarian/api/timeseries/?indikator_id=...
GET /pencarian/api/timeseries/?tabel_id=...
```

Smoke test:

```text
/pencarian/api/search/?q=penduduk -> HTTP 200, tabel=10, indikator=15
/pencarian/api/timeseries/?indikator_id=909 -> HTTP 200, rows=356
```

API output sample:

```json
{
  "id": 147581,
  "tahun": 2010,
  "nilai": "30702.0000",
  "nilai_teks": "30.702",
  "wilayah_nama": "Cibalong",
  "rincian_nama": "-",
  "flag": "ada"
}
```

### Frontend mismatch found

`ChartModal.tsx` expects:

```ts
row.wilayah?.nama
row.nilai_num
```

But serializer returns:

```ts
row.wilayah_nama
row.nilai
```

So current React chart transformation likely cannot render values correctly without a fix.

### Current API gaps

- no `wilayah_id` / `wilayah` filter;
- no year range filter;
- no canonical indicator grouping;
- no source publication/table/page metadata in response;
- no unit metadata;
- no confidence/verified status;
- no warning when requested year is unavailable;
- raw indicator IDs fragment the same concept.

---

## 3. Target UX Query

User query:

```text
penduduk cisayong 2020-2026
```

Expected app behavior:

1. Search understands:
   - indicator/concept: `jumlah_penduduk`
   - region: `Cisayong`
   - year range: 2020-2026
2. App shows one clear result card:
   - **Jumlah Penduduk — Kecamatan Cisayong**
   - Unit: `jiwa`
   - Available years: 2020-2025
   - Missing: 2026 belum tersedia
3. Chart/table output:

```text
2020  60324
2021  60126  (after numeric normalization)
2022  61974
2023  62158
2024  62772
2025  63761
2026  unavailable
```

4. Each point has evidence:
   - publication title/year;
   - table number/title;
   - source page if available;
   - raw value text;
   - normalized value;
   - status: verified / auto-mapped / needs-review.

---

## 4. Proposed Database Layer

Do not drop old tables. Add canonical layer.

### 4.1 CanonicalIndicator

Create model/table:

```text
canonical_indicator
- id
- code unique             e.g. jumlah_penduduk
- name                    e.g. Jumlah Penduduk
- description
- topic                   e.g. Kependudukan
- default_unit_id nullable
- preferred_direction     up/down/neutral optional
- is_active
- created_at/updated_at
```

### 4.2 IndicatorAlias

```text
indicator_alias
- id
- canonical_indicator_id FK
- raw_indicator_id FK referensi_indikator nullable
- alias_text
- normalized_alias
- match_type              manual/exact/fuzzy/imported
- confidence
- is_approved
- notes
```

Seed for population:

```text
jumlah_penduduk:
- Jumlah Penduduk Menurut Kecamatan
- Jumlah Penduduk
- [Penduduk] Jumlah
- Penduduk Jumlah
- Penduduk Jumlah/total
```

Separate canonical concepts:

```text
jumlah_penduduk_laki_laki
jumlah_penduduk_perempuan
persentase_penduduk
kepadatan_penduduk
rasio_jenis_kelamin
laju_pertumbuhan_penduduk
```

### 4.3 Unit normalization

```text
canonical_unit
- id
- code unique             jiwa, persen, km2, per_100_perempuan
- name
- symbol

unit_alias
- id
- canonical_unit_id FK
- alias_text              jiwa, orang, %, persen, per 100 perempuan
- multiplier numeric      e.g. ribu -> 1000
```

### 4.4 Observation canonical table or view

Phase 1 can use a DB view. Phase 2 can materialize/cache.

```text
canonical_observation
- id / fakta_id
- canonical_indicator_id
- wilayah_id
- period_year
- category_jsonb
- canonical_unit_id
- value_raw_text
- value_num_original
- value_num_normalized
- normalization_status
- source_fakta_id
- source_publication_id
- source_table_id
- source_table_number
- confidence_score
- quality_flags jsonb
```

### 4.5 HarmonizationReview

```text
harmonization_review
- id
- object_type             indicator/unit/value/region/period
- source_id
- raw_value
- suggested_target_id
- suggested_value
- confidence
- status                  pending/approved/rejected/corrected
- reviewer_id nullable
- reviewed_at nullable
- notes
```

---

## 5. Implementation Plan: Bite-Sized Tasks

### Task 1: Add read-only database audit management command

**Objective:** Provide repeatable audit command before schema changes.

**Files:**

- Create: `webapp/apps/data/management/commands/audit_timeseries_readiness.py`

**Verification:**

```bash
cd webapp
. .venv/bin/activate
python manage.py audit_timeseries_readiness --query "penduduk" --wilayah "Cisayong" --start-year 2020 --end-year 2026
```

Expected output includes counts, indicator candidates, exact current rows, suspicious numeric parsing warnings.

### Task 2: Add tests for Indonesian numeric normalization

**Objective:** Lock rules before changing data handling.

**Files:**

- Create: `webapp/apps/data/tests/test_numeric_normalization.py`
- Create/modify: `webapp/apps/data/normalization.py`

Test cases:

```text
60.324 + unit jiwa -> 60324
60,126 + unit jiwa -> 60126
3,23 + unit % -> 3.23
3.19 + unit % -> 3.19
102.79 + unit per 100 perempuan -> 102.79
```

### Task 3: Add canonical models

**Objective:** Add schema without touching old data.

**Files:**

- Modify: `webapp/apps/referensi/models.py` or create new app `apps/harmonisasi/`
- Add migrations
- Add admin registration

Models:

```text
CanonicalIndicator
IndicatorAlias
CanonicalUnit
UnitAlias
HarmonizationReview
```

### Task 4: Seed first population canonical dictionary

**Objective:** Prove the desired query using one domain first.

**Files:**

- Create: `webapp/apps/referensi/management/commands/seed_population_harmonization.py`

Seed canonical indicators:

```text
jumlah_penduduk
jumlah_penduduk_laki_laki
jumlah_penduduk_perempuan
persentase_penduduk
kepadatan_penduduk
rasio_jenis_kelamin
laju_pertumbuhan_penduduk
```

### Task 5: Create canonical observation query service

**Objective:** Build read path for canonical time-series.

**Files:**

- Create: `webapp/apps/data/canonical_timeseries.py`
- Tests: `webapp/apps/data/tests/test_canonical_timeseries.py`

Function target:

```python
get_timeseries(
    canonical_code="jumlah_penduduk",
    wilayah="Cisayong",
    start_year=2020,
    end_year=2026,
)
```

Expected result:

```text
2020=60324
2021=60126
2022=61974
2023=62158
2024=62772
2025=63761
2026 missing
```

### Task 6: Add API v2 endpoint

**Objective:** Expose canonical time-series for React/internal BPS.

**Files:**

- Modify/create: `webapp/apps/pencarian/api_v2.py`
- Modify: `webapp/apps/pencarian/urls.py`
- Tests: `webapp/apps/pencarian/tests/test_api_v2_timeseries.py`

Endpoint:

```text
GET /pencarian/api/v2/timeseries/?q=penduduk&wilayah=Cisayong&start_year=2020&end_year=2026
```

Response shape:

```json
{
  "query": {...},
  "resolved": {
    "indicator": {"code": "jumlah_penduduk", "name": "Jumlah Penduduk"},
    "region": {"id": 32, "name": "Cisayong"},
    "unit": {"code": "jiwa", "symbol": "jiwa"}
  },
  "points": [
    {"year": 2020, "value": 60324, "raw_value": "60.324", "status": "mapped", "source": {...}}
  ],
  "missing_years": [2026],
  "quality_warnings": []
}
```

### Task 7: Fix frontend API contract and add filters

**Objective:** React chart uses correct response shape and supports query/region/year.

**Files:**

- Modify: `bps-pencarian/src/lib/api.ts`
- Modify: `bps-pencarian/src/components/features/ChartModal.tsx`
- Add component if needed: `SearchFilters.tsx`

Fix current mismatch:

```text
current frontend expects row.wilayah?.nama and row.nilai_num
current backend returns row.wilayah_nama and row.nilai
```

### Task 8: Add review UI or admin workflow

**Objective:** Low-confidence mappings and numeric anomalies are reviewable by internal staff.

**Files:**

- Django admin for harmonization models first.
- Later optional internal template page.

### Task 9: Add final integration and QA gate

**Objective:** Prove end-to-end before commit/merge.

Commands:

```bash
cd webapp
. .venv/bin/activate
python manage.py check
python manage.py migrate --check
python manage.py test
python manage.py audit_timeseries_readiness --query "penduduk" --wilayah "Cisayong" --start-year 2020 --end-year 2026
```

Frontend:

```bash
cd bps-pencarian
bun install
bun run build
bun test
```

API smoke:

```bash
curl 'http://127.0.0.1:8000/pencarian/api/v2/timeseries/?q=penduduk&wilayah=Cisayong&start_year=2020&end_year=2026'
```

---

## 6. Hermes/Subagent Execution Strategy After Approval

Use controller + subagents.

### Controller responsibilities

- maintain todo list;
- decide task order;
- verify subagent claims with tools;
- run final tests;
- commit only after verified.

### Subagents

1. **DB Migration Implementer**
   - adds canonical models/migrations/admin.
   - must return exact files changed and migration name.

2. **Normalization Implementer**
   - writes numeric normalization tests and code.
   - must prove RED -> GREEN.

3. **Canonical Query Implementer**
   - writes `get_timeseries` service and tests.
   - must prove Cisayong population expected result.

4. **API Implementer**
   - writes v2 endpoint and serializer.
   - must run API tests.

5. **Frontend Implementer**
   - updates React API + chart rendering.
   - must run build/tests.

6. **Spec Reviewer**
   - checks task matches this plan.
   - writes review only, no code.

7. **Quality Reviewer**
   - checks security/data correctness/N+1/API contract.
   - writes review only, no code.

### Gates

- **Pre-flight gate:** DB backup exists, tests baseline known, `.env` ignored.
- **Schema gate:** migrations apply and rollback safely.
- **Data correctness gate:** Cisayong population query returns normalized 2020-2025 + missing 2026.
- **API gate:** v2 endpoint returns source metadata and warnings.
- **Frontend gate:** build passes and chart uses backend field names correctly.
- **Review gate:** spec reviewer + quality reviewer approve.

---

## 7. Do Not Do Yet

- Do not delete or reshape old `data_fakta` until canonical layer proves itself.
- Do not overwrite `nilai_num` globally before numeric normalization is tested.
- Do not merge all “penduduk” indicators into one; split total/laki/perempuan/persentase/kepadatan/rasio/laju.
- Do not claim 2026 exists for Cisayong population unless data year 2026 appears; publication 2026 currently maps to effective year 2025.
- Do not show unverified values to BPS personnel without raw source and quality flag.
