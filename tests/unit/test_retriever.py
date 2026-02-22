"""Unit tests for memory.semantic.retriever."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from memory.semantic.retriever import HybridRetriever, _reciprocal_rank_fusion


def test_rrf_fusion_basic():
    list_a = [{"chunk_id": "a", "score": 1.0}, {"chunk_id": "b", "score": 0.5}]
    list_b = [{"chunk_id": "b", "score": 1.0}, {"chunk_id": "c", "score": 0.5}]
    fused = _reciprocal_rank_fusion([list_a, list_b], k=60)
    ids = [item["chunk_id"] for item in fused]
    # "b" appears in both lists so should have highest RRF score
    assert ids[0] == "b"
    assert len(fused) == 3


def test_rrf_fusion_single_list():
    items = [{"chunk_id": "x"}, {"chunk_id": "y"}, {"chunk_id": "z"}]
    fused = _reciprocal_rank_fusion([items])
    assert len(fused) == 3
    assert fused[0]["chunk_id"] == "x"


def test_rrf_fusion_empty():
    fused = _reciprocal_rank_fusion([[], []])
    assert fused == []


@pytest.mark.asyncio
async def test_retrieve_without_reranker():
    config = MagicMock()
    config.final_top_k = 2
    config.rerank_top_k = 10

    vector_store = AsyncMock()
    vector_store.search.return_value = [
        {"chunk_id": "d1", "score": 0.9, "content": "doc1"},
        {"chunk_id": "d2", "score": 0.7, "content": "doc2"},
    ]
    vector_store.get_by_id.return_value = None

    bm25 = MagicMock()
    bm25.search.return_value = [
        {"chunk_id": "d1", "bm25_score": 2.0, "content": "doc1"},
    ]

    async def fake_embed(text: str) -> list[float]:
        return [0.1] * 1024

    retriever = HybridRetriever(config, vector_store, bm25, fake_embed)
    results = await retriever.retrieve("test query")
    assert len(results) <= 2
    assert all("chunk_id" in r for r in results)


@pytest.mark.asyncio
async def test_retrieve_with_reranker():
    config = MagicMock()
    config.final_top_k = 2
    config.rerank_top_k = 10

    vector_store = AsyncMock()
    vector_store.search.return_value = [
        {"chunk_id": "d1", "score": 0.9, "content": "doc1"},
    ]
    vector_store.get_by_id.return_value = None

    bm25 = MagicMock()
    bm25.search.return_value = [
        {"chunk_id": "d1", "bm25_score": 2.0, "content": "doc1"},
    ]

    reranker = AsyncMock()
    reranker.rerank.return_value = [{"chunk_id": "d1", "score": 0.95}]

    async def fake_embed(text: str) -> list[float]:
        return [0.1] * 1024

    retriever = HybridRetriever(config, vector_store, bm25, fake_embed, reranker=reranker)
    results = await retriever.retrieve("test")
    reranker.rerank.assert_awaited_once()
    assert len(results) == 1
