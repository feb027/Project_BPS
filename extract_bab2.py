"""
Ekstraktor BAB 2 - PEMERINTAHAN.
Menangani 2 pola tabel:
  - 'kecamatan' : baris = kecamatan (wilayah), kolom = tahun. (tabel 2.1.1)
  - 'kategori'  : baris = kategori bebas (partai/jabatan/...), wilayah = Kabupaten,
                  rincian = label baris, kolom = Laki/Perempuan/Jumlah. (2.2.1, 2.3.x)

Skema long diperluas: + kolom 'rincian' dan 'tahun'.
Reuse helper dari extract.py (col_edges, cluster_lines, clean_num, match_kec, ...).
"""
import pdfplumber, re, csv, os
import extract as E

PDF = E.PDF
OUT = os.path.join("output", "bab2_pemerintahan_long.csv")

# mode kolom: 'year' -> indikator tetap, tahun=col; 'kategori' -> indikator = base + label
BAB2 = {
    "2.1.1": dict(tipe="kecamatan", hal=[58, 59],
        judul="Jumlah Desa/Kelurahan Menurut Kecamatan 2021-2025",
        base="Jumlah Desa/Kelurahan", satuan="desa/kel", mode="year",
        kolom=[("2021", 2021), ("2022", 2022), ("2023", 2023), ("2024", 2024), ("2025", 2025)]),
    "2.2.1": dict(tipe="kategori", hal=[60], rincian_dim="Partai Politik",
        judul="Jumlah Anggota DPRD Menurut Partai Politik dan Jenis Kelamin, 2025",
        base="Anggota DPRD", satuan="orang", mode="kategori",
        kolom=[("Laki-laki", 2025), ("Perempuan", 2025), ("Jumlah", 2025)]),
    "2.3.1": dict(tipe="kategori", hal=[61], rincian_dim="Jabatan",
        judul="Jumlah PNS Menurut Jabatan dan Jenis Kelamin, 2025",
        base="Jumlah PNS", satuan="orang", mode="kategori",
        kolom=[("Laki-laki", 2025), ("Perempuan", 2025), ("Jumlah", 2025)]),
    "2.3.2": dict(tipe="kategori", hal=[62], rincian_dim="Tingkat Pendidikan",
        judul="Jumlah PNS Menurut Tingkat Pendidikan dan Jenis Kelamin, 2025",
        base="Jumlah PNS", satuan="orang", mode="kategori",
        kolom=[("Laki-laki", 2025), ("Perempuan", 2025), ("Jumlah", 2025)]),
    "2.3.3": dict(tipe="kategori", hal=[63], rincian_dim="Tingkat Kepangkatan",
        judul="Jumlah PNS Menurut Tingkat Kepangkatan dan Jenis Kelamin, 2025",
        base="Jumlah PNS", satuan="orang", mode="kategori",
        kolom=[("Laki-laki", 2025), ("Perempuan", 2025), ("Jumlah", 2025)]),
    "2.4.1": dict(tipe="kategori", hal=[64, 65, 66], rincian_dim="Jenis Pendapatan/Belanja",
        judul="Realisasi Keuangan Pemerintah Kabupaten Tasikmalaya Menurut Jenis (ribu rupiah), 2024-2025",
        base="Realisasi Keuangan Pemerintah", satuan="ribu rupiah", mode="year", keep_code=True,
        kolom=[("2024", 2024), ("2025", 2025)]),
}


def region_bounds(lines, edges):
    """Cari batas atas (setelah baris '(1)(2)..') dan bawah (sebelum Catatan/Sumber)."""
    top, bot = None, None
    for ln in lines:
        txt = "".join(c["text"] for c in ln["chars"])
        if top is None and re.match(r"\s*\(1\)", txt):
            top = ln["top"] + 4
        if re.search(r"Catatan/|Sumber/|Note\s*:|Source\s*:", txt):
            bot = ln["top"] - 2; break
    return (top or 150), (bot or 540)


def cols_of(chars_in_band, edges):
    cols = [""] * (len(edges) - 1)
    for c in sorted(chars_in_band, key=lambda c: c["x0"]):
        cx = (c["x0"] + c["x1"]) / 2
        for j in range(len(edges) - 1):
            if edges[j] <= cx < edges[j + 1]:
                cols[j] += c["text"]; break
    return [re.sub(r"\s+", " ", x).strip() for x in cols]


