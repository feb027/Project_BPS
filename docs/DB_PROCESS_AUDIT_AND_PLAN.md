# Audit Awal & Rencana Proses Data Project_BPS

Tanggal audit: 2026-07-05
Repo: `feb027/Project_BPS`
Lokasi VPS: `/home/aqua/Project_BPS`

## 1. Kondisi Awal Repo

Repo berhasil di-clone dari GitHub.

Stack utama:

- Backend internal: Django 5.2 (`webapp/`)
- Frontend pelayanan/personel: React 19 + Vite (`bps-pencarian/`)
- Database default dev: SQLite jika `DB_ENGINE` kosong
- Database target produksi: PostgreSQL via env Django
- PDF extraction: `pdfplumber`, PyMuPDF, pytesseract, optional Gemini Vision
- API pencarian/time-series: Django REST Framework di `webapp/apps/pencarian/api_views.py`

Validasi awal yang sudah dijalankan:

```bash
python3 -m compileall -q webapp
# hasil: python_compile_ok
```

Catatan file/data:

- File Excel tracked: `DATA PUBLIKASI BPS.xlsx`
- PDF publikasi tracked: 2018, 2019, 2020, 2021, 2025, 2026
- Tidak ada `.db` / `.sqlite` / `.csv` tracked
- Ada `webapp/error.html` tracked berisi halaman debug Django. Walau secret tampak dimasking, file seperti ini sebaiknya dihapus dari repo karena menyimpan trace/runtime context.
- `.env.example` punya typo awal baris: `oke# Security Settings`; perlu dibersihkan.

## 2. Schema Saat Ini

Model utama saat ini sudah mengarah ke Tidy/long format:

- `katalog.Publikasi`
- `katalog.Bab`
- `katalog.Tabel`
- `katalog.KolomTabel`
- `referensi.Wilayah`
- `referensi.Indikator`
- `referensi.Rincian`
- `data.Fakta`

Model `Fakta` saat ini:

```text
Fakta = tabel + kolom + wilayah/rincian + tahun + nilai_num/nilai_teks + flag
```

Ini sudah cukup untuk proof-of-concept time series, tapi belum cukup kuat untuk proses sinkronisasi lintas buku karena belum ada:

1. canonical indicator dictionary,
2. alias indikator,
3. unit normalization/multiplier,
4. raw extraction audit table,
5. harmonization confidence,
6. review queue,
7. fact grain uniqueness eksplisit,
8. source/raw cell trace yang detail.

## 3. Proses Sinkronisasi Saat Ini

Ada `webapp/apps/katalog/sync_engine.py` yang melakukan matching antar `KolomTabel` menggunakan:

- preprocessing stopword BPS,
- synonym dictionary,
- Jaro-Winkler similarity,
- unit penalty,
- antonym penalty,
- greedy 1-to-1 matching.

Ini bagus sebagai awal untuk menyamakan kolom antar tabel, tapi masih berada di level `KolomTabel`, bukan canonical dictionary global.

Risiko:

- indikator dengan makna sama tetapi judul berbeda bisa tetap terpecah,
- indikator mirip tetapi makna beda bisa salah match,
- satuan beda belum dinormalisasi ke nilai standar,
- tidak ada review queue formal untuk keputusan matching.

## 4. API React Saat Ini

Endpoint:

- `/pencarian/api/search/?q=...`
- `/pencarian/api/timeseries/?indikator_id=...`
- `/pencarian/api/timeseries/?tabel_id=...`

Search memakai PostgreSQL trigram jika DB vendor PostgreSQL, fallback `icontains` untuk SQLite.

Time-series saat ini mengambil `Fakta` berdasarkan `kolom__indikator_id` atau `tabel_id`, lalu order by `tahun`.

Catatan penting:

- endpoint belum punya filter wilayah/rincian/kategori,
- belum ada grouping/series key yang eksplisit,
- serializer belum mengirim source publication/page/table metadata lengkap,
- belum ada confidence/verified status untuk data hasil sinkronisasi.

## 5. PostgreSQL Status VPS

Update 2026-07-05: PostgreSQL sudah terinstall dan aktif.

```text
psql: /usr/bin/psql
pg_restore: /usr/bin/pg_restore
version: PostgreSQL 17.7
service: active
port 5432: listen 127.0.0.1 only
pg_isready: accepting connections
```

Catatan akses awal:

```text
role aqua awalnya belum ada
peer auth user postgres gagal dari sesi ini
sudo masih butuh password
```

Update: role PostgreSQL `aqua` sudah dibuat dengan `CREATEDB`, sehingga database produksi lokal bisa dibuat dan diakses melalui peer auth/Unix socket dari proses Linux user `aqua`.

## 5.1 Verifikasi Backup Dump

File dump diverifikasi non-destruktif:

```text
path: backups/backup_publikasi_bps_20260705_1439.dump
format: PostgreSQL custom database dump
size: 4.8 MB
sha256: 98fb1ca4ed11a536259cd5543ae8c027fc7798dfababf48efc0a76c2b6271034
archive created: 2026-07-05 14:39:17 UTC
dbname asal: publikasi_bps
dumped from PostgreSQL: 18.4
pg_dump version: 18.4
TOC entries: 183
extension: pg_trgm
DROP statements in schema-only output: none
```

Restore test dilakukan ke PostgreSQL private sementara di `/tmp`, bukan ke server produksi, dengan `pg_restore --no-owner --no-acl`.

Hasil restore test:

```text
data_fakta: 162114
katalog_publikasi: 9
katalog_bab: 107
katalog_tabel: 776
katalog_kolomtabel: 4913
referensi_indikator: 1395
referensi_rincian: 2185
referensi_wilayah: 86
```

Quick quality:

