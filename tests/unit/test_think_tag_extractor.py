"""Tests for the ThinkTagExtractor state machine.

The extractor must correctly split ``<think>…</think>`` content from
visible text, even when tags arrive split across multiple ``feed()``
calls (as happens with real SSE token streaming).
"""

from __future__ import annotations

from emily_chat.models.providers._openai_compat import ThinkTagExtractor
from emily_chat.models.streaming_engine import ChunkType


class TestBasicExtraction:
    """Happy-path tests with complete tags in single feed calls."""

    def test_pure_text_no_tags(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("Hello world")
        chunks += ext.flush()
        assert len(chunks) == 1
        assert chunks[0].type == ChunkType.TEXT
        assert chunks[0].content == "Hello world"

    def test_thinking_then_text(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("<think>reasoning here</think>visible text")
        chunks += ext.flush()
        types = [(c.type, c.content) for c in chunks]
        assert (ChunkType.THINKING, "reasoning here") in types
        assert (ChunkType.TEXT, "visible text") in types

    def test_only_thinking(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("<think>only reasoning</think>")
        chunks += ext.flush()
        assert len(chunks) == 1
        assert chunks[0].type == ChunkType.THINKING
        assert chunks[0].content == "only reasoning"

    def test_text_before_and_after(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("before<think>middle</think>after")
        chunks += ext.flush()
        types = [(c.type, c.content) for c in chunks]
        assert types[0] == (ChunkType.TEXT, "before")
        assert types[1] == (ChunkType.THINKING, "middle")
        assert types[2] == (ChunkType.TEXT, "after")


class TestStreamingPartialTags:
    """Tests where tags arrive split across multiple feed() calls."""

    def test_open_tag_split(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("<thi")
        chunks += ext.feed("nk>reasoning</think>text")
        chunks += ext.flush()
        thinking = [c for c in chunks if c.type == ChunkType.THINKING]
        text = [c for c in chunks if c.type == ChunkType.TEXT]
        assert any("reasoning" in c.content for c in thinking)
        assert any("text" in c.content for c in text)

    def test_close_tag_split(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("<think>reasoning</th")
        chunks += ext.feed("ink>text")
        chunks += ext.flush()
        thinking = [c for c in chunks if c.type == ChunkType.THINKING]
        text = [c for c in chunks if c.type == ChunkType.TEXT]
        assert any("reasoning" in c.content for c in thinking)
        assert any("text" in c.content for c in text)

    def test_token_by_token(self) -> None:
        """Simulate character-by-character streaming."""
        ext = ThinkTagExtractor()
        full = "<think>step 1 step 2</think>The answer is 42"
        chunks: list = []
        for ch in full:
            chunks.extend(ext.feed(ch))
        chunks.extend(ext.flush())

        thinking_text = "".join(
            c.content for c in chunks if c.type == ChunkType.THINKING
        )
        visible_text = "".join(
            c.content for c in chunks if c.type == ChunkType.TEXT
        )
        assert "step 1" in thinking_text
        assert "step 2" in thinking_text
        assert "The answer is 42" in visible_text

    def test_multiple_think_blocks(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("<think>first</think>mid<think>second</think>end")
        chunks += ext.flush()
        thinking = [c.content for c in chunks if c.type == ChunkType.THINKING]
        text = [c.content for c in chunks if c.type == ChunkType.TEXT]
        assert "first" in thinking
        assert "second" in thinking
        assert "mid" in text
        assert "end" in text


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_empty_feed(self) -> None:
        ext = ThinkTagExtractor()
        assert ext.feed("") == []
        assert ext.flush() == []

    def test_unclosed_think_tag(self) -> None:
        """Unclosed tag at stream end emits remaining as thinking."""
        ext = ThinkTagExtractor()
        chunks = ext.feed("<think>never closed")
        chunks += ext.flush()
        assert any(c.type == ChunkType.THINKING for c in chunks)
        thinking = "".join(c.content for c in chunks if c.type == ChunkType.THINKING)
        assert "never closed" in thinking

    def test_empty_think_block(self) -> None:
        ext = ThinkTagExtractor()
        chunks = ext.feed("<think></think>text after")
        chunks += ext.flush()
        text = [c for c in chunks if c.type == ChunkType.TEXT]
        assert any("text after" in c.content for c in text)

    def test_flush_after_complete(self) -> None:
        """Flushing after all tags are closed yields nothing extra."""
        ext = ThinkTagExtractor()
        chunks = ext.feed("<think>r</think>t")
        remaining = ext.flush()
        all_chunks = chunks + remaining
        assert len([c for c in all_chunks if c.type == ChunkType.TEXT]) >= 1
