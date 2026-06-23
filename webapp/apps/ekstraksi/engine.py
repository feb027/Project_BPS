"""
Engine ekstraksi tabel PDF digital BPS (Kabupaten Dalam Angka).

Fitur:
- Segmentasi otomatis: satu rentang halaman bisa berisi BANYAK tabel.
  Tiap halaman dideteksi nomor/judul tabelnya. Halaman "Lanjutan/Continued"
  digabung ke tabel sebelumnya; halaman dengan nomor tabel baru memulai
  tabel baru. -> preview tidak lagi menyatukan tabel berbeda.
- Identitas tabel otomatis: nomor, judul (ID & EN), nama bab, sumber.
- Definisi kolom otomatis: nama indikator, satuan (dari tanda kurung),
  tahun (bila header berupa tahun), serta tipe nilai (num/teks).
- Jenis tabel otomatis: 'kecamatan' (baris cocok master 39 kecamatan)
  atau 'kategori' (baris label bebas: umur/partai/jabatan/...).

Watermark (hitam murni 0,0,0) dibuang lebih dulu; teks data berwarna gelap.
"""
from __future__ import annotations

import difflib
import re

import pdfplumber

KECAMATAN = [
    "Cipatujah", "Karangnunggal", "Cikalong", "Pancatengah", "Cikatomas", "Cibalong",
    "Parungponteng", "Bantarkalong", "Bojongasih", "Culamega", "Bojonggambir", "Sodonghilir",
    "Taraju", "Salawu", "Puspahiang", "Tanjungjaya", "Sukaraja", "Salopa", "Jatiwaras", "Cineam",
    "Karangjaya", "Manonjaya", "Gunungtanjung", "Singaparna", "Sukarame", "Mangunreja",
    "Cigalontang", "Leuwisari", "Sariwangi", "Padakembang", "Sukaratu", "Cisayong", "Sukahening",
    "Rajapolah", "Jamanis", "Ciawi", "Kadipaten", "Pagerageung", "Sukaresik",
]
_KEC_LOWER = {k.lower(): k for k in KECAMATAN}

_NOMOR_RE = re.compile(r"\d+(?:\.\d+){1,3}")


# --------------------------------------------------------------------------- #
#  Watermark & geometri dasar
# --------------------------------------------------------------------------- #
def is_watermark(obj):
    """
    Deteksi teks watermark berdasarkan kemiringannya (rotasi diagonal).
    Teks biasa memiliki matriks (s, 0, 0, s, tx, ty) di mana elemen ke-1 dan ke-2 mendekati 0.
    Watermark BPS biasanya diputar 45 derajat (sin 45 = 0.707).
    """
    matrix = obj.get("matrix")
    if matrix and isinstance(matrix, (list, tuple)) and len(matrix) >= 4:
        # Jika nilai sin(theta) signifikan, teks diputar (bukan horizontal)
        if abs(matrix[1]) > 0.1 or abs(matrix[2]) > 0.1:
            return True
    return False


def clean_page(page):
    return page.filter(lambda o: not (o.get("object_type") == "char" and is_watermark(o)))


def cluster_lines(chars, tol=None):
    if not chars:
        return []
    if tol is None:
        import statistics
        sizes = [c.get("size", 10) for c in chars if "size" in c]
        med = statistics.median(sizes) if sizes else 10.0
        tol = med * 0.4
    chars = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines = []
    for c in chars:
        for ln in lines:
            if abs(ln["top"] - c["top"]) <= tol:
                ln["chars"].append(c)
                break
        else:
            lines.append({"top": c["top"], "chars": [c]})
    for ln in lines:
        ln["chars"].sort(key=lambda c: c["x0"])
    lines.sort(key=lambda l: l["top"])
    return lines


