import pdfplumber

def test():
    p = pdfplumber.open('../kabupaten-tasikmalaya-dalam-angka-2025.pdf').pages[52]
    tbl_top = 121.88
    colnum_top = 156
    
    # 1. Edges
    from webapp.apps.ekstraksi.engine import clean_page, col_edges
    cpage = clean_page(p)
    edges = col_edges(cpage)
    n = len(edges) - 1
    
    # 2. Hlines
    hlines = [l for l in p.lines if tbl_top - 4 <= l['top'] <= colnum_top and l['width'] > 10]
    hlines.sort(key=lambda l: (l['top'], l['x0']))
    merged_hl = []
    if hlines:
        curr = {"x0": hlines[0]["x0"], "x1": hlines[0]["x1"], "top": hlines[0]["top"]}
        for l in hlines[1:]:
            if abs(l["top"] - curr["top"]) < 2 and l["x0"] - curr["x1"] < 1.0:
                curr["x1"] = max(curr["x1"], l["x1"])
            else:
                merged_hl.append(curr)
                curr = {"x0": l["x0"], "x1": l["x1"], "top": l["top"]}
        merged_hl.append(curr)

    # 3. Blk
    words = cpage.extract_words()
    id_words = [w for w in words if (tbl_top - 4 < w["top"] < colnum_top - 1)]
    
    # Let's mock a merged block "Tepi Laut"
    tepi = [w for w in id_words if w['text'] in ('Tepi', 'Laut') and w['x0'] < 250]
    blk = {"text": "Tepi Laut", "x0": tepi[0]["x0"], "x1": tepi[1]["x1"], "bottom": tepi[1]["bottom"]}
    
    print("Blk:", blk)
    print("Merged HL:", merged_hl)
    
    # 4. Assign
    target_cols = []
    matched_hl = None
    for hl in merged_hl:
        if 0 < hl["top"] - blk["bottom"] < 20 and blk["x0"] >= hl["x0"] - 10 and blk["x1"] <= hl["x1"] + 10:
            matched_hl = hl
            break
            
    if matched_hl:
        print("Matched HL:", matched_hl)
        for i in range(n):
            col_x0 = edges[i]
            col_x1 = edges[i+1]
            # Column center falls within the HL
            if matched_hl["x0"] - 5 <= (col_x0 + col_x1)/2 <= matched_hl["x1"] + 5:
                target_cols.append(i)
    else:
        print("No matched HL")
        for i in range(n):
            col_x0 = edges[i]
            col_x1 = edges[i+1]
            if (col_x0 <= (blk["x0"] + blk["x1"])/2 < col_x1):
                target_cols.append(i)
                
    print("Target cols for 'Tepi Laut':", target_cols)

if __name__ == "__main__":
    test()