```text
total_fakta: 162114
numeric_fakta: 104847
non_numeric_or_null: 57267
tahun_unik: 16
range tahun: 2010-2026
facts with wilayah: 162114
facts with rincian: 19893
```

Dump juga berisi tabel bawaan Django:

```text
auth_user: 1 user admin, password algorithm pbkdf2_sha256
django_session: 10 rows
```

Kesimpulan: dump valid dan bisa dipakai sebagai sumber data, tetapi jangan dibagikan publik karena mengandung akun admin hash dan session rows. Untuk restore produksi, gunakan database kosong atau restore dengan opsi clean/drop yang disengaja setelah backup lama dibuat.

## 5.2 Restore Produksi Lokal VPS

Restore produksi lokal sudah dilakukan ke database server PostgreSQL utama:

```text
database: bps_publikasi
owner/connection role: aqua
restore command: pg_restore --no-owner --no-acl -d bps_publikasi backups/backup_publikasi_bps_20260705_1439.dump
restore result: OK
```

`webapp/.env` lokal VPS dibuat dan di-ignore Git:

```text
DB_ENGINE=django.db.backends.postgresql
DB_NAME=bps_publikasi
DB_USER=aqua
DB_HOST=          # kosong: Unix socket/peer auth
DB_PORT=5432
```

Backend dependencies sudah dipasang di `webapp/.venv`. Validasi Django:

```bash
python manage.py check
python manage.py migrate --check
```

Hasil:

```text
System check identified no issues
migrate --check: OK
pg_trgm extension: available
API smoke /pencarian/api/search/?q=penduduk: HTTP 200, tabel=10, indikator=15
```

Counts via Django ORM:

```text
fakta: 162114
publikasi: 9
tabel: 776
kolom: 4913
indikator: 1395
wilayah: 86
rincian: 2185
```

## 6. Rekomendasi Schema V2

Tambahkan layer berikut tanpa menghapus model lama langsung.

### Raw/audit layer

```text
raw_publication_files
raw_extracted_tables
raw_extracted_rows / raw_extracted_cells optional
```

Tujuan: menyimpan bukti hasil PDF extraction dan sumber halaman.

### Canonical dictionary

```text
canonical_indicators
indicator_aliases
canonical_units
unit_aliases
```

Tujuan: menyamakan indikator lintas publikasi.

### Harmonized fact layer

Bisa berupa pengembangan `Fakta` atau tabel baru `fact_observations`.

Kolom penting:

```text
publication_id
raw_table_id
source_page
raw_indicator_name
canonical_indicator_id
raw_region_name
region_id
raw_period
period_id/year
raw_unit
unit_id
value_raw
value_numeric
value_standardized
category_json
confidence_score
harmonization_status
```

Status minimal:

```text
mapped
needs_review
rejected
verified
```

### Review queue

```text
harmonization_reviews
```

Untuk approval/correction mapping indikator, wilayah, periode, dan satuan.

## 7. Rencana Implementasi Bertahap

### Fase 1 — DB produksi PostgreSQL

Setelah sudo tersedia:

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

Buat DB dan user:

```bash
sudo -u postgres psql
CREATE DATABASE bps_publikasi;
CREATE USER bps_app WITH PASSWORD '<password-kuat>';
GRANT ALL PRIVILEGES ON DATABASE bps_publikasi TO bps_app;
```

Aktifkan extension:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

### Fase 2 — migrasi Django ke PostgreSQL

Isi `webapp/.env` lokal VPS:

```env
DB_ENGINE=django.db.backends.postgresql
DB_NAME=bps_publikasi
DB_USER=bps_app
DB_PASSWORD=<password-kuat>
DB_HOST=127.0.0.1
DB_PORT=5432
```

Lalu:

```bash
cd webapp
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py check
```

### Fase 3 — audit data existing

Hitung:

```text
jumlah publikasi
jumlah tabel
jumlah kolom tabel
jumlah fakta
jumlah indikator unik
jumlah wilayah unik
jumlah rincian unik
jumlah tahun unik
jumlah fakta numeric vs teks
```

### Fase 4 — canonical indicator dictionary

Bangun tabel canonical dari indikator paling sering dulu:

```sql
SELECT nama, satuan, count(*)
FROM referensi_indikator i
JOIN katalog_kolomtabel k ON k.indikator_id = i.id
JOIN data_fakta f ON f.kolom_id = k.id
GROUP BY nama, satuan
ORDER BY count(*) DESC;
```

### Fase 5 — harmonization engine

Ubah matching saat ini menjadi pipeline formal:

1. exact alias match,
2. normalized text match,
3. trigram/Jaro-Winkler match,
4. unit compatibility check,
5. semantic/fuzzy optional,
6. confidence scoring,
7. review queue untuk confidence rendah.

### Fase 6 — React time-series API v2

Endpoint yang dibutuhkan:

```text
GET /api/search?q=...
GET /api/indicators/:id/timeseries?region_id=...&category=...
GET /api/indicators/:id/metadata
GET /api/reviews/pending
```

Output time series harus punya:

```text
series_key
indicator
region
category
unit
points: [{year, value, source_publication, source_page, confidence}]
```

## 8. Prioritas Perbaikan Terdekat

1. Install PostgreSQL setelah akses sudo tersedia.
2. Hapus `webapp/error.html` dari repo.
3. Bersihkan typo `.env.example`.
4. Tambahkan migration untuk PostgreSQL extensions (`pg_trgm`, `unaccent`).
5. Tambahkan audit command untuk menghitung state data existing.
6. Tambahkan canonical dictionary + alias model.
7. Tambahkan review queue untuk sinkronisasi indikator.
8. Upgrade API time-series supaya bisa filter wilayah/rincian/kategori dan menampilkan source metadata.