def _edges_from_items(items, min_gap=None, body_left=None, body_right=None):
    """
    Deteksi batas kolom dari CELAH vertikal (gutter) antar teks.
    Dipakai utk tabel TANPA garis (borderless) & hasil OCR.
    items: list dict dengan 'x0','x1'. -> list edge (x) atau None.
    """
    if not items:
        return None
    if min_gap is None:
        import statistics
        widths = [i.get("x1", 0) - i.get("x0", 0) for i in items]
        med_w = statistics.median(widths) if widths else 5.0
        min_gap = med_w * 1.5
    if not items:
        return None
    left = body_left if body_left is not None else min(i["x0"] for i in items)
    right = body_right if body_right is not None else max(i["x1"] for i in items)
    width = int(right - left) + 2
    if width <= 1:
        return None
    occ = bytearray(width)
    for it in items:
        a = max(0, int(it["x0"] - left))
        b = min(width - 1, int(it["x1"] - left))
        for x in range(a, b + 1):
            occ[x] = 1
    edges = [left]
    j = 0
    while j < width:
        if not occ[j]:
            k = j
            while k < width and not occ[k]:
                k += 1
            if (k - j) >= min_gap:
                edges.append((j + k) / 2 + left)
            j = k
        else:
            j += 1
    edges.append(right)
    edges = sorted(set(round(e, 1) for e in edges))
    return edges if len(edges) >= 3 else None


def col_edges(page):
    """Batas kolom: utamakan garis tabel (find_tables); cadangan: celah teks."""
    try:
        tabs = page.find_tables()
    except Exception:
        tabs = []
    if tabs:
        xset = set()
        for cell in tabs[0].cells:
            if cell:
                xset.add(round(cell[0], 1))
                xset.add(round(cell[2], 1))
        edges = sorted(xset)
        if len(edges) >= 3:
            return edges
    # --- cadangan borderless: pakai celah teks di area badan tabel ---
    tbl_top = _table_top(page)
    lo = (tbl_top - 5) if tbl_top else 130
    body = [c for c in page.chars if lo < c["top"] < 560]
    return _edges_from_items(body, min_gap=None)


def row_to_cols(line, edges):
    cols = [""] * (len(edges) - 1)
    for c in line["chars"]:
        cx = (c["x0"] + c["x1"]) / 2
        for i in range(len(edges) - 1):
            if edges[i] <= cx < edges[i + 1]:
                cols[i] += c["text"]
                break
    return [re.sub(r"\s+", " ", x).strip() for x in cols]


# --------------------------------------------------------------------------- #
#  Pembersih nilai & pencocokan
# --------------------------------------------------------------------------- #
def clean_num(raw):
    """-> (nilai_num_str|None, teks, flag)"""
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


def match_kec(s):
    s2 = re.sub(r"^\s*\d+[.\)]?\s*", "", s)
    s2 = re.sub(r"[^A-Za-z]", "", s2).lower()
    if not s2:
        return None
    if s2 in _KEC_LOWER:
        return _KEC_LOWER[s2]
    m = difflib.get_close_matches(s2, list(_KEC_LOWER.keys()), n=1, cutoff=0.82)
    return _KEC_LOWER[m[0]] if m else None


def is_kab_total(name):
    n = re.sub(r"[^a-z ]", " ", name.lower())
    if "dalam" in n:
        return False
    return "kabupaten tasikmalaya" in n


def _norm_label(s):
    return (s.replace("\u2013", "-").replace("\u2014", "-")
             .replace("û", "-").replace("Γ", "").strip())


# --------------------------------------------------------------------------- #
#  Deteksi identitas tabel (nomor, judul ID/EN, bab, sumber)
# --------------------------------------------------------------------------- #
def _font(w):
    return w.get("fontname", "")


def _is_italic(w):
    """Italic/oblique terdeteksi lintas-font (tidak terikat MyriadPro)."""
    f = _font(w).lower()
    return "it" in f or "italic" in f or "oblique" in f


def _table_top(page):
    """Tepi atas tabel (anchor bebas-font utk awal area header). None bila tak ada."""
    try:
        tabs = page.find_tables()
    except Exception:
        tabs = []
    if not tabs:
        return None
    return min(t.bbox[1] for t in tabs)


