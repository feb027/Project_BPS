"""
Dukungan OCR untuk PDF hasil pemindaian (buku lama / pra-2000 tanpa lapisan teks).

Strategi:
- Klasifikasi halaman: 'digital' (ada teks ter-embed) vs 'scan' (gambar saja).
- Untuk halaman scan: render ke gambar resolusi tinggi (PyMuPDF), pra-proses
  (grayscale + threshold via OpenCV bila tersedia), lalu Tesseract OCR dengan
  data posisi kata (image_to_data) -> objek 'kata' kompatibel dengan engine.

Semua dependensi opsional. Bila Tesseract tidak terpasang, fungsi melempar
OcrTidakTersedia dengan pesan panduan, dan engine memberi tahu pengguna.
"""
from __future__ import annotations

import re

try:
    import fitz  # PyMuPDF
    _ADA_FITZ = True
except Exception:
    _ADA_FITZ = False

try:
    import pytesseract
    from PIL import Image
    _ADA_TESS = True
except Exception:
    _ADA_TESS = False

try:
    import cv2
    import numpy as np
    _ADA_CV = True
except Exception:
    _ADA_CV = False


class OcrTidakTersedia(RuntimeError):
    """Dilempar bila OCR diminta tapi dependensi/binary tidak tersedia."""


PESAN_INSTALL = (
    "OCR untuk PDF hasil scan butuh: (1) pustaka Python 'pytesseract' "
    "(`pip install pytesseract pillow`), dan (2) program Tesseract OCR. "
    "Di Windows, unduh installer dari "
    "https://github.com/UB-Mannheim/tesseract/wiki lalu pastikan tesseract.exe "
    "ada di PATH (atau set TESSERACT_CMD)."
)


def ocr_tersedia():
    """True bila pytesseract + binary Tesseract bisa dipakai."""
    if not _ADA_TESS:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def klasifikasi_halaman(pdf_path, pno, ambang_kata=8):
    """
    -> 'digital' | 'scan'
    Halaman dianggap 'scan' bila teks ter-embed sangat sedikit (di bawah ambang).
    """
    if not _ADA_FITZ:
        return "digital"
    try:
        doc = fitz.open(pdf_path)
        if pno < 1 or pno > doc.page_count:
            return "digital"
        page = doc[pno - 1]
        kata = page.get_text("words")
        n_teks = len([w for w in kata if re.search(r"\w", w[4])])
        doc.close()
        return "digital" if n_teks >= ambang_kata else "scan"
    except Exception:
        return "digital"


def _render(pdf_path, pno, dpi=300):
    if not _ADA_FITZ:
        raise OcrTidakTersedia("PyMuPDF (fitz) tidak tersedia untuk render halaman.")
    doc = fitz.open(pdf_path)
    page = doc[pno - 1]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY)
    import numpy as _np
    img = _np.frombuffer(pix.samples, dtype=_np.uint8).reshape(pix.height, pix.width)
    doc.close()
    return img, zoom


def _praproses(img):
    """Grayscale -> threshold adaptif (bila OpenCV ada) utk mempertajam OCR."""
    if not _ADA_CV:
        return img
    try:
        _, bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return bw
    except Exception:
        return img


def kata_ocr_halaman(pdf_path, pno, dpi=300):
    """
    OCR satu halaman -> (words, page_size)
    words: list dict {text, x0, x1, top, bottom} dalam koordinat PDF (point, 72dpi)
    Sehingga kompatibel dgn cluster_lines/row_to_cols milik engine.
    """
    if not ocr_tersedia():
        raise OcrTidakTersedia(PESAN_INSTALL)
    img, zoom = _render(pdf_path, pno, dpi=dpi)
    proc = _praproses(img)
    if _ADA_TESS:
        pil = Image.fromarray(proc)
        data = pytesseract.image_to_data(
            pil, lang="ind+eng", output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )
    else:
        raise OcrTidakTersedia(PESAN_INSTALL)

    words = []
    n = len(data["text"])
    for i in range(n):
        teks = (data["text"][i] or "").strip()
        if not teks:
            continue
        try:
            konf = float(data["conf"][i])
        except (ValueError, TypeError):
            konf = -1
        if konf >= 0 and konf < 30:  # buang kata sangat tidak yakin
            continue
        x = data["left"][i] / zoom
        y = data["top"][i] / zoom
        w = data["width"][i] / zoom
        h = data["height"][i] / zoom
        words.append({
            "text": teks, "x0": x, "x1": x + w,
            "top": y, "bottom": y + h, "conf": konf,
        })
    return words, None
