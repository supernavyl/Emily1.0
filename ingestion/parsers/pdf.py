"""
PDF parser — extracts text from PDF documents for knowledge ingestion.

Uses pymupdf (already installed as `fitz`) to extract page text.
Returns a ParsedDocument with the full text and per-page breakdown.
The text is then fed to the ExtractionPipeline for entity extraction.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class ParsedDocument:
    """Text extracted from a document file."""

    source_path: str = ""
    title: str = ""
    full_text: str = ""
    page_texts: list[str] = field(default_factory=list)
    page_count: int = 0
    metadata: dict = field(default_factory=dict)


async def parse_pdf(path: Path) -> ParsedDocument:
    """
    Extract text from a PDF file asynchronously.

    Args:
        path: Path to the PDF file.

    Returns:
        ParsedDocument with extracted text.
    """
    return await asyncio.to_thread(_parse_pdf_sync, path)


def _parse_pdf_sync(path: Path) -> ParsedDocument:
    """
    Synchronous PDF text extraction using pymupdf.

    Args:
        path: Path to the PDF file.

    Returns:
        ParsedDocument.
    """
    doc = ParsedDocument(source_path=str(path), title=path.stem)

    try:
        import fitz  # pymupdf

        pdf = fitz.open(str(path))
        doc.page_count = len(pdf)

        pages = []
        for page in pdf:
            text = page.get_text("text")
            pages.append(text)

        doc.page_texts = pages
        doc.full_text = "\n\n".join(pages)

        # Extract metadata
        meta = pdf.metadata or {}
        doc.metadata = {k: str(v) for k, v in meta.items() if v}
        if meta.get("title"):
            doc.title = str(meta["title"])

        pdf.close()
        log.info("pdf_parsed", path=str(path), pages=doc.page_count)

    except Exception as exc:
        log.error("pdf_parse_error", path=str(path), error=str(exc))

    return doc


async def parse_text_file(path: Path) -> ParsedDocument:
    """
    Read a plain text file as a ParsedDocument.

    Args:
        path: Path to the text file.

    Returns:
        ParsedDocument with the file contents.
    """
    try:
        text = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
        return ParsedDocument(
            source_path=str(path),
            title=path.stem,
            full_text=text,
            page_texts=[text],
            page_count=1,
        )
    except Exception as exc:
        log.error("text_file_parse_error", path=str(path), error=str(exc))
        return ParsedDocument(source_path=str(path))