def identitas_halaman(page):
    """
    -> dict(lanjutan, nomor, judul_id, judul_en, bab, sumber)
    Anchor: 'Tabel'/'Table' di kolom kiri (atas), tepi atas tabel (bawah).
    Pemisah ID/EN: baris non-italic vs italic; cadangan: batas tahun.
    """
    words = page.extract_words(extra_attrs=["fontname"])
    txt = page.extract_text() or ""

    lanjutan = bool(re.search(r"Lanjutan|Continued", txt))

    nomor = None
    m = re.search(r"(?:Lanjutan\s+Tabel|Continued\s+Table)[^\d]*(\d+(?:\.\d+){1,3})", txt)
    if m:
        nomor = m.group(1)
    else:
        mm = re.search(r"(?m)^\s*(\d+(?:\.\d+){1,3})\s*$", txt)
        if mm:
            nomor = mm.group(1)

    # anchor atas: kata 'Tabel'/'Table'/'Gambar' di kolom kiri; cadangan: posisi tetap
    kata_tabel = [w for w in words
                  if w["text"] in ("Tabel", "Table", "Gambar", "Figure") and w["x0"] < 75]
    tabel_top = min((w["top"] for w in kata_tabel), default=None)
    # anchor bawah area judul: tepi atas tabel
    header_top = _table_top(page) or 9999

    def order(ws):
        ws = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
        return re.sub(r"\s+", " ", " ".join(w["text"] for w in ws)).strip()

    judul_id = judul_en = ""
    if tabel_top is not None:
        lo, hi = tabel_top - 3, header_top - 3
        # judul ada di kolom teks (x0 > ~110), abaikan nomor tabel di kolom kiri
        reg = [w for w in words if w["x0"] > 105 and lo <= w["top"] < hi]
        idw = [w for w in reg if not _is_italic(w)]
        enw = [w for w in reg if _is_italic(w)]
        if idw and enw:
            judul_id, judul_en = order(idw), order(enw)
        else:
            # font tidak memisahkan ID/EN -> pakai batas tahun pertama
            full = order(reg)
            mm = re.search(r",?\s*(?:19|20)\d{2}", full)
            if mm:
                judul_id, judul_en = full[:mm.end()].strip(), full[mm.end():].strip()
            else:
                judul_id = full

    bab = ""
    # nama bab = running header paling atas (kapital), bukan footer "...Dalam Angka"
    atas = [w for w in words if w["top"] < 35]
    cand = " ".join(w["text"] for w in sorted(atas, key=lambda w: w["x0"])).strip()
    cand = re.sub(r"^\d+(?:\.\d+)*\s*", "", cand)  # buang nomor bab bila ada
    if cand and "DALAM ANGKA" not in cand.upper() and len(cand) < 60:
        bab = cand.title()

    sumber = ""
    ms = re.search(r"Sumber\s*/?\s*Source\s*:\s*(.+)", txt)
    if not ms:
        ms = re.search(r"Sumber\s*:\s*(.+)", txt)
    if ms:
        sumber = ms.group(1).strip()

    return {"lanjutan": lanjutan, "nomor": nomor, "judul_id": judul_id,
            "judul_en": judul_en, "bab": bab, "sumber": sumber}


# --------------------------------------------------------------------------- #
#  Deteksi header kolom + satuan + tahun + tipe
# --------------------------------------------------------------------------- #
def _parse_satuan(teks):
    """Ambil satuan dari tanda kurung paling kanan, mis '(km2/sq.km)' -> 'km2'."""
    paren = re.findall(r"\(([^)]*)\)", teks)
    for p in reversed(paren):
        p = p.strip()
        if not p or p in ("1", "2", "3", "4", "5", "6"):
            continue
        # buang nomor kolom seperti '1', dan ambil bagian ID sebelum '/'
        bagian = p.split("/")[0].strip()
        bagian = re.sub(r"[a-z]\.[a-z].*", "", bagian).strip()  # buang 'a.s.l' dsb
        if bagian:
            return bagian
    return ""


def _bersih_nama_kolom(teks):
    """Buang terjemahan EN & satuan; sisakan nama indikator ID yang ringkas."""
    teks = re.sub(r"\([^)]*\)", "", teks)               # buang (satuan)
    teks = re.sub(r"\s+", " ", teks).strip(" /")
    return teks.strip()


