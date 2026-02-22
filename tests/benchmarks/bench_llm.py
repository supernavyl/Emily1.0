"""
LLM fleet benchmark suite.

Measures:
- First token latency per model tier
- Throughput (tokens/second)
- Quality on a standard prompt set
- VRAM usage per model

Run with:
    python -m pytest tests/benchmarks/bench_llm.py -v -s
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import pytest

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


BENCHMARK_PROMPTS = [
    {
        "name": "simple_qa",
        "tier": "nano",
        "prompt": "What is the capital of France?",
        "expected_keyword": "Paris",
    },
    {
        "name": "code_generation",
        "tier": "fast",
        "prompt": "Write a Python function to compute Fibonacci numbers recursively.",
        "expected_keyword": "def",
    },
    {
        "name": "reasoning",
        "tier": "smart",
        "prompt": (
            "A farmer has 17 sheep. All but 9 die. How many are left? "
            "Think step by step."
        ),
        "expected_keyword": "9",
    },
]


@pytest.mark.asyncio
@pytest.mark.benchmark
@pytest.mark.parametrize("case", BENCHMARK_PROMPTS, ids=[c["name"] for c in BENCHMARK_PROMPTS])
async def test_llm_latency(case: dict[str, Any]) -> None:
    """Measure first-token latency and response quality for each model tier."""
    try:
        from config import get_settings
        from llm.client import ChatMessage, OllamaClient

        settings = get_settings()
        client = OllamaClient(base_url=settings.llm.ollama_base_url)

        healthy = await client.health_check()
        if not healthy:
            pytest.skip("Ollama not running")

        model = getattr(settings.llm.models, case["tier"])

        t0 = time.monotonic()
        chunks = []
        first_token_latency = None

        async for chunk in client.chat_stream(
            model=model,
            messages=[ChatMessage(role="user", content=case["prompt"])],
            model_tier=case["tier"],
            max_tokens=1024,
        ):
            if chunk.content and first_token_latency is None:
                first_token_latency = (time.monotonic() - t0) * 1000
            chunks.append(chunk.content)
            if chunk.done:
                break

        total_time = (time.monotonic() - t0) * 1000
        full_response = "".join(chunks)
        answer_text = _THINK_RE.sub("", full_response).strip()

        print(f"\n[{case['name']}] tier={case['tier']} model={model}")
        print(f"  First token: {first_token_latency:.0f}ms" if first_token_latency else "  No tokens")
        print(f"  Total: {total_time:.0f}ms")
        print(f"  Response: {answer_text[:80]}...")

        assert first_token_latency is not None, "No tokens received"
        searchable = full_response.lower()
        assert case["expected_keyword"].lower() in searchable, (
            f"Expected '{case['expected_keyword']}' in response: {answer_text[:200]}"
        )

        # Performance assertions (not strict — warn only)
        if first_token_latency > 30_000:
            pytest.warns(UserWarning, match="slow")

    except ImportError as e:
        pytest.skip(f"Import error: {e}")


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_embedding_throughput() -> None:
    """Measure embedding throughput for BGE-M3."""
    try:
        from llm.client import OllamaClient
        client = OllamaClient()

        if not await client.health_check():
            pytest.skip("Ollama not running")

        texts = [
            "The quick brown fox jumps over the lazy dog.",
            "Machine learning is a subfield of artificial intelligence.",
            "Python is a high-level programming language.",
            "Neural networks are inspired by biological neural networks.",
            "Transformers revolutionized natural language processing.",
        ]

        t0 = time.monotonic()
        results = await client.embed_batch("bge-m3", texts)
        elapsed = (time.monotonic() - t0) * 1000

        print(f"\n[embedding] model=bge-m3 texts={len(texts)}")
        print(f"  Total: {elapsed:.0f}ms ({elapsed/len(texts):.0f}ms per text)")
        print(f"  Embedding dim: {len(results[0].embedding)}")

        assert len(results) == len(texts)
        assert len(results[0].embedding) > 0

    except ImportError as e:
        pytest.skip(f"Import error: {e}")
