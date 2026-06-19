# Pangkalan Data Publikasi — BPS Tasikmalaya

Aplikasi internal (Django) untuk mengelola data publikasi BPS: ekstraksi dari PDF,
input/edit, dan pencarian. Dipakai tim (±8 orang) di LAN, dari satu laptop host.

## Struktur (modular)

```
webapp/
  config/            setelan proyek (settings dev/prod terpisah), urls, wsgi
  apps/
    core/            basis + beranda/dashboard
    referensi/       master: Wilayah, Indikator, Rincian
    katalog/         Publikasi -> Bab -> Tabel -> KolomTabel (header tabel)
    data/            Fakta (inti, format long)
    ekstraksi/       engine ekstraksi PDF + halaman ekstraksi (F2)
    pencarian/       pencarian data (F4)
  templates/         tampilan (base + per halaman)
  static/css/        desain (instrumen data: ink/teal + amber, angka tabular)
```

## Menjalankan (pengembangan)

```cmd
py manage.py migrate
py manage.py runserver 127.0.0.1:8000
```

Buka http://127.0.0.1:8000/ . Panel admin: http://127.0.0.1:8000/admin/
(akun awal: `admin` / `bps2026` — ganti setelah dipakai).

## Dipakai bersama di LAN

Di laptop host:
```cmd
py manage.py runserver 0.0.0.0:8000
```
Tim lain buka `http://<ip-laptop-host>:8000/`. Pastikan firewall mengizinkan port 8000.

## Database

Default SQLite (pengembangan). Untuk PostgreSQL (produksi/tim), salin `.env.example`
ke `.env`, isi `DB_ENGINE=django.db.backends.postgresql` + kredensial, lalu `migrate`.