def detect_headers(page, edges):
    """
    -> list per kolom: dict(nama, satuan, tahun, tipe)
       Kolom-0 (label baris) ikut, pemanggil membuang index 0.
    Area header = antara tepi atas tabel dan baris '(1)(2)..'. Bebas-font:
    nama ID = kata non-italic; terjemahan EN (italic) dibuang.
    """
    cpage = clean_page(page)
    words = cpage.extract_words(extra_attrs=["fontname"])
    tbl_top = _table_top(page) or 110
    # baris '(1)(2)..' menandai akhir header
    colnum_top = None
    for ln in cluster_lines(cpage.chars, tol=None):
        if ln["top"] < tbl_top - 2:
            continue
        t = "".join(c["text"] for c in ln["chars"]).strip()
        # baris penanda kolom: deretan '(1)(2)(3)..' (kadang '(1)' diabaikan -> mulai '(2)')
        if re.fullmatch(r"(?:\(\d+\)\s*){2,}", t):
            colnum_top = ln["top"]
            break
    n = len(edges) - 1
    # Fallback jika baris (1)(2)(3) tidak ketemu di halaman ini
    if colnum_top is None:
        # Coba cari baris dengan pola angka kolom yang lebih longgar
        for ln in cluster_lines(cpage.chars, tol=None):
            t = "".join(c["text"] for c in ln["chars"]).strip()
            if re.search(r"\(\d+\)", t) and ln["top"] > tbl_top:
                colnum_top = ln["top"]
                break
        if colnum_top is None:
            colnum_top = tbl_top + 80   # fallback: ambil 80pt di bawah top tabel
    # Pisahkan kata ID dan EN, ambil hanya ID
    id_words = []
    for w in words:
        if (tbl_top - 4 < w["top"] < colnum_top - 1) and not _is_italic(w):
            id_words.append(w)
            
    # Kelompokkan kata-kata header menjadi baris
    header_lines = cluster_lines(id_words, tol=None)
    
    # Ambil sel-sel tabel di area header jika ada (membantu deteksi span/gabungan kolom)
    header_cells = []
    try:
        tabs = page.find_tables()
        if tabs:
            for c in tabs[0].cells:
                if c and c[1] < colnum_top:
                    header_cells.append(c)
    except Exception:
        pass

    col_headers = [[] for _ in range(n)]
    
    for ln in header_lines:
        # Gabungkan kata-kata yang berdekatan di baris ini
        ln_words = ln["chars"]
        
        # Kata-kata sudah diurutkan dari x0 ke x1 di cluster_lines
        merged_blocks = []
        if ln_words:
            curr_w = {
                "text": ln_words[0]["text"], 
                "x0": ln_words[0]["x0"], 
                "x1": ln_words[0]["x1"],
                "top": ln["top"],
                "bottom": ln_words[0]["bottom"]
            }
            for w in ln_words[1:]:
                # Jika jaraknya dekat, gabungkan
                if w["x0"] - curr_w["x1"] < 15.0: # toleransi spasi
                    curr_w["text"] += " " + w["text"]
                    curr_w["x1"] = w["x1"]
                    curr_w["bottom"] = max(curr_w["bottom"], w["bottom"])
                else:
                    merged_blocks.append(curr_w)
                    curr_w = {
                        "text": w["text"], "x0": w["x0"], "x1": w["x1"], 
                        "top": ln["top"], "bottom": w["bottom"]
                    }
            merged_blocks.append(curr_w)
            
        # Alokasikan blok teks ke kolom-kolom yang bersilangan
        for blk in merged_blocks:
            span_x0, span_x1 = blk["x0"], blk["x1"]
            
            # Jika blk ini berada di dalam sel header yang membentang (colspan), gunakan rentang sel
            for c in header_cells:
                if c[0] - 5 <= blk["x0"] and blk["x1"] <= c[2] + 5 and c[1] - 5 <= blk["top"] and blk["bottom"] <= c[3] + 5:
                    span_x0 = c[0]
                    span_x1 = c[2]
                    break

            for i in range(n):
                col_x0 = edges[i]
                col_x1 = edges[i + 1]
                
                # Cek persilangan (intersection) antara [span_x0, span_x1] dan [col_x0, col_x1]
                overlap_x0 = max(span_x0, col_x0)
                overlap_x1 = min(span_x1, col_x1)
                
                # Jika bersilangan signifikan atau pusat blok ada di kolom ini
                if overlap_x1 - overlap_x0 > 5 or (col_x0 <= (span_x0 + span_x1)/2 < col_x1):
                    col_headers[i].append(blk["text"].strip())

    out = []
    for i in range(n):
        lines = col_headers[i]
        
        # Bersihkan dari satuan dan gabungkan
        nama_id = ""
        satuan = ""
        tahun = ""
        
        if lines:
            raw_full = " ".join(lines)
            satuan = _parse_satuan(raw_full)
            
            # Format Multi-level: [Baris 1] Baris 2 ... (jika ada lebih dari 1 baris logis)
            bersih_lines = [_bersih_nama_kolom(l) for l in lines]
            bersih_lines = [l for l in bersih_lines if l]
            
            if len(bersih_lines) > 1:
                # Anggap elemen pertama adalah Super-Header/Group
                nama_id = f"[{bersih_lines[0]}] {' '.join(bersih_lines[1:])}"
            elif len(bersih_lines) == 1:
                nama_id = bersih_lines[0]
                
            mt = re.match(r"^(19|20)\d{2}", re.sub(r"\D", "", nama_id)[:4] or "")
            if mt:
                tahun = mt.group(0)
                
            if tahun and not re.search(r"[A-Za-z]", nama_id):
                nama_id = ""
                
        out.append({"nama": nama_id.strip(), "satuan": satuan, "tahun": tahun, "tipe": "num"})
    return out


