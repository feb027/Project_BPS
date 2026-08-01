<div align="center">
  <img src="bps-pencarian/public/favicon.svg" alt="Project BPS" width="84" height="84" />

  # Project BPS

  **Sistem ekstraksi, harmonisasi, dan pencarian time-series publikasi BPS Kabupaten Tasikmalaya — Django + React.**

  [![Django](https://img.shields.io/badge/Django-5.2-0C4B33?style=flat-square&logo=django&logoColor=white)](webapp/)
  [![DRF](https://img.shields.io/badge/DRF-3.14-802808?style=flat-square&logo=django&logoColor=white)](webapp/)
  [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-4169E1?style=flat-square&logo=postgresql&logoColor=white)](webapp/)
  [![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=111827)](bps-pencarian/)
  [![Vite](https://img.shields.io/badge/Vite-8-646CFF?style=flat-square&logo=vite&logoColor=white)](bps-pencarian/)
  [![Bun](https://img.shields.io/badge/Bun-package--manager-000000?style=flat-square&logo=bun&logoColor=white)](bps-pencarian/package.json)
  [![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)](bps-pencarian/)
  [![Tailwind](https://img.shields.io/badge/Tailwind-v4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](bps-pencarian/)

  [Buka pencarian publik](https://bps-pencarian.aquarise.my.id/) · [Backend hub (Basic Auth)](https://bps-hub.aquarise.my.id/) · [Runbook migrasi](docs/harmonization-migration-runbook.md)
</div>

> [!NOTE]
> Monorepo **decoupled**: `webapp/` adalah mesin ekstraksi & kurasi data (Django), `bps-pencarian/` adalah antarmuka pencarian time-series (React/Vite). Keduanya berbagi satu basis data PostgreSQL.

---

## Ringkasan

Project BPS mengubah tabel publikasi **Kabupaten Dalam Angka (KDA)** — yang biasanya berupa blok tabel bertingkat di dalam PDF — menjadi basis data **long/tidy** sehingga setiap angka dapat dicari sebagai deret waktu (*time-series*). Pengguna mengetik pertanyaan natural seperti `jumlah penduduk cisayong`, lalu aplikasi menampilkan jawaban langsung: grafik lintas tahun, tabel nilai, dan ekspor Excel/PDF — tanpa harus memahami struktur tabel mentah BPS.

| Area | Status |
| --- | --- |
| Publikasi terindeks | 9 tahun terbit (2018–2026) |
| Tabel katalog | ±842 tabel (110 nomor tabel lintas tahun) |
| Fakta long/tidy | ±174.745 baris (nilai numerik + teks asli) |
| Wilayah | 39 kecamatan + kabupaten (dibersihkan dari 113 entri kotor) |
| Indikator mentah | ±1.466 |
| Indikator canonical | 325 indikator, 395 alias harmonisasi |
| Rentang tahun data | 2010–2026 |
| Pencarian publik | `https://bps-pencarian.aquarise.my.id/` |
| Internal hub | `https://bps-hub.aquarise.my.id/` (Basic Auth) |

## Fitur utama

### Pencarian & visualisasi (frontend publik)

- **Pencarian bahasa natural** — query gabungan indikator + wilayah, misal `jumlah penduduk cisayong laki laki`; deteksi wilayah otomatis (kabupaten > kecamatan, nama terpanjang menang).
- **Jawaban cepat** — satu kartu time-series langsung (bukan daftar kandidat mentah), lengkap dengan deteksi usia (`penduduk umur 15 tahun`), level sekolah (`guru sma`), dan agregasi kabupaten yang tidak menggandakan total.
- **Multi-konsep & perbandingan tabel** — query `murid sma + guru sma` (atau `murid sma dan guru sma`) otomatis membuka perbandingan 2+ tabel; setiap konsep dipetakan ke metrik yang tepat (mis. `Jumlah Murid (SMA)` → metrik `Murid Jumlah`).
- **Slider rentang tahun** — filter grafik dan tabel ekspor ke rentang tahun pilihan (dual-thumb), tersedia di chart tunggal dan modal perbandingan; pilihan tersimpan di `localStorage`.
- **Jelajahi publikasi** — panel katalog yang menggabungkan tabel lintas tahun per nomor tabel, dengan filter **Jenis Data** (Per Kecamatan / Per Kabupaten / Per Kategori) dan keranjang bandingkan (maks. 6 tabel).
- **Ekspor profesional** — Excel & PDF (branding BPS, tabel pivot tahun × wilayah/rincian, gambar grafik) untuk chart tunggal maupun perbandingan.

### Ekstraksi & kurasi (backend internal)

- **Engine ekstraksi PDF** (`apps/ekstraksi`) — segmentasi otomatis halaman → banyak tabel, deteksi nomor/judul/sumber, tipe baris otomatis (kecamatan vs kategori), pembersihan watermark, fallback OCR (Tesseract) dan Gemini Vision untuk PDF kompleks.
- **Gudang data tidy** — setiap angka = satu baris `Fakta` dengan tautan tabel, kolom, wilayah/rincian, tahun, nilai numerik, dan `nilai_teks` asli (audit-friendly).
- **Harmonisasi lintas tahun** — `CanonicalIndicator` + `IndicatorAlias` + alias berbasis konteks judul tabel; unit kanonik (`UnitAlias`) untuk menyatukan satuan yang berbeda antar edisi.
- **Import manual via Excel** (`apps/manual_import`) — unduh template per-BAB/per-tabel (dengan format visual profesional), isi manual, upload → validasi ketat → pratinjau → commit idempoten ke publikasi tahun target. Mendukung baris per kecamatan, per kabupaten, dan per kategori (rincian).
- **Hub internal Django** — dashboard, kurasi tabel, sinkronisasi kolom antar publikasi, verifikasi fakta, dan audit kualitas.

## Arsitektur

### Monorepo decoupled

```mermaid
flowchart LR
    subgraph Backend["webapp/ — Django 5.2 (mesin data)"]
        EK[apps.ekstraksi<br/>PDF → tabel]
        MI[apps.manual_import<br/>Excel template → commit]
        KA[apps.katalog<br/>Publikasi/Bab/Tabel]
        RE[apps.referensi<br/>Indikator/Wilayah/Rincian]
        DA[apps.data<br/>Fakta & time-series]
        PE[apps.pencarian<br/>API search/catalog]
    end

    subgraph Frontend["bps-pencarian/ — React 19 + Vite (SPA)"]
        SPA[Komponen modular<br/>Sidebar · Catalog · ChartModal · CompareModal]
    end

    PDF[(PDF publikasi)] --> EK
    XLS[(Excel isian manual)] --> MI
    EK --> KA --> DA
    MI --> KA --> DA
    RE --> DA
    DA --> PE
    PE -->|"/pencarian/api/*"| SPA
    SPA -->|"REST JSON"| PE
    DA --> PG[(PostgreSQL<br/>bps_publikasi)]
```

### Alur data end-to-end

```mermaid
flowchart TD
    A[Publikasi PDF 2018–2026] -->|ekstraksi / OCR / Gemini| B[Preview tabel terdeteksi]
    B -->|simpan (ingest_long_rows)| C[(Tabel + Kolom + Fakta)]
    X[Template Excel manual] -->|upload + validasi| Y[Preview]
    Y -->|commit idempoten| C
    C -->|harmonisasi alias| D[CanonicalIndicator + UnitAlias]
    D --> E[API pencarian trigram + deteksi wilayah]
    E --> F[Kartu jawaban · grafik time-series · perbandingan]
    F --> G[Ekspor Excel / PDF]
```

### Model data inti

```mermaid
erDiagram
    PUBLIKASI ||--o{ BAB : memiliki
    BAB ||--o{ TABEL : memiliki
    TABEL ||--o{ KOLOMTABEL : memiliki
    TABEL ||--o{ FAKTA : berisi
    KOLOMTABEL }o--|| INDIKATOR : merujuk
    INDIKATOR ||--o{ RINCIANALIAS : "disatukan oleh"
    RINCIANALIAS }o--|| CANONICALINDICATOR : "mengarah ke"
    TABEL ||--o{ FAKTA : ""
    FAKTA }o--o| WILAYAH : "baris kecamatan"
    FAKTA }o--o| RINCIAN : "baris kategori"
    PUBLIKASI {
        int tahun_terbit
        string judul
        string jenis
    }
    BAB {
        int nomor
        string nama
    }
    TABEL {
        string nomor_tabel "mis. 1.1.1"
        string judul
        string tipe_baris "kecamatan/kabupaten/kategori"
    }
    KOLOMTABEL {
        int urutan
        string satuan
        int tahun
    }
    FAKTA {
        decimal nilai_num
        string nilai_teks
        int tahun
        string flag "ada/nihil/tidak_tersedia"
    }
```

## Struktur repositori

```text
Project_BPS/
├── webapp/                     # Backend Django (mesin data)
│   ├── apps/
│   │   ├── core/               # Dashboard & utilitas bersama
│   │   ├── katalog/            # Publikasi, Bab, Tabel, KolomTabel
│   │   ├── referensi/          # Indikator, Wilayah, Rincian, alias
│   │   ├── data/               # Fakta, time-series, ekspor, ingest
│   │   ├── pencarian/          # API search/timeseries/catalog
│   │   ├── ekstraksi/          # Engine ekstraksi PDF (+ OCR/Gemini)
│   │   └── manual_import/      # Template Excel → upload → commit
│   ├── config/
│   │   ├── settings/           # base / dev / prod
│   │   └── urls.py             # /admin /data /kelola /pencarian /ekstraksi /importer
│   ├── templates/              # Template Django (hub internal)
│   ├── staticfiles/            # collectstatic (production)
│   └── requirements.txt
├── bps-pencarian/              # Frontend React SPA (pencarian publik)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/             # Atomik (button, input, select, card)
│   │   │   ├── layout/         # Sidebar, MainArea, SplitPaneLayout
│   │   │   └── features/       # CatalogBrowser, ChartModal, CompareModal,
│   │   │                       #   YearRangeSlider, InlineTimeSeriesAnswer
│   │   └── lib/                # api (SWR), utils, pdfExport
│   ├── public/                 # favicon, aset statis
│   └── package.json            # Bun + Vite + TypeScript + Tailwind v4
├── docs/                       # Runbook, audit DB, rencana
└── scripts/                    # Backup Windows (PowerShell + rclone)
```

## API (public)

Prefix: `https://bps-pencarian.aquarise.my.id/pencarian/api/`

| Endpoint | Keterangan |
| --- | --- |
| `GET /search/?q=...` | Pencarian natural-language; balikan tabel, indikator, wilayah terdeteksi, `quick_matches`, dan `multi_concepts` (query `+`/`dan`) |
| `GET /catalog/` | Katalog tabel di-merge lintas publikasi per nomor tabel |
| `GET /catalog/?nomor_tabel=1.1.1` | Seri time-series gabungan satu nomor tabel |
| `GET /timeseries/?tabel_id=...\|indikator_id=...` | Fakta time-series per tabel/indikator |
| `GET /canonical-timeseries/?indicator_code=...` | Seri ter-harmonisasi via canonical indicator (+ `wilayah_id`, `start_year`, `end_year`) |

Endpoint manual import (hub internal, tanpa auth): `POST /importer/generate-template/`, `POST /importer/upload/`, `POST /importer/commit/<uuid>/`.

## Cara menjalankan

> [!TIP]
> Untuk pengembangan cepat, backend bisa pakai **SQLite** bawaan (tanpa `DB_ENGINE`). Untuk fitur penuh (trigram, cache bersama), gunakan **PostgreSQL** 14+.

### Prasyarat

- Python **3.11+** (rekomendasi 3.12/3.13)
- Node.js **20+** dan [Bun](https://bun.sh) 1.x
- PostgreSQL **14+** *(opsional untuk dev; wajib untuk production)*
- Tesseract OCR *(opsional, untuk PDF hasil scan)*
- Kunci API Google Gemini *(opsional, untuk ekstraksi tabel kompleks)*

### 1. Backend (Django)

```bash
cd webapp
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
python manage.py migrate

# Pengembangan (SQLite)
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver 0.0.0.0:8000
```

Aktifkan PostgreSQL (bila dipakai):

```bash
# Linux/macOS
export DB_ENGINE=django.db.backends.postgresql
export DB_NAME=bps_publikasi DB_USER=bps DB_PASSWORD=... DB_HOST=127.0.0.1 DB_PORT=5432

# Windows (PowerShell)
# $env:DB_ENGINE = "django.db.backends.postgresql"
# $env:DB_NAME  = "bps_publikasi"

DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py migrate
```

### 2. Frontend (React/Vite)

```bash
cd bps-pencarian
bun install
bun run dev        # http://localhost:5173 — proxy /pencarian/api/* diatur Caddy/Vite
```

> [!WARNING]
> `bun test` dapat crash di CPU lama tanpa dukungan AVX (segfault Bun). Gunakan `npx vitest run` sebagai pengganti.

### 3. (Opsional) OCR & Gemini Vision

- **Tesseract**: pasang sesuai OS — Linux: `apt install tesseract-ocr`, macOS: `brew install tesseract`, Windows: [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki).
- **Gemini**: set `GEMINI_API_KEY` (variabel lingkungan) agar engine ekstraksi memakai AI untuk tabel PDF kompleks.

## Pengujian

```bash
# Backend (pytest + pytest-django)
cd webapp
source .venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.dev python -m pytest apps/pencarian/tests.py apps/manual_import/tests.py --create-db

# Frontend (Vitest — bukan bun test, lihat warning di atas)
cd bps-pencarian
npx vitest run

# Lint frontend
bun run lint

# Build produksi
bun run build
```

> [!NOTE]
> `config/settings/dev.py` memakai **DummyCache** agar cache `@cache_page` tidak bocor antar test (flake urutan test dihindari). Production tetap memakai `DatabaseCache`.

## Deployment (production)

Topologi saat ini: **Cloudflare → Caddy → (static SPA | gunicorn)**.

```mermaid
flowchart TD
    U[Pengguna] --> CF[Cloudflare]
    CF --> C[ Caddy ]
    C -->|bps-pencarian.aquarise.my.id| SPA[Vite build<br/>bps-pencarian/dist]
    C -->|/pencarian/api/*| G[Gunicorn<br/>127.0.0.1:8020]
    C -->|bps-hub.aquarise.my.id + Basic Auth| G
    G --> D[Django config.settings.prod]
    D --> PG[(PostgreSQL bps_publikasi)]
```

- Backend dijalankan **user systemd unit** `project-bps-backend.service` (gunicorn, `Restart=always`).
- SPA di-serve langsung dari `dist/` oleh Caddy (tanpa proses tambahan); rebuild cukup `bun run build`.
- `bps-hub` dilindungi Basic Auth di tingkat Caddy; `bps-pencarian` publik.

```bash
# Deploy backend
systemctl --user restart project-bps-backend
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8020/importer/   # → 200

# Deploy frontend
cd bps-pencarian && bun run build

# Koleksi static Django (setelah ubah template/static)
cd webapp && . .venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py collectstatic --noinput

# Caddy (bila konfigurasi berubah)
caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

> [!IMPORTANT]
> Hanya ada **satu** unit yang boleh melayani port 8020: `project-bps-backend.service` (user). Bila ada unit lain (mis. `bps-webapp.service`) dalam keadaan `active` dan merebut port, matikan dulu (`systemctl stop bps-webapp`) agar deploy benar-benar tersaji. Verifikasi selalu dengan memeriksa **key response baru**, bukan sekadar HTTP 200 (kode lama tetap balasan 200).

## Backup & restore

- Backup database production: `pg_dump` (lihat `scripts/backup_db.ps1` untuk otomasi Windows + rclone ke penyimpanan eksternal).
- Selalu `pg_dump` sebelum operasi destruktif; verifikasi dump di database uji sebelum restore.
- File data mentah (PDF publikasi, Excel isian, dump SQL) **tidak** di-track di repositori — disimpan lokal/backup terpisah.

## Troubleshooting singkat

| Gejala | Penyebab umum & solusi |
| --- | --- |
| Deploy backend "tidak ngefek" (key API lama) | Unit lain merebut port 8020. Periksa `ss -tlnp | grep 8020`, cek `cat /proc/<pid>/cgroup`; stop unit pengganggu, restart `project-bps-backend`. |
| Search trigram error di PostgreSQL | Pastikan ekstensi `pg_trgm` aktif (`CREATE EXTENSION IF NOT EXISTS pg_trgm;`). |
| `bun test` segfault | CPU tanpa AVX — pakai `npx vitest run`. |
| Template Excel gagal dibuat | Nama sheet mengandung karakter ilegal (`/`, `[`, `]`) — kode sudah menormalisasi; pastikan tabel judul tidak melebihi 31 karakter setelah sanitasi. |
| Commit import dobel | Sejak Agustus 2026 commit idempoten via `update_or_create`; pastikan versi backend terbaru. |

## Dokumentasi teknis

- [Runbook harmonisasi migrasi](docs/harmonization-migration-runbook.md)
- [Audit & rencana proses DB](docs/DB_PROCESS_AUDIT_AND_PLAN.md)
- [Rencana database time-series](docs/plans/2026-07-05-timeseries-database-agent-plan.md)

## Prinsip desain

- **Jawaban dulu, kandidat belakangan** — query `penduduk cisayong` langsung menjadi grafik wilayah, bukan daftar mentah panjang.
- **Data audit-friendly** — `nilai_teks` asli selalu tersimpan bersama nilai numerik ternormalisasi.
- **Alias kontekstual** — label generik (`Jumlah`, `Laki-laki`, `Perempuan`) dipetakan dengan konteks judul tabel agar tidak salah topik lintas tahun.
- **Frontend modular** — layout, fitur, dan UI atomik dipisahkan agar mudah dikembangkan dan diuji.
- **UI enterprise BPS** — datar, bersih, palet biru muda/oranye/hijau identitas BPS; tanpa efek glassmorphism/neon.
