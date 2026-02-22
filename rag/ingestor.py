"""
Document ingestion pipeline for Emily's RAG system.

Supports multiple file formats and orchestrates the full ingestion pipeline:
  File → Parser → Chunker → Deduplicator → Embedder → Vector Store

All formats are handled by format-specific parsers in rag/parsers/.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any

from config import RAGConfig
from observability.logger import get_logger
from observability.metrics import RAG_DOCUMENTS_INGESTED
from rag.chunker import Chunk, SemanticChunker

log = get_logger(__name__)

_PARSER_MAP = {
    ".pdf": "rag.parsers.pdf",
    ".docx": "rag.parsers.docx",
    ".doc": "rag.parsers.docx",
    ".epub": "rag.parsers.epub",
    ".md": "rag.parsers.text",
    ".txt": "rag.parsers.text",
    ".html": "rag.parsers.text",
    ".htm": "rag.parsers.text",
    ".py": "rag.parsers.code",
    ".js": "rag.parsers.code",
    ".ts": "rag.parsers.code",
    ".rs": "rag.parsers.code",
    ".go": "rag.parsers.code",
    ".java": "rag.parsers.code",
    ".ipynb": "rag.parsers.code",
    ".csv": "rag.parsers.text",
    ".json": "rag.parsers.text",
    ".yaml": "rag.parsers.text",
    ".yml": "rag.parsers.text",
    ".mp3": "rag.parsers.audio",
    ".wav": "rag.parsers.audio",
    ".m4a": "rag.parsers.audio",
    ".mp4": "rag.parsers.video",
    ".mkv": "rag.parsers.video",
    ".pptx": "rag.parsers.text",
}


class IngestionResult:
    """Result of a document ingestion operation."""

    def __init__(self, path: str, chunks: list[Chunk], error: str | None = None) -> None:
        self.path = path
        self.chunks = chunks
        self.error = error
        self.success = error is None

    @property
    def n_chunks(self) -> int:
        return len(self.chunks)


class DocumentIngestor:
    """
    Orchestrates the full document ingestion pipeline.

    Documents are parsed, chunked, deduplicated, and stored in the vector DB.
    Already-ingested documents (by content hash) are skipped.
    """

    def __init__(
        self,
        config: RAGConfig,
        vector_store: Any | None = None,
    ) -> None:
        """
        Args:
            config: RAG configuration.
            vector_store: Optional vector store for writing embeddings.
                          If None, chunks are returned but not stored.
        """
        self._config = config
        self._vector_store = vector_store
        self._chunker = SemanticChunker(
            child_size=config.chunk_size_child,
            parent_size=config.chunk_size_parent,
            overlap=config.chunk_overlap,
        )
        self._ingested_hashes: set[str] = set()

    async def ingest_file(self, path: str | Path) -> IngestionResult:
        """
        Ingest a single file through the full pipeline.

        Args:
            path: Path to the file to ingest.

        Returns:
            IngestionResult with chunks and status.
        """
        p = Path(path)
        if not p.exists():
            return IngestionResult(str(path), [], error=f"File not found: {path}")

        suffix = p.suffix.lower()
        if suffix not in _PARSER_MAP:
            return IngestionResult(str(path), [], error=f"Unsupported format: {suffix}")

        # Deduplication check
        file_hash = self._hash_file(p)
        if file_hash in self._ingested_hashes:
            log.info("rag_skip_duplicate", path=str(p))
            return IngestionResult(str(path), [], error=None)

        log.info("rag_ingesting", path=str(p), suffix=suffix)
        t0 = time.monotonic()

        try:
            text = await self._parse(p, suffix)
            if not text.strip():
                return IngestionResult(str(path), [], error="Empty document after parsing")

            chunks = self._chunker.chunk(
                text,
                source=p.name,
                metadata={"source_path": str(p), "file_type": suffix, "ingested_at": time.time()},
            )

            # Store embeddings if vector store is available
            if self._vector_store and chunks:
                await self._store_chunks(chunks)

            self._ingested_hashes.add(file_hash)
            elapsed = (time.monotonic() - t0) * 1000
            RAG_DOCUMENTS_INGESTED.labels(file_type=suffix).inc()
            log.info(
                "rag_ingested",
                path=str(p),
                n_chunks=len(chunks),
                elapsed_ms=f"{elapsed:.0f}",
            )
            return IngestionResult(str(path), chunks)

        except Exception as exc:
            log.error("rag_ingestion_error", path=str(p), error=str(exc))
            return IngestionResult(str(path), [], error=str(exc))

    async def ingest_directory(self, dir_path: str | Path) -> list[IngestionResult]:
        """
        Ingest all supported files in a directory (non-recursive by default).

        Args:
            dir_path: Directory to scan.

        Returns:
            List of IngestionResult objects.
        """
        d = Path(dir_path)
        if not d.is_dir():
            return []

        tasks = [
            self.ingest_file(f)
            for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in _PARSER_MAP
        ]
        return list(await asyncio.gather(*tasks))

    async def _parse(self, path: Path, suffix: str) -> str:
        """
        Parse a file to plain text using the appropriate parser.

        Args:
            path: File path.
            suffix: File extension.

        Returns:
            Extracted plain text.
        """
        # Import the parser module dynamically
        module_path = _PARSER_MAP[suffix]
        try:
            import importlib
            module = importlib.import_module(module_path)
            parse_fn = getattr(module, "parse")
            return await asyncio.to_thread(parse_fn, str(path))
        except (ImportError, AttributeError):
            # Fallback: read as plain text
            return await asyncio.to_thread(self._read_text, path)

    @staticmethod
    def _read_text(path: Path) -> str:
        """Read a file as plain UTF-8 text with error replacement."""
        return path.read_text(encoding="utf-8", errors="replace")

    async def _store_chunks(self, chunks: list[Chunk]) -> None:
        """Store chunk embeddings in the vector store."""
        if self._vector_store is None:
            return
        child_chunks = [c for c in chunks if not c.is_parent]
        await self._vector_store.upsert_chunks(child_chunks)

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Compute SHA256 of file contents for deduplication."""
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()