# --------------------------------------------------------------------------- #
#  Ekstraksi baris (mode kecamatan & kategori) per halaman
# --------------------------------------------------------------------------- #
def extract_page_rows(page):
    """Mode kecamatan: anchor master 39 kecamatan. -> (rows[(nama,cells)], kab|None)."""
    page = clean_page(page)
    edges = col_edges(page)
    if not edges:
        return [], None
    chars = page.chars
    anchors = []
    for ln in cluster_lines(chars, tol=None):
        if len(ln["chars"]) < 3 or ln["top"] < 130:
            continue
        name = row_to_cols(ln, edges)[0]
        if is_kab_total(name):
            anchors.append((ln["top"], "__KAB__"))
        else:
            kec = match_kec(name)
            if kec:
                anchors.append((ln["top"], kec))
    anchors.sort(key=lambda a: a[0])

    rows, kab = [], None
    for i, (top, name) in enumerate(anchors):
        lo = (anchors[i - 1][0] + top) / 2 if i > 0 else top - 5
        hi = (anchors[i + 1][0] + top) / 2 if i + 1 < len(anchors) else top + 6
        band = [c for c in chars if lo < c["top"] <= hi]
        cols = row_to_cols({"chars": band}, edges)
        if name == "__KAB__":
            kab = cols
        else:
            rows.append((name, cols))
    return rows, kab


def extract_page_rows_kategori(page):
    """Mode kategori: label kolom-0 (gabung multi-baris) + baris nilai."""
    page = clean_page(page)
    edges = col_edges(page)
    if not edges:
        return [], None
    lines = cluster_lines(page.chars, tol=None)
    rtop, rbot = 130, 9999
    for ln in lines:
        t = "".join(c["text"] for c in ln["chars"]).strip()
        if re.fullmatch(r"(?:\(\d+\)\s*){2,}", t):
            rtop = ln["top"] + 4
        if re.search(r"Catatan/|Sumber/|Note\s*:|Source\s*:", t):
            rbot = ln["top"] - 2
            break
    rows, kab, pending = [], None, ""
    for ln in lines:
        if not (rtop <= ln["top"] <= rbot):
            continue
        cols = row_to_cols(ln, edges)
        has_val = any(re.search(r"\d", c) or c.strip() in ("-", "–", "—") for c in cols[1:])
        label = _norm_label(cols[0])
        # label valid bila mengandung huruf ATAU angka (mis. kelompok umur '0-4')
        punya_label = bool(re.search(r"[A-Za-z0-9]", label))
        if has_val:
            use = label if punya_label else pending
            if is_kab_total(use):
                kab = cols
            elif use.strip():
                rows.append((use, cols))
            # baris bernilai tanpa label sama sekali = duplikat/total bayangan -> dilewati
            pending = ""
        elif punya_label:
            pending = label
    return rows, kab


# --------------------------------------------------------------------------- #
#  Bangun satu tabel dari sekumpulan halaman (utama + lanjutan)
# --------------------------------------------------------------------------- #
def _buat_sel(cells):
    out = []
    for raw in cells:
        num, teks, flag = clean_num(raw)
        out.append({"teks": teks, "num": num, "flag": flag})
    return out


