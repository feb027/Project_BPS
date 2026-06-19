"""
Ekstraktor tabel BPS - Kabupaten Tasikmalaya Dalam Angka 2026 (PDF digital).
Batch pertama: BAB 1 - GEOGRAFI (tabel 1.1.1, 1.1.2, 1.1.3).

Strategi inti:
- Cluster karakter jadi baris-teks (toleransi-y ketat) -> watermark jatuh ke baris sendiri.
- Petakan karakter ke kolom berdasarkan batas-x dari struktur tabel.
- Kolom angka: buang karakter watermark (huruf/slash/titikdua), titik=ribuan, koma=desimal.
- Kolom nama kecamatan: cocokkan ke daftar master 39 kecamatan (fuzzy).
- Gabungkan halaman utama + "Lanjutan Tabel" -> emit baris format LONG.
"""
import pdfplumber
import re
import csv
import difflib
import os

PDF = "kabupaten-tasikmalaya-dalam-angka-2026.pdf"
OUT_DIR = "output"

# Daftar master 39 kecamatan Kab. Tasikmalaya (urutan resmi sesuai publikasi)
KECAMATAN = [
    "Cipatujah","Karangnunggal","Cikalong","Pancatengah","Cikatomas","Cibalong",
    "Parungponteng","Bantarkalong","Bojongasih","Culamega","Bojonggambir","Sodonghilir",
    "Taraju","Salawu","Puspahiang","Tanjungjaya","Sukaraja","Salopa","Jatiwaras","Cineam",
    "Karangjaya","Manonjaya","Gunungtanjung","Singaparna","Sukarame","Mangunreja",
    "Cigalontang","Leuwisari","Sariwangi","Padakembang","Sukaratu","Cisayong","Sukahening",
    "Rajapolah","Jamanis","Ciawi","Kadipaten","Pagerageung","Sukaresik",
]
KEC_LOWER = {k.lower(): k for k in KECAMATAN}

# Konfigurasi tabel BAB 1. indikator = nama tiap kolom angka SETELAH kolom nama.
# tipe: 'num' (angka) atau 'text' (teks, mis. nama ibukota).
BAB1 = {
    "1.1.1": {
        "judul": "Luas Daerah dan Jumlah Pulau Menurut Kecamatan, 2025",
        "halaman": [46, 47],
        "kolom": [("Luas Daerah", "km2", "num"), ("Jumlah Pulau", "pulau", "num")],
    },
    "1.1.2": {
        "judul": "Tinggi Wilayah (mdpl) dan Jarak ke Ibukota (km), 2025",
        "halaman": [48, 49],
        "kolom": [("Tinggi Wilayah", "mdpl", "num"), ("Jarak ke Ibukota", "km", "num")],
    },
    "1.1.3": {
        "judul": "Ibukota Kecamatan dan Persentase Luas Wilayah Terhadap Kabupaten, 2025",
        "halaman": [50, 51],
        "kolom": [("Ibukota Kecamatan", "-", "text"),
                  ("Persentase terhadap Luas Kabupaten", "%", "num")],
    },
}


def is_watermark(obj):
    """Karakter watermark = hitam murni (0,0,0). Teks data = (0.141,0.122,0.122)."""
    c = obj.get("non_stroking_color")
    if c is None:
        return False
    if isinstance(c, (list, tuple)):
        return len(c) > 0 and all(abs(float(v)) < 0.04 for v in c)
    try:
        return abs(float(c)) < 0.04
    except (TypeError, ValueError):
        return False


def clean_page(page):
    """Page tanpa karakter watermark (struktur tabel/garis tetap utuh)."""
    def keep(o):
        if o.get("object_type") == "char":
            return not is_watermark(o)
        return True
    return page.filter(keep)


def cluster_lines(chars, tol=4.0):
    chars = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines = []
    for c in chars:
        placed = False
        for ln in lines:
            if abs(ln["top"] - c["top"]) <= tol:
                ln["chars"].append(c); placed = True; break
        if not placed:
            lines.append({"top": c["top"], "chars": [c]})
    for ln in lines:
        ln["chars"].sort(key=lambda c: c["x0"])
    lines.sort(key=lambda l: l["top"])
    return lines


