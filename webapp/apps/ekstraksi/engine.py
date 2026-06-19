"""
Engine ekstraksi tabel kecamatan dari PDF digital BPS.
Port dari extract.py: filter watermark (hitam murni), anchor baris nama
kecamatan, petakan ke kolom via batas-x, bersihkan angka, gabung antar-halaman.
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


def is_watermark(obj):
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
    return page.filter(lambda o: not (o.get("object_type") == "char" and is_watermark(o)))


def cluster_lines(chars, tol=4.0):
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


def col_edges(page):
    tabs = page.find_tables()
    if not tabs:
        return None
    xset = set()
    for cell in tabs[0].cells:
        if cell:
            xset.add(round(cell[0], 1))
            xset.add(round(cell[2], 1))
    return sorted(xset)


def row_to_cols(line, edges):
    cols = [""] * (len(edges) - 1)
    for c in line["chars"]:
        cx = (c["x0"] + c["x1"]) / 2
        for i in range(len(edges) - 1):
            if edges[i] <= cx < edges[i + 1]:
                cols[i] += c["text"]
                break
    return [re.sub(r"\s+", " ", x).strip() for x in cols]


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


def extract_page_rows(page):
    """-> (rows[(nama, [cells])], kab_total_cells|None)"""
    page = clean_page(page)
    edges = col_edges(page)
    if not edges:
        return [], None
    chars = page.chars
    anchors = []
    for ln in cluster_lines(chars, tol=2.0):
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


def _norm_label(s):
    return (s.replace("\u2013", "-").replace("\u2014", "-")
             .replace("û", "-").replace("Γ", "").strip())


def detect_headers(page, edges):
    """Ambil teks header tiap kolom (baris di atas '(1)(2)..'). -> list len = jml kolom."""
    page = clean_page(page)
    lines = cluster_lines(page.chars, 3.0)
    colnum_top = None
    for ln in lines:
        t = "".join(c["text"] for c in ln["chars"])
        if re.match(r"\s*\(1\)", t):
            colnum_top = ln["top"]
            break
    n = len(edges) - 1
    cols = [""] * n
    if colnum_top is None:
        return cols
    for ln in lines:
        if not (110 < ln["top"] < colnum_top):
            continue
        for i, part in enumerate(row_to_cols(ln, edges)):
            if part and i < n:
                cols[i] = (cols[i] + " " + part).strip()
    return [_norm_label(c) for c in cols]


def extract_page_rows_kategori(page):
    """Baris generik (kategori): label di kolom-0, nilai di kolom lain. -> (rows, kab)."""
    page = clean_page(page)
    edges = col_edges(page)
    if not edges:
        return [], None
    lines = cluster_lines(page.chars, 3.5)
    rtop, rbot = 130, 9999
    for ln in lines:
        t = "".join(c["text"] for c in ln["chars"])
        if re.match(r"\s*\(1\)", t):
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
        if has_val:
            use = label if re.search(r"[A-Za-z0-9]", label) else pending
            if is_kab_total(use):
                kab = cols
            else:
                rows.append((use, cols))
            pending = ""
        elif re.search(r"[A-Za-z]", label):
            pending = label
    return rows, kab


def ekstrak(pdf_path, hal_awal, hal_akhir, mode="kecamatan"):
    """
    -> {n_kolom, rows, total, headers:[...], label_kolom}
    mode: 'kecamatan' (anchor master) atau 'kategori' (baris generik).
    """
    gabung, urutan, total_cells = {}, [], None
    headers, label_kolom = None, ""
    with pdfplumber.open(pdf_path) as pdf:
        for pno in range(hal_awal, hal_akhir + 1):
            if pno < 1 or pno > len(pdf.pages):
                continue
            page = pdf.pages[pno - 1]
            if headers is None:
                edges = col_edges(clean_page(page))
                if edges:
                    allh = detect_headers(page, edges)
                    label_kolom = allh[0] if allh else ""
                    headers = allh[1:]
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

    n_kolom = max((len(v) for v in gabung.values()), default=0)

    def buat_sel(cells):
        out = []
        for raw in cells:
            num, teks, flag = clean_num(raw)
            out.append({"teks": teks, "num": num, "flag": flag})
        return out

    hasil_rows = [{"wilayah": n, "sel": buat_sel(gabung[n])} for n in urutan]
    total = {"wilayah": "Kabupaten Tasikmalaya", "sel": buat_sel(total_cells)} if total_cells else None

    headers = (headers or [])[:n_kolom] + [""] * max(0, n_kolom - len(headers or []))
    return {"n_kolom": n_kolom, "rows": hasil_rows, "total": total,
            "headers": headers, "label_kolom": label_kolom}