def _rakit_tabel(pages_info):
    """
    pages_info: list of (page, identitas) -> satu tabel.
    Deteksi tipe (kecamatan/kategori) otomatis, gabung antar-halaman.
    """
    ident0 = pages_info[0][1]
    ada_ocr = any(len(info) > 2 and info[2] for info in pages_info)

    def _edges_of(page, is_ocr):
        return col_edges(page if is_ocr else clean_page(page))

    # --- tentukan headers dari halaman pertama ---
    headers = []
    label_kolom = ""
    first_page = pages_info[0][0]
    first_ocr = len(pages_info[0]) > 2 and pages_info[0][2]
    edges = _edges_of(first_page, first_ocr)
    if edges:
        allh = detect_headers(first_page, edges)
        if allh:
            label_kolom = allh[0]["nama"]
            headers = allh[1:]

    # --- coba mode kecamatan dulu; bila baris sedikit -> kategori ---
    def kumpul(mode):
        gabung, urutan, total_cells = {}, [], None
        for info in pages_info:
            page = info[0]
            if mode == "kategori":
                rows, kab = extract_page_rows_kategori(page)
            else:
                rows, kab = extract_page_rows(page)
            for nama, cols in rows:
                if nama not in gabung:
                    gabung[nama] = []
                    urutan.append(nama)
                gabung[nama].extend(cols[1:])
            if kab:
                total_cells = (total_cells or []) + kab[1:]
        return gabung, urutan, total_cells

    g_kec, u_kec, t_kec = kumpul("kecamatan")
    if len(u_kec) >= 5:
        mode = "kecamatan"
        gabung, urutan, total_cells = g_kec, u_kec, t_kec
    else:
        mode = "kategori"
        gabung, urutan, total_cells = kumpul("kategori")

    n_kolom = max((len(v) for v in gabung.values()), default=0)

    hasil_rows = [{"wilayah": n, "sel": _buat_sel(gabung[n])} for n in urutan]
    total = ({"wilayah": "Kabupaten Tasikmalaya", "sel": _buat_sel(total_cells)}
             if total_cells else None)

    # --- samakan panjang headers dengan n_kolom ---
    while len(headers) < n_kolom:
        headers.append({"nama": "", "satuan": "", "tahun": "", "tipe": "num"})
    headers = headers[:n_kolom]

    # bila kolom tanpa nama tapi judul punya indikator tunggal (mis. 'Jumlah Desa')
    judul = ident0.get("judul_id", "")
    indikator_judul = _indikator_dari_judul(judul)
    for idx, h in enumerate(headers):
        if not h["nama"]:
            # 1) kolom tahun murni -> pakai indikator dari judul
            # 2) lainnya -> pakai indikator judul, atau 'Kolom N' sbg cadangan akhir
            h["nama"] = indikator_judul or f"Kolom {idx + 1}"

    halaman = [info[0].page_number for info in pages_info]
    tabel_dict = {
        "nomor": ident0.get("nomor") or "",
        "judul_id": judul,
        "judul_en": ident0.get("judul_en", ""),
        "bab": ident0.get("bab", ""),
        "sumber": ident0.get("sumber", ""),
        "mode": mode,
        "ocr": ada_ocr,
        "n_kolom": n_kolom,
        "headers": headers,
        "label_kolom": label_kolom,
        "rows": hasil_rows,
        "total": total,
        "halaman": halaman,
        "halaman_awal": min(halaman),
        "halaman_akhir": max(halaman),
    }
    return auto_correct_table(tabel_dict)


def _indikator_dari_judul(judul):
    """Tebak nama indikator dari judul: ambil frasa sebelum 'Menurut'."""
    if not judul:
        return ""
    m = re.split(r"\bMenurut\b", judul, maxsplit=1)
    nama = m[0].strip().rstrip(",")
    return nama[:120]


def _angka(teks):
    """Parse angka gaya Indonesia '1.946.197' / '2.706,82' -> float|None."""
    num, _, flag = clean_num(teks)
    if num is None:
        return None
    try:
        return float(num)
    except (TypeError, ValueError):
        return None


