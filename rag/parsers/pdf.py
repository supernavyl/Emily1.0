"""PDF parser using PyMuPDF (fitz) with OCR fallback."""

from __future__ import annotations

from pathlib import Path


def parse(path: str) -> str:
    """
    Extract text from a PDF file.

    Uses PyMuPDF (fitz) for text extraction. Falls back to Tesseract OCR
    for scanned PDFs (pages with very little text).

    Args:
        path: Path to the PDF file.

    Returns:
        Extracted plain text content.
    """
    try:
        import fitz  # type: ignore[import-untyped]  # PyMuPDF

        doc = fitz.open(path)
        pages: list[str] = []
        for page in doc:
            text = page.get_text().strip()
            if not text or len(text) < 20:
                # Scanned page — try OCR
                text = _ocr_page(page)
            pages.append(text)
        doc.close()
        return "\n\n".join(pages)
    except ImportError:
        return _fallback_read(path)
    except Exception as exc:
        return f"[PDF parse error: {exc}]"


def _ocr_page(page: object) -> str:
    """Run Tesseract OCR on a page rendered as an image."""
    try:
        import fitz

        mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR quality
        pix = page.get_pixmap(matrix=mat)  # type: ignore[union-attr]
        img_bytes = pix.tobytes("png")
        return _tesseract_ocr(img_bytes)
    except Exception:
        return ""


def _tesseract_ocr(img_bytes: bytes) -> str:
    """Run Tesseract OCR on image bytes."""
    try:
        import io

        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img)
    except ImportError:
        return "[OCR not available: install pytesseract and tesseract]"


def _fallback_read(path: str) -> str:
    """Fallback: try to read the file as binary and extract ASCII text."""
    try:
        raw = Path(path).read_bytes()
        # Very crude text extraction from PDF binary
        text = raw.decode("latin-1", errors="ignore")
        import re

        text = re.sub(r"[^\x20-\x7E\n]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text[:50000]
    except Exception as exc:
        return f"[PDF fallback failed: {exc}]"
