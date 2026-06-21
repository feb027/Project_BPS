"""
Ekstraksi tabel PDF via Gemini Flash Vision AI.

Alur:
1. Render setiap halaman PDF → gambar (via PyMuPDF).
2. Kirim gambar ke Gemini Flash API dengan prompt terstruktur.
3. Parse respons JSON → gabung halaman lanjutan → output format
   sama persis dengan engine._rakit_tabel() supaya preview/simpan
   tetap kompatibel.

Dependency:
- google-genai >= 1.0  (SDK baru Google untuk Gemini API)
- PyMuPDF (fitz)       (sudah ada utk OCR)
- Pillow               (sudah ada utk OCR)
"""
from __future__ import annotations

import io
import json
import logging
import re
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────── #
#  Ketersediaan
# ──────────────────────────────────────────────────────────────────────── #
try:
    from google import genai
    _ADA_GENAI = True
except ImportError:
    _ADA_GENAI = False

try:
    import fitz  # PyMuPDF
    _ADA_FITZ = True
except ImportError:
    _ADA_FITZ = False

try:
    from PIL import Image
    _ADA_PIL = True
except ImportError:
    _ADA_PIL = False


PESAN_INSTALL = (
    "Gemini Vision membutuhkan: (1) paket Python 'google-genai' "
    "(`pip install google-genai`), (2) PyMuPDF (`pip install PyMuPDF`), "
    "dan (3) API key Gemini di file .env (GEMINI_API_KEY=...). "
    "Dapatkan API key gratis di https://aistudio.google.com/apikey"
)


def gemini_tersedia() -> bool:
    """True bila semua komponen Gemini Vision siap pakai."""
    return (
        _ADA_GENAI
        and _ADA_FITZ
        and _ADA_PIL
        and bool(getattr(settings, "GEMINI_API_KEY", ""))
    )


def _alasan_tidak_tersedia() -> str:
    """Pesan diagnostik bila gemini_tersedia() False."""
    alasan = []
    if not _ADA_GENAI:
        alasan.append("paket 'google-genai' belum terinstall")
    if not _ADA_FITZ:
        alasan.append("paket 'PyMuPDF' belum terinstall")
    if not _ADA_PIL:
        alasan.append("paket 'Pillow' belum terinstall")
    if not getattr(settings, "GEMINI_API_KEY", ""):
        alasan.append("GEMINI_API_KEY belum diisi di .env")
    return "; ".join(alasan) if alasan else "OK"


# ──────────────────────────────────────────────────────────────────────── #
#  Render halaman PDF → gambar PIL
# ──────────────────────────────────────────────────────────────────────── #
def _render_halaman(pdf_path: str, pno: int, dpi: int = 200) -> "Image.Image":
    """Render satu halaman PDF → PIL Image (RGB)."""
    doc = fitz.open(pdf_path)
    page = doc[pno - 1]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    doc.close()
    return img.convert("RGB")