def has_value(cols):
    return any(re.search(r"\d", c) or c.strip() in ("-", "–", "—") for c in cols[1:])


def extract_kategori(page, cfg):
    """Baris kategori: gabung label multi-baris (Indo/English) + baris-nilai."""
    page = E.clean_page(page)        # buang watermark dulu
    edges = E.col_edges(page)
    if not edges:
        return [], ""
    lines = E.cluster_lines(page.chars, tol=3.0)
    rtop, rbot = region_bounds(lines, edges)
    sumber = ""
    txt_all = page.extract_text() or ""
    m = re.search(r"Sumber/Source\s*:\s*(.+)", txt_all)
    if m: sumber = m.group(1).strip()

    rows = []          # (rincian_label, cols)
    pending_label = ""
    keep_code = cfg.get("keep_code", False)
    for ln in lines:
        if not (rtop <= ln["top"] <= rbot):
            continue
        cols = cols_of(ln["chars"], edges)
        if keep_code:
            label = cols[0].strip()
        else:
            label = re.sub(r"^\s*[\d.]+\s*", "", cols[0]).strip()
        if has_value(cols):
            # baris-nilai. label = col0 jika ada, kalau kosong pakai pending
            use = label if re.search(r"[A-Za-z]", label) else pending_label
            rows.append((use, cols))
            pending_label = ""
        else:
            # baris label saja (mis. judul Indo sebelum baris '- - -', atau wrap English)
            if re.search(r"[A-Za-z]", label) and not re.match(r"^[A-Z][a-z]+ (Executives|Position|Revenue)", label):
                pending_label = label
    return rows, sumber


def emit(nomor, cfg, w, flags):
    base, mode, satuan = cfg["base"], cfg["mode"], cfg["satuan"]
    n_rows = 0
    with pdfplumber.open(PDF) as pdf:
        if cfg["tipe"] == "kecamatan":
            allrows, kab, sumber = [], None, ""
            for pno in cfg["hal"]:
                page = pdf.pages[pno - 1]
                m = re.search(r"Sumber/Source\s*:\s*(.+)", page.extract_text() or "")
                if m: sumber = m.group(1).strip()
                pr, pk = E.extract_page_rows(page)
                allrows += pr
                if pk: kab = pk
            for wilayah, cols in allrows:
                for i, (lbl, th) in enumerate(cfg["kolom"]):
                    val, teks, fl = E.clean_num(cols[i + 1] if i + 1 < len(cols) else "")
                    w.writerow(["Pemerintahan", nomor, cfg["judul"], wilayah, "",
                                base, satuan, th, "" if val is None else val, teks, fl, sumber])
                    flags[fl] += 1
                n_rows += 1
        else:  # kategori
            sumber = ""
            for pno in cfg["hal"]:
                page = pdf.pages[pno - 1]
                rows, s = extract_kategori(page, cfg)
                if s: sumber = s
                for rincian, cols in rows:
                    if not rincian.strip():      # buang baris berlabel kosong (phantom)
                        continue
                    for i, (lbl, th) in enumerate(cfg["kolom"]):
                        val, teks, fl = E.clean_num(cols[i + 1] if i + 1 < len(cols) else "")
                        ind = base if mode == "year" else f"{base} - {lbl}"
                        w.writerow(["Pemerintahan", nomor, cfg["judul"], "Kabupaten Tasikmalaya",
                                    rincian, ind, satuan, th, "" if val is None else val, teks, fl, sumber])
                        flags[fl] += 1
                    n_rows += 1
    return n_rows


def main():
    os.makedirs("output", exist_ok=True)
    from collections import Counter
    flags = Counter()
    print("=== EKSTRAKSI BAB 2 - PEMERINTAHAN ===\n")
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["bab","nomor_tabel","judul_tabel","wilayah","rincian","indikator",
                    "satuan","tahun","nilai_num","nilai_teks","flag","sumber"])
        for nomor, cfg in BAB2.items():
            n = emit(nomor, cfg, w, flags)
            print(f"Tabel {nomor} ({cfg['tipe']:9}): {n} baris-data")
    print(f"\n=== RINGKASAN FLAG ({sum(flags.values())} sel) ===")
    for fl, n in flags.most_common():
        print(f"  {fl:16}: {n}")
    print(f"\nOutput: {OUT}")


if __name__ == "__main__":
    main()
