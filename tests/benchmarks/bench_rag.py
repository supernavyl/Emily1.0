"""
RAG pipeline benchmark suite.

Measures:
- Ingestion throughput (documents/second)
- Retrieval latency (dense + sparse + hybrid)
- Retrieval quality (relevance scores)
- Reranker latency
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

SAMPLE_DOCUMENTS = [
    "Python is a high-level, interpreted programming language with dynamic semantics.",
    "FastAPI is a modern web framework for building APIs with Python.",
    "Qdrant is a vector similarity search engine with extended filtering support.",
    "Transformers are neural network architectures based on self-attention mechanisms.",
    "SQLite is a self-contained, serverless SQL database engine.",
]


@pytest.fixture
def tmp_text_file(tmp_path: Path) -> Path:
    """Create a temporary text file for ingestion tests."""
    doc_path = tmp_path / "test_doc.txt"
    doc_path.write_text("\n\n".join(SAMPLE_DOCUMENTS))
    return doc_path


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_chunker_throughput(tmp_text_file: Path) -> None:
    """Measure semantic chunker throughput."""
    try:
        from rag.chunker import SemanticChunker

        chunker = SemanticChunker()
        content = tmp_text_file.read_text()

        t0 = time.monotonic()
        chunks = chunker.chunk(content, source=str(tmp_text_file))
        elapsed_ms = (time.monotonic() - t0) * 1000

        print(
            f"\n[chunker] content_len={len(content)} chunks={len(chunks)} elapsed={elapsed_ms:.1f}ms"
        )

        assert len(chunks) > 0, "Chunker produced no chunks"
        assert elapsed_ms < 500, f"Chunker too slow: {elapsed_ms:.0f}ms"

    except ImportError as e:
        pytest.skip(f"Import error: {e}")


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_bm25_retrieval_latency() -> None:
    """Measure BM25 retrieval latency."""
    try:
        from memory.semantic.bm25 import BM25Index

        index = BM25Index(index_dir=Path("data/test_bm25_bench"))
        index.add_documents(
            [{"id": str(i), "content": doc} for i, doc in enumerate(SAMPLE_DOCUMENTS)]
        )

        query = "Python programming language features"
        N_QUERIES = 50

        t0 = time.monotonic()
        for _ in range(N_QUERIES):
            results = index.search(query, top_k=5)
        elapsed_ms = (time.monotonic() - t0) * 1000

        per_query_ms = elapsed_ms / N_QUERIES
        print(f"\n[bm25] queries={N_QUERIES} per_query={per_query_ms:.2f}ms results={len(results)}")

        assert per_query_ms < 10.0, f"BM25 retrieval too slow: {per_query_ms:.2f}ms/query"

    except ImportError as e:
        pytest.skip(f"Import error: {e}")
    finally:
        import shutil

        shutil.rmtree("data/test_bm25_bench", ignore_errors=True)