# ──────────────────────────────────────────────────────────────────────── #
#  Prompt untuk Gemini
# ──────────────────────────────────────────────────────────────────────── #
_PROMPT = """\
Kamu adalah asisten ekstraksi data tabel statistik BPS (Badan Pusat Statistik) Indonesia.

Dari gambar halaman PDF ini, ekstrak SEMUA informasi tabel yang terlihat.

Kembalikan HANYA JSON valid (tanpa markdown fence, tanpa penjelasan) dengan format:
{
  "nomor_tabel": "string, contoh: 4.1.1",
  "lanjutan": false,
  "judul_id": "judul tabel dalam Bahasa Indonesia",
  "judul_en": "judul tabel dalam Bahasa Inggris (jika ada, biasanya italic)",
  "sumber": "sumber data (jika tertulis, contoh: BPS Kab. Tasikmalaya)",
  "bab": "nama bab di header atas halaman (jika ada)",
  "headers": [
    {"nama": "nama kolom dalam Bahasa Indonesia", "satuan": "satuan jika ada dalam kurung", "tahun": "tahun jika header berupa tahun"}
  ],
  "label_kolom": "label untuk kolom pertama (baris), misal: KECAMATAN, Kelompok Umur, dll",
  "rows": [
    {"label": "nama baris (kecamatan/kategori)", "values": ["nilai1", "nilai2", ...]}
  ],
  "total_row": {"label": "nama baris total", "values": ["nilai1", ...]} atau null jika tidak ada baris total
}

ATURAN PENTING:
1. "headers" TIDAK termasuk kolom pertama (label baris). Hanya kolom data.
2. Jumlah elemen di "values" HARUS sama dengan jumlah elemen di "headers".
3. Untuk angka desimal gaya Indonesia, tulis apa adanya (misal "1.946.197" atau "2,53").
4. Untuk sel kosong atau tanda "-", tulis "-".
5. Untuk sel "..." atau "..", tulis "...".
6. Jika halaman bertuliskan "Lanjutan" atau "Continued", set "lanjutan": true, dan isi "nomor_tabel" dari teks "Lanjutan Tabel X.X.X".
7. Untuk halaman lanjutan, "judul_id", "judul_en", "sumber" boleh kosong "".
8. Jika header tabel memiliki sub-header atau multi-level (merged cells), gabungkan menjadi nama kolom yang deskriptif. Contoh: jika ada header utama "Jenis Kelamin" dengan sub-header "Laki-Laki" dan "Perempuan", maka headers = [{"nama": "Laki-Laki", ...}, {"nama": "Perempuan", ...}].
9. Baris yang berisi total Kabupaten (biasanya "Kabupaten Tasikmalaya") masukkan ke "total_row", BUKAN ke "rows".
10. Jangan sertakan baris nomor kolom seperti "(1) (2) (3)..." — itu bukan data.
11. ABAIKAN warna latar belakang sel (seperti tabel berwarna kuning, oranye, atau abu-abu). Fokus HANYA pada struktur teks dan garis tabel (baik yang terlihat eksplisit maupun implisit). Warna atau shading sama sekali tidak merubah struktur atau makna data.
12. Sangat berhati-hati dengan "merged cells" (sel yang digabung). Pastikan untuk memisahkan batas kolom dan baris dengan akurat tanpa terpengaruh oleh warna-warni tabel.
13. TRANSKRIPSI 100% AKURAT: Jangan pernah merangkum (summarize) atau melewatkan baris data. SELURUH baris data dari awal hingga akhir tabel HARUS diekstrak tanpa terkecuali.
14. ALIGNMENT KOLOM: Pastikan setiap baris (rows) benar-benar memiliki jumlah elemen `values` yang *tepat sama* dengan jumlah `headers`. Jika sebuah sel kosong, isi dengan "-". Jangan sampai ada nilai yang bergeser ke kolom yang salah.
15. FORMAT ANGKA BPS: Salin angka persis seperti yang tertulis. Pemisah ribuan biasanya titik (.) dan desimal koma (,) contoh: "1.234,56".
16. MULTI-BARIS: Jika nama baris (label wilayah/kategori) terpotong menjadi 2 baris teks, gabungkan menjadi satu kalimat menggunakan spasi.
17. STRUKTUR TEKS: Abaikan tipografi visual (seperti teks tebal, miring, atau font yang berbeda), ambil nilai datanya saja.
"""


# ──────────────────────────────────────────────────────────────────────── #
#  Panggil Gemini API (dengan retry)
# ──────────────────────────────────────────────────────────────────────── #
def _panggil_gemini(img: "Image.Image", max_retry: int = 3) -> dict:
    """Kirim gambar ke Gemini → parse JSON respons."""
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")

    client = genai.Client(api_key=api_key)

    last_err = None
    for attempt in range(max_retry):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[_PROMPT, img],
            )
            teks = (response.text or "").strip()
            # Bersihkan markdown fence jika ada
            teks = re.sub(r"^```(?:json)?\s*", "", teks)
            teks = re.sub(r"\s*```$", "", teks)
            teks = teks.strip()

            if not teks:
                raise ValueError("Respons Gemini kosong")

            data = json.loads(teks)
            return data

        except json.JSONDecodeError as e:
            logger.warning("Gemini JSON parse error (attempt %d): %s\nResponse: %s",
                           attempt + 1, e, teks[:500])
            last_err = e
        except Exception as e:
            err_str = str(e).lower()
            logger.warning("Gemini API error (attempt %d): %s", attempt + 1, e)
            last_err = e
            # Rate limit → tunggu lebih lama
            if "429" in err_str or "rate" in err_str or "quota" in err_str:
                wait = (attempt + 1) * 10
                logger.info("Rate limited, waiting %ds...", wait)
                time.sleep(wait)
                continue

        # Retry delay normal
        if attempt < max_retry - 1:
            time.sleep(2 * (attempt + 1))

    raise RuntimeError(f"Gemini gagal setelah {max_retry} percobaan: {last_err}")


