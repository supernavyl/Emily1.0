"""EPUB parser using ebooklib."""

from __future__ import annotations

import re


def parse(path: str) -> str:
    """
    Extract text from an EPUB ebook.

    Args:
        path: Path to the .epub file.

    Returns:
        Extracted plain text.
    """
    try:
        import ebooklib  # type: ignore[import-untyped]
        from ebooklib import epub

        book = epub.read_epub(path, options={"ignore_ncx": True})
        texts: list[str] = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            html = item.get_content().decode("utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                texts.append(text)
        return "\n\n".join(texts)
    except ImportError:
        return "[ebooklib not installed. Run: pip install ebooklib]"
    except Exception as exc:
        return f"[EPUB parse error: {exc}]"