def cek_total(tabel):
    """
    Validasi: jumlah nilai baris per kolom == nilai baris TOTAL.
    -> dict(ada_total, per_kolom=[{kolom, jumlah_baris, total, cocok, selisih}],
            semua_cocok)
    Hanya kolom numerik yang diperiksa. Toleransi kecil utk pembulatan desimal.
    Untuk tabel berisi sub-total (mis. 'Golongan I'), penjumlahan baris bisa
    > total -> ditandai tidak cocok agar diperiksa manusia (bukan auto-benar).
    """
    total = tabel.get("total")
    if not total:
        return {"ada_total": False, "per_kolom": [], "semua_cocok": True}

    n = tabel["n_kolom"]
    per_kolom = []
    semua = True
    for j in range(n):
        tnum = _angka(total["sel"][j]["teks"]) if j < len(total["sel"]) else None
        if tnum is None:
            per_kolom.append({"kolom": j, "jumlah_baris": None, "total": None,
                              "cocok": None, "selisih": None})
            continue
        jml = 0.0
        ada_angka = False
        for row in tabel["rows"]:
            if j < len(row["sel"]):
                v = _angka(row["sel"][j]["teks"])
                if v is not None:
                    jml += v
                    ada_angka = True
        if not ada_angka:
            per_kolom.append({"kolom": j, "jumlah_baris": None, "total": tnum,
                              "cocok": None, "selisih": None})
            continue
        tol = max(1.0, abs(tnum) * 0.005)  # toleransi 0.5% atau 1 unit
        cocok = abs(jml - tnum) <= tol
        if not cocok:
            semua = False
        per_kolom.append({
            "kolom": j,
            "jumlah_baris": round(jml, 2),
            "total": tnum,
            "cocok": cocok,
            "selisih": round(jml - tnum, 2),
        })
    return {"ada_total": True, "per_kolom": per_kolom, "semua_cocok": semua}


def auto_correct_table(tabel):
    """
    Auto-correct tabel jika ada tepat 1 sel kosong/perlu_cek yang menyebabkan total tidak cocok.
    Berlaku untuk memperbaiki kegagalan OCR yang hanya terjadi di 1 baris.
    """
    if not tabel.get("total"):
        return tabel
        
    hasil_cek = cek_total(tabel)
    if not hasil_cek["ada_total"] or hasil_cek["semua_cocok"]:
        return tabel
        
    for info in hasil_cek["per_kolom"]:
        if info["cocok"] is False and info["selisih"] is not None:
            col_idx = info["kolom"]
            selisih = info["selisih"]
            
            baris_target = []
            for r in tabel["rows"]:
                if col_idx < len(r["sel"]):
                    sel = r["sel"][col_idx]
                    if sel["flag"] in ("nihil", "tidak_tersedia", "perlu_cek"):
                        baris_target.append(sel)
            
            # Jika tepat ada 1 sel target, otomatis isi dengan nilai selisih (dibalik)
            if len(baris_target) == 1:
                koreksi = round(-selisih, 4)
                if koreksi != 0:
                    str_koreksi = str(int(koreksi)) if koreksi.is_integer() else str(koreksi)
                    str_koreksi = str_koreksi.replace('.', ',')
                    
                    baris_target[0]["teks"] = str_koreksi
                    baris_target[0]["num"] = str_koreksi.replace(',', '.')
                    baris_target[0]["flag"] = "auto_corrected"
                    
    return tabel


# --------------------------------------------------------------------------- #
#  Halaman OCR (untuk PDF hasil scan) — meniru antarmuka pdfplumber.Page
# --------------------------------------------------------------------------- #
class _OcrPage:
    """
    Page-like dari hasil OCR. Mengekspos antarmuka minimal yang dipakai engine:
    .chars, .page_number, .extract_words(), .extract_text(), .find_tables(), .filter().
    Kolom dideteksi via celah teks (borderless), sebab OCR tak punya garis.
    """

    def __init__(self, words, page_number):
        self._words = words
        self.page_number = page_number
        self.chars = []
        for w in words:
            for ch in w["text"]:
                self.chars.append({
                    "text": ch, "x0": w["x0"], "x1": w["x1"],
                    "top": w["top"], "bottom": w["bottom"],
                    "non_stroking_color": (0.1, 0.1, 0.1),
                })

    def extract_words(self, **kw):
        return [dict(w, fontname="OCR") for w in self._words]

    def extract_text(self, **kw):
        lines = cluster_lines(self.chars, 3.5)
        return "\n".join("".join(c["text"] for c in ln["chars"]) for ln in lines)

    def find_tables(self, *a, **k):
        return []

    def filter(self, fn):
        return self  # watermark filter tak perlu (hasil OCR sudah 'bersih')