# ──────────────────────────────────────────────────────────────────────── #
#  Konversi output Gemini → format engine
# ──────────────────────────────────────────────────────────────────────── #
def _clean_num_gemini(raw: str):
    """Sama dengan engine.clean_num tapi diulang di sini agar modular."""
    raw = (raw or "").strip()
    if "..." in raw or raw in ("..", "…"):
        return None, raw, "tidak_tersedia"
    neg = raw.startswith("(") and raw.endswith(")")
    keep = re.sub(r"[^0-9,.\-–—]", "", raw)
    if not re.search(r"\d", keep):
        if re.search(r"[-–—]", keep):
            return None, raw, "nihil"
        return None, raw, "tidak_tersedia"
    num = re.sub(r"[-–—]", "", keep).replace(".", "").replace(",", ".")
    try:
        val = float(num)
    except ValueError:
        return None, raw, "perlu_cek"
    if neg:
        val = -val
    return (str(int(val)) if val.is_integer() else str(val)), raw, "ada"


def _buat_sel_gemini(values: list) -> list:
    """Konversi list string values → list sel {teks, num, flag}."""
    out = []
    for raw in values:
        num, teks, flag = _clean_num_gemini(raw)
        out.append({"teks": teks, "num": num, "flag": flag})
    return out


def _gemini_ke_tabel(data: dict) -> dict:
    """Konversi satu respons Gemini → format tabel engine."""
    headers_raw = data.get("headers", [])
    rows_raw = data.get("rows", [])
    total_raw = data.get("total_row")

    n_kolom = len(headers_raw)

    headers = []
    for h in headers_raw:
        headers.append({
            "nama": h.get("nama", ""),
            "satuan": h.get("satuan", ""),
            "tahun": h.get("tahun", ""),
            "tipe": "num",
        })

    rows = []
    for r in rows_raw:
        label = r.get("label", "")
        vals = r.get("values", [])
        # Pastikan panjang values = n_kolom
        while len(vals) < n_kolom:
            vals.append("")
        vals = vals[:n_kolom]
        rows.append({"wilayah": label, "sel": _buat_sel_gemini(vals)})

    total = None
    if total_raw and total_raw.get("values"):
        tvals = total_raw.get("values", [])
        while len(tvals) < n_kolom:
            tvals.append("")
        tvals = tvals[:n_kolom]
        total = {
            "wilayah": total_raw.get("label", "Kabupaten Tasikmalaya"),
            "sel": _buat_sel_gemini(tvals),
        }

    return {
        "nomor": data.get("nomor_tabel", ""),
        "judul_id": data.get("judul_id", ""),
        "judul_en": data.get("judul_en", ""),
        "bab": data.get("bab", ""),
        "sumber": data.get("sumber", ""),
        "mode": "kategori",  # AI tidak perlu bedakan; pemanggil bisa override
        "ocr": False,
        "gemini": True,
        "n_kolom": n_kolom,
        "headers": headers,
        "label_kolom": data.get("label_kolom", ""),
        "rows": rows,
        "total": total,
    }


# ──────────────────────────────────────────────────────────────────────── #
#  Deteksi mode kecamatan
# ──────────────────────────────────────────────────────────────────────── #
_KECAMATAN_SET = {
    "cipatujah", "karangnunggal", "cikalong", "pancatengah", "cikatomas",
    "cibalong", "parungponteng", "bantarkalong", "bojongasih", "culamega",
    "bojonggambir", "sodonghilir", "taraju", "salawu", "puspahiang",
    "tanjungjaya", "sukaraja", "salopa", "jatiwaras", "cineam",
    "karangjaya", "manonjaya", "gunungtanjung", "singaparna", "sukarame",
    "mangunreja", "cigalontang", "leuwisari", "sariwangi", "padakembang",
    "sukaratu", "cisayong", "sukahening", "rajapolah", "jamanis",
    "ciawi", "kadipaten", "pagerageung", "sukaresik",
}


