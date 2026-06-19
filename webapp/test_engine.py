"""Tes ringan untuk fitur engine baru (borderless, OCR-page, klasifikasi)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from apps.ekstraksi import engine
from apps.ekstraksi import ocr

PDF = os.path.join(os.path.dirname(__file__), "..", "kabupaten-tasikmalaya-dalam-angka-2026.pdf")


def test_edges_from_gaps():
    # 3 kolom: 10-50, 100-140, 200-250 -> 2 gutter -> 4 edge
    items = []
    for x0, x1 in [(10, 50), (100, 140), (200, 250)]:
        items.append({"x0": x0, "x1": x1})
    edges = engine._edges_from_items(items, min_gap=7.0)
    assert edges is not None, "harus mendeteksi edge"
    assert len(edges) == 4, f"harus 4 edge, dapat {edges}"
    # gutter tengah ~ (50+100)/2=75 dan (140+200)/2=170
    assert any(70 < e < 80 for e in edges), edges
    assert any(165 < e < 175 for e in edges), edges
    print("OK test_edges_from_gaps:", edges)


def test_edges_terlalu_rapat():
    # kolom menempel tanpa gutter cukup -> None
    items = [{"x0": 10, "x1": 50}, {"x0": 52, "x1": 90}]
    edges = engine._edges_from_items(items, min_gap=7.0)
    assert edges is None, f"harusnya None, dapat {edges}"
    print("OK test_edges_terlalu_rapat")


def test_ocr_page_interface():
    words = [
        {"text": "Cipatujah", "x0": 50, "x1": 110, "top": 200, "bottom": 210},
        {"text": "241", "x0": 210, "x1": 240, "top": 200, "bottom": 210},
        {"text": "Salopa", "x0": 50, "x1": 100, "top": 220, "bottom": 230},
        {"text": "99", "x0": 215, "x1": 240, "top": 220, "bottom": 230},
    ]
    p = engine._OcrPage(words, page_number=5)
    assert p.page_number == 5
    assert len(p.chars) == sum(len(w["text"]) for w in words)
    assert "Cipatujah" in p.extract_text()
    edges = engine.col_edges(p)
    assert edges and len(edges) >= 3, f"borderless edges harus terdeteksi: {edges}"
    print("OK test_ocr_page_interface:", edges)


def test_klasifikasi_digital():
    if not os.path.exists(PDF):
        print("SKIP test_klasifikasi (PDF tak ada)")
        return
    j = ocr.klasifikasi_halaman(PDF, 46)
    assert j == "digital", f"hal 46 harus digital, dapat {j}"
    print("OK test_klasifikasi_digital")


def test_ocr_tak_tersedia_pesan():
    # tanpa tesseract, ekstrak 'paksa' harus tetap jalan & beri pesan
    if not os.path.exists(PDF):
        print("SKIP test_ocr_pesan")
        return
    if ocr.ocr_tersedia():
        print("SKIP (tesseract terpasang)")
        return
    d = engine.ekstrak_range(PDF, 46, 46, pakai_ocr="paksa")
    info = d[0]["info_ocr"] if d else None
    assert info is not None and not info["dipakai"], info
    assert "Tesseract" in info["pesan"]
    print("OK test_ocr_tak_tersedia_pesan")


def test_digital_regresi():
    if not os.path.exists(PDF):
        print("SKIP test_digital_regresi")
        return
    d = engine.ekstrak_range(PDF, 46, 51)
    nomor = [t["nomor"] for t in d]
    assert nomor == ["1.1.1", "1.1.2", "1.1.3"], nomor
    assert all(len(t["rows"]) == 39 for t in d), [len(t["rows"]) for t in d]
    print("OK test_digital_regresi:", nomor)


if __name__ == "__main__":
    test_edges_from_gaps()
    test_edges_terlalu_rapat()
    test_ocr_page_interface()
    test_klasifikasi_digital()
    test_ocr_tak_tersedia_pesan()
    test_digital_regresi()
    print("\nSEMUA TES LULUS")