# --------------------------------------------------------------------------- #
#  API utama
# --------------------------------------------------------------------------- #
def ekstrak_range(pdf_path, hal_awal, hal_akhir, pakai_ocr="auto",
                   pakai_gemini=False):
    """
    Segmentasi rentang halaman menjadi DAFTAR tabel.
    pakai_ocr: 'auto' (OCR hanya utk halaman scan), 'paksa' (OCR semua),
               'tidak' (jangan OCR).
    pakai_gemini: True → gunakan Gemini Vision AI (lebih akurat utk tabel
                  kompleks, butuh API key + internet).
    -> list[dict] (lihat _rakit_tabel; tiap tabel punya kunci 'ocr' bool).
    """
    # ── Gemini Vision path ──
    if pakai_gemini:
        from . import gemini_vision as _gv
        if not _gv.gemini_tersedia():
            raise RuntimeError(
                f"Gemini Vision tidak tersedia: {_gv._alasan_tidak_tersedia()}"
            )
        return _gv.ekstrak_tabel_gemini(pdf_path, hal_awal, hal_akhir)

    # ── pdfplumber path (engine lama) ──
    from . import ocr as _ocr

    tabel_list = []
    info_ocr = {"dipakai": False, "tersedia": _ocr.ocr_tersedia(), "pesan": ""}

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        grup = []  # list of (page, identitas, is_ocr)

        def page_untuk(pno):
            """Kembalikan (page_obj, is_ocr). OCR bila perlu & tersedia."""
            jenis = "digital"
            if pakai_ocr == "paksa":
                jenis = "scan"
            elif pakai_ocr == "auto":
                jenis = _ocr.klasifikasi_halaman(pdf_path, pno)
            if jenis == "scan":
                if not info_ocr["tersedia"]:
                    info_ocr["pesan"] = _ocr.PESAN_INSTALL
                    return pdf.pages[pno - 1], False
                try:
                    words, _ = _ocr.kata_ocr_halaman(pdf_path, pno)
                    info_ocr["dipakai"] = True
                    return _OcrPage(words, pno), True
                except _ocr.OcrTidakTersedia as e:
                    info_ocr["pesan"] = str(e)
                    return pdf.pages[pno - 1], False
            return pdf.pages[pno - 1], False

        for pno in range(hal_awal, hal_akhir + 1):
            if pno < 1 or pno > n_pages:
                continue
            page, is_ocr = page_untuk(pno)
            ident = identitas_halaman(page)
            edges = col_edges(clean_page(page) if not is_ocr else page)
            if edges is None:
                continue  # halaman tanpa tabel (mis. grafik) -> lewati
            mulai_baru = (not ident["lanjutan"]) and bool(ident["nomor"]) and bool(grup)
            if not grup:
                grup = [(page, ident, is_ocr)]
            elif mulai_baru:
                tabel_list.append(_rakit_tabel(grup))
                grup = [(page, ident, is_ocr)]
            else:
                grup.append((page, ident, is_ocr))
        if grup:
            tabel_list.append(_rakit_tabel(grup))

    for t in tabel_list:
        t["info_ocr"] = info_ocr
        t["gemini"] = False
    return tabel_list


def ekstrak(pdf_path, hal_awal, hal_akhir, mode=None):
    """Kompatibilitas lama: kembalikan tabel pertama dari rentang."""
    daftar = ekstrak_range(pdf_path, hal_awal, hal_akhir)
    if not daftar:
        return {"n_kolom": 0, "rows": [], "total": None, "headers": [], "label_kolom": ""}
    t = daftar[0]
    return {
        "n_kolom": t["n_kolom"], "rows": t["rows"], "total": t["total"],
        "headers": [h["nama"] for h in t["headers"]], "label_kolom": t["label_kolom"],
    }