def _deteksi_mode(rows: list) -> str:
    """Tebak mode dari label baris: jika banyak cocok nama kecamatan → 'kecamatan'."""
    if not rows:
        return "kategori"
    cocok = sum(
        1 for r in rows
        if re.sub(r"[^a-z]", "", r.get("wilayah", "").lower()) in _KECAMATAN_SET
    )
    return "kecamatan" if cocok >= 5 else "kategori"


# ──────────────────────────────────────────────────────────────────────── #
#  API utama
# ──────────────────────────────────────────────────────────────────────── #
def ekstrak_tabel_gemini(pdf_path: str, hal_awal: int, hal_akhir: int) -> list[dict]:
    """
    Ekstrak tabel dari PDF menggunakan Gemini Vision AI.

    → list[dict] format sama dengan engine.ekstrak_range().
    """
    if not gemini_tersedia():
        raise RuntimeError(f"Gemini Vision tidak tersedia: {_alasan_tidak_tersedia()}")

    halaman_data = []  # list of (pno, gemini_response_dict)

    for pno in range(hal_awal, hal_akhir + 1):
        logger.info("Gemini Vision: memproses halaman %d …", pno)
        try:
            img = _render_halaman(pdf_path, pno)
            data = _panggil_gemini(img)
            halaman_data.append((pno, data))
        except Exception as e:
            logger.error("Gemini Vision gagal di halaman %d: %s", pno, e)
            # Halaman gagal → lewati (bisa jadi halaman grafik/kosong)
            continue

        # Delay antar halaman supaya tidak kena rate limit
        time.sleep(1)

    if not halaman_data:
        return []

    # ── Gabung halaman: kelompokkan per tabel (lanjutan digabung) ──
    grup = []      # list of list[(pno, data)]
    current = []

    for pno, data in halaman_data:
        lanjutan = data.get("lanjutan", False)
        nomor = data.get("nomor_tabel", "")

        if not current:
            current = [(pno, data)]
        elif lanjutan:
            # Halaman lanjutan → gabung ke tabel saat ini
            current.append((pno, data))
        elif nomor and nomor != current[0][1].get("nomor_tabel", ""):
            # Tabel baru (nomor berbeda)
            grup.append(current)
            current = [(pno, data)]
        else:
            # Nomor sama tanpa flag lanjutan → gabung juga
            current.append((pno, data))

    if current:
        grup.append(current)

    # ── Rakit setiap grup menjadi satu tabel ──
    tabel_list = []
    for pages in grup:
        first_pno, first_data = pages[0]
        tabel = _gemini_ke_tabel(first_data)

        # Gabung baris dari halaman lanjutan
        for pno, data in pages[1:]:
            extra = _gemini_ke_tabel(data)
            tabel["rows"].extend(extra["rows"])
            # Total dari halaman terakhir yang punya total
            if extra["total"]:
                tabel["total"] = extra["total"]
            # Tambah kolom dari lanjutan jika headers kosong di pertama
            if not tabel["headers"] and extra["headers"]:
                tabel["headers"] = extra["headers"]
                tabel["n_kolom"] = extra["n_kolom"]

        # Update n_kolom berdasarkan data aktual
        if tabel["rows"]:
            max_kol = max(len(r["sel"]) for r in tabel["rows"])
            if max_kol > tabel["n_kolom"]:
                tabel["n_kolom"] = max_kol
                while len(tabel["headers"]) < max_kol:
                    tabel["headers"].append({
                        "nama": f"Kolom {len(tabel['headers']) + 1}",
                        "satuan": "", "tahun": "", "tipe": "num",
                    })

        # Deteksi mode
        tabel["mode"] = _deteksi_mode(tabel["rows"])

        # Info halaman
        tabel["halaman"] = [p[0] for p in pages]
        tabel["halaman_awal"] = min(tabel["halaman"])
        tabel["halaman_akhir"] = max(tabel["halaman"])

        # Info metode
        tabel["info_ocr"] = {
            "dipakai": False,
            "tersedia": False,
            "pesan": "",
        }

        tabel_list.append(tabel)

    return tabel_list