def col_edges(page):
    tabs = page.find_tables()
    if not tabs:
        return None
    xset = set()
    for cell in tabs[0].cells:
        if cell:
            xset.add(round(cell[0], 1)); xset.add(round(cell[2], 1))
    return sorted(xset)


def row_to_cols(line, edges):
    cols = [""] * (len(edges) - 1)
    for c in line["chars"]:
        cx = (c["x0"] + c["x1"]) / 2
        for i in range(len(edges) - 1):
            if edges[i] <= cx < edges[i + 1]:
                cols[i] += c["text"]; break
    return [re.sub(r"\s+", " ", x).strip() for x in cols]


def clean_num(raw):
    """-> (nilai_num, teks_asli, flag)"""
    raw = raw.strip()
    if "..." in raw or raw in ("..", "…"):
        return None, raw, "tidak_tersedia"
    neg = raw.startswith("(") and raw.endswith(")")   # notasi akuntansi (x) = negatif
    # buang karakter watermark (huruf/slash/titikdua), TAPI pertahankan tanda '-'
    keep = re.sub(r"[^0-9,.\-–—]", "", raw)
    if not re.search(r"\d", keep):
        # tidak ada digit sama sekali
        if re.search(r"[-–—]", keep):
            return None, raw, "nihil"        # sel '-' = nilai nihil/nol
        return None, raw, "tidak_tersedia"   # sel benar-benar kosong
    numpart = re.sub(r"[-–—]", "", keep)
    num = numpart.replace(".", "").replace(",", ".")  # ID: titik=ribuan, koma=desimal
    try:
        val = float(num)
        if val.is_integer():
            val = int(val)
    except ValueError:
        return None, raw, "perlu_cek"
    if neg:
        val = -val
    return val, raw, "ada"


def match_kec(s):
    """Cocokkan teks kolom-nama ke master kecamatan. -> (nama, flag) atau (None,None)."""
    # buang nomor urut "12." dan watermark; sisakan huruf
    s2 = re.sub(r"^\s*\d+[.\)]?\s*", "", s)
    s2 = re.sub(r"[^A-Za-z]", "", s2).lower()
    if not s2:
        return None, None
    if s2 in KEC_LOWER:
        return KEC_LOWER[s2], "ada"
    m = difflib.get_close_matches(s2, list(KEC_LOWER.keys()), n=1, cutoff=0.82)
    if m:
        return KEC_LOWER[m[0]], "ada"
    return None, None


def clean_text(raw):
    """Bersihkan kolom teks (mis. nama ibukota) dari sisa watermark terisolasi."""
    # buang token 1 huruf yang berdiri sendiri (sisa watermark)
    toks = [t for t in raw.split() if len(t) > 1 or t.isalpha() and len(t) > 1]
    out = " ".join(toks) if toks else raw
    return out.strip()


def is_kab_total(name):
    n = re.sub(r"[^a-z ]", " ", name.lower())
    n = re.sub(r"\s+", " ", n).strip()
    if "dalam" in n:      # tolak header halaman "...Dalam Angka 2026" (terpotong di batas kolom)
        return False
    return bool(re.search(r"kabupaten tasikmalaya", n))


