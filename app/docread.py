"""Read a tender book or brief into clean text, in Arabic or English: text, DOCX, PDF with a text layer,
and scans or photos through OCR (Tesseract, when installed on the server). Pure Python except OCR."""
import io
import re
import unicodedata
import zipfile
from collections import Counter

BIDI = re.compile("[‎‏‪-‮⁦-⁩﻿]")
TASHKEEL = re.compile("[ً-ٰٟـ]")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


class ReadError(Exception):
    pass


def clean(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)          # folds Arabic presentation forms (including lam-alef) back to letters
    s = BIDI.sub("", s)
    s = TASHKEEL.sub("", s)
    s = s.replace(" ", " ")
    return re.sub(r"[ \t]+", " ", s)


def _strip_repeating(pages: list[str]) -> list[str]:
    """Drop headers and footers that repeat on most pages (letterhead, page numbers, document number)."""
    if len(pages) < 5:
        return pages
    norm = lambda ln: re.sub(r"\d+", "#", ln.strip())
    cnt = Counter(norm(ln) for p in pages for ln in set(p.split("\n")) if ln.strip())
    cut = max(3, int(len(pages) * 0.4))
    drop = {k for k, v in cnt.items() if v >= cut and len(k) < 120}
    out = []
    for p in pages:
        out.append("\n".join(ln for ln in p.split("\n") if ln.strip() and norm(ln) not in drop))
    return out


def _ocr_image(img) -> str:
    try:
        import pytesseract
    except ImportError:
        raise ReadError("This looks like a scan or an image, and OCR is not installed on this server. Install Tesseract with the Arabic and English language data, or paste the text.")
    try:
        return pytesseract.image_to_string(img, lang="ara+eng")
    except Exception as e:
        raise ReadError(f"OCR failed ({type(e).__name__}). Check that Tesseract has the 'ara' and 'eng' language data.")


def _pdf(raw: bytes, warnings: list) -> tuple[list[str], str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ReadError("PDF reading is not available here. Paste the text, or upload a DOCX or TXT file.")
    try:
        r = PdfReader(io.BytesIO(raw))
        pages = [(p.extract_text() or "") for p in r.pages]
    except Exception as e:
        raise ReadError(f"Could not read this PDF ({type(e).__name__})")
    pages = [clean(p) for p in pages]
    empty = [i for i, p in enumerate(pages) if len(p.strip()) < 40]
    method = "pdf-text"
    if empty and len(empty) >= max(1, len(pages) // 4):          # mostly scanned: OCR the pages with no text layer
        try:
            from pdf2image import convert_from_bytes
        except ImportError:
            raise ReadError("This PDF is mostly scanned pages and OCR (pdf2image) is not installed on this server. Paste the text instead.")
        for i in empty:
            imgs = convert_from_bytes(raw, dpi=200, first_page=i + 1, last_page=i + 1)
            pages[i] = clean(_ocr_image(imgs[0]))
        method = "pdf-ocr"
        warnings.append(f"{len(empty)} page(s) had no text layer and were read by OCR; check the extracted items against the original")
    return pages, method


def _docx(raw: bytes) -> list[str]:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        xml = z.read("word/document.xml").decode("utf8")
    except Exception:
        raise ReadError("Could not read this DOCX file")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    lines = []
    for p in paras:
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, flags=re.S))
        t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))
        lines.append(t)
    return [clean("\n".join(lines))]


def read_document(filename: str, raw: bytes) -> dict:
    """Returns {text, pages:[...], method, warnings}. Page breaks matter: items are traced back to a page."""
    name = filename.lower()
    warnings: list[str] = []
    if name.endswith((".txt", ".md")):
        txt = raw.decode("utf-8", errors="replace")
        pages, method = [clean(txt)], "text"
    elif name.endswith(".docx"):
        pages, method = _docx(raw), "docx"
    elif name.endswith(".pdf"):
        pages, method = _pdf(raw, warnings)
    elif name.endswith(IMAGE_EXT):
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw))
        except Exception:
            raise ReadError("Could not open this image")
        pages, method = [clean(_ocr_image(img))], "image-ocr"
        warnings.append("Read by OCR from an image; check the extracted items against the original")
    else:
        raise ReadError("Supported: PDF, DOCX, TXT, MD, PNG, JPG, TIFF")
    pages = _strip_repeating(pages)
    text = "\n".join(pages)
    if len(text.strip()) < 40:
        raise ReadError("Almost no text could be read from this file")
    return {"text": text, "pages": pages, "method": method, "warnings": warnings}