def extract_page_rows(page):
    """Anchor pada baris-nama kecamatan, lalu ambil karakter per pita-y. Kokoh thd jitter."""
    page = clean_page(page)          # buang watermark dulu
    edges = col_edges(page)
    if not edges:
        return [], None
    chars = page.chars
    # 1) cluster ketat utk temukan baris-jangkar (nama kecamatan / total kabupaten)
    anchors = []  # (top, nama)
    for ln in cluster_lines(chars, tol=2.0):
        if len(ln["chars"]) < 3:
            continue
        if ln["top"] < 130:      # area header/judul halaman -> bukan baris data
            continue
        name = row_to_cols(ln, edges)[0]
        if is_kab_total(name):
            anchors.append((ln["top"], "__KAB__"))
        else:
            kec, _ = match_kec(name)
            if kec:
                anchors.append((ln["top"], kec))
    anchors.sort(key=lambda a: a[0])
    # 2) pita-y per jangkar (batas = titik tengah ke tetangga)
    rows, kab = [], None
    for i, (top, name) in enumerate(anchors):
        lo = (anchors[i - 1][0] + top) / 2 if i > 0 else top - 5
        hi = (anchors[i + 1][0] + top) / 2 if i + 1 < len(anchors) else top + 6
        band = [c for c in chars if lo < c["top"] <= hi]
        cols = [""] * (len(edges) - 1)
        for c in sorted(band, key=lambda c: c["x0"]):
            cx = (c["x0"] + c["x1"]) / 2
            for j in range(len(edges) - 1):
                if edges[j] <= cx < edges[j + 1]:
                    cols[j] += c["text"]; break
        cols = [re.sub(r"\s+", " ", x).strip() for x in cols]
        if name == "__KAB__":
            kab = cols
        else:
            rows.append((name, cols))
    return rows, kab


def extract_table(pdf, nomor, cfg):
    rows = []          # (wilayah, [raw cells])
    kab_total = None
    sumber = ""
    for pno in cfg["halaman"]:
        page = pdf.pages[pno - 1]
        txt = page.extract_text() or ""
        m = re.search(r"Sumber/Source\s*:\s*(.+)", txt)
        if m:
            sumber = m.group(1).strip()
        page_rows, page_kab = extract_page_rows(page)
        rows.extend(page_rows)
        if page_kab:
            kab_total = page_kab
    return rows, kab_total, sumber


def emit_long(nomor, cfg, rows, kab_total, sumber, writer):
    kolom = cfg["kolom"]
    n_emit = 0

    def emit(wilayah, cols):
        nonlocal n_emit
        # cols[0] = nama; cols[1..] = nilai per indikator
        for idx, (ind, sat, tipe) in enumerate(kolom):
            cell = cols[idx + 1] if idx + 1 < len(cols) else ""
            if tipe == "text":
                teks = clean_text(cell)
                # watermark sudah dibuang via clean_page -> teks bersih
                writer.writerow(["Geografi", nomor, cfg["judul"], wilayah, ind, sat,
                                 "", teks, "ada" if teks else "kosong", sumber])
            else:
                val, teks, fl = clean_num(cell)
                writer.writerow(["Geografi", nomor, cfg["judul"], wilayah, ind, sat,
                                 "" if val is None else val, teks, fl, sumber])
            n_emit += 1

    for wilayah, cols in rows:
        emit(wilayah, cols)
    if kab_total:
        emit("Kabupaten Tasikmalaya", kab_total)
    return n_emit, len(rows)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out_csv = os.path.join(OUT_DIR, "bab1_geografi_long.csv")
    print("=== EKSTRAKSI BAB 1 - GEOGRAFI ===\n")
    from collections import Counter
    flags = Counter()
    with pdfplumber.open(PDF) as pdf, open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["bab","nomor_tabel","judul_tabel","wilayah","indikator","satuan",
                    "nilai_num","nilai_teks","flag","sumber"])
        # bungkus writer utk menghitung flag
        class W:
            def writerow(self, row):
                flags[row[8]] += 1
                w.writerow(row)
        cw = W()
        for nomor, cfg in BAB1.items():
            rows, kab_total, sumber = extract_table(pdf, nomor, cfg)
            n_emit, n_kec = emit_long(nomor, cfg, rows, kab_total, sumber, cw)
            status = "OK" if n_kec == 39 else f"PERIKSA (dapat {n_kec})"
            print(f"Tabel {nomor}: {n_kec}/39 kecamatan, total_kab={'ada' if kab_total else 'TIDAK'}, "
                  f"baris_long={n_emit}  -> {status}")
    total = sum(flags.values())
    print(f"\n=== RINGKASAN VERIFIKASI ({total} sel) ===")
    for fl, n in flags.most_common():
        print(f"  {fl:16}: {n}")
    print(f"\nOutput: {out_csv}")


if __name__ == "__main__":
    main()
