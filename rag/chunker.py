"""
Semantic chunker with parent-child architecture for Emily's RAG pipeline.

Architecture:
- Child chunks: 256 tokens (for precise retrieval)
- Parent chunks: 2048 tokens (returned to LLM for rich context)
- Semantic boundaries: sentence-level splitting, not arbitrary token windows
- Each child carries a reference to its parent chunk ID

This enables the "parent chunk promotion" strategy in retrieval:
  1. Dense/sparse search on child chunks (small → precise match)
  2. Return the parent chunk to the LLM (large → rich context)
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import tiktoken

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    """Count tokens in a text string."""
    return len(_TOKENIZER.encode(text))


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences for semantic chunking."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


@dataclass
class Chunk:
    """A single chunk of text from an ingested document."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    token_count: int = 0
    source: str = ""
    source_path: str = ""
    chunk_index: int = 0
    parent_id: str | None = None
    is_parent: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.token_count:
            self.token_count = _count_tokens(self.content)
        if not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()


class SemanticChunker:
    """
    Splits documents into semantic child/parent chunk pairs.

    Algorithm:
    1. Split document into sentences
    2. Accumulate sentences into parent chunks (~2048 tokens)
    3. Split each parent chunk into child chunks (~256 tokens)
    4. Link children to their parent via parent_id
    """

    def __init__(
        self,
        child_size: int = 256,
        parent_size: int = 2048,
        overlap: int = 32,
    ) -> None:
        """
        Args:
            child_size: Target token count for child chunks.
            parent_size: Target token count for parent chunks.
            overlap: Token overlap between consecutive chunks.
        """
        self.child_size = child_size
        self.parent_size = parent_size
        self.overlap = overlap

    def chunk(
        self, text: str, source: str = "", metadata: dict[str, Any] | None = None
    ) -> list[Chunk]:
        """
        Chunk a document into parent and child chunks.

        Args:
            text: Full document text.
            source: Human-readable source name (e.g., filename).
            metadata: Optional metadata to attach to all chunks.

        Returns:
            List of Chunk objects (parents followed by their children).
        """
        meta = metadata or {}
        sentences = _split_sentences(text)
        parents = self._build_parents(sentences, source, meta)
        children = []
        for parent in parents:
            children.extend(self._build_children(parent, source, meta))
        return parents + children

    def _build_parents(
        self,
        sentences: list[str],
        source: str,
        meta: dict[str, Any],
    ) -> list[Chunk]:
        """Build parent-sized chunks from sentence list."""
        parents: list[Chunk] = []
        current_sentences: list[str] = []
        current_tokens = 0
        chunk_index = 0

        for sentence in sentences:
            sent_tokens = _count_tokens(sentence)
            if current_tokens + sent_tokens > self.parent_size and current_sentences:
                content = " ".join(current_sentences)
                parents.append(
                    Chunk(
                        content=content,
                        source=source,
                        chunk_index=chunk_index,
                        is_parent=True,
                        metadata=meta.copy(),
                    )
                )
                # Overlap: keep last N tokens worth of sentences
                overlap_sentences = self._take_overlap(current_sentences)
                current_sentences = overlap_sentences + [sentence]
                current_tokens = sum(_count_tokens(s) for s in current_sentences)
                chunk_index += 1
            else:
                current_sentences.append(sentence)
                current_tokens += sent_tokens

        if current_sentences:
            content = " ".join(current_sentences)
            parents.append(
                Chunk(
                    content=content,
                    source=source,
                    chunk_index=chunk_index,
                    is_parent=True,
                    metadata=meta.copy(),
                )
            )

        return parents

    def _build_children(self, parent: Chunk, source: str, meta: dict[str, Any]) -> list[Chunk]:
        """Split a parent chunk into child-sized chunks."""
        sentences = _split_sentences(parent.content)
        children: list[Chunk] = []
        current_sentences: list[str] = []
        current_tokens = 0
        child_index = 0

        for sentence in sentences:
            sent_tokens = _count_tokens(sentence)
            if current_tokens + sent_tokens > self.child_size and current_sentences:
                content = " ".join(current_sentences)
                children.append(
                    Chunk(
                        content=content,
                        source=source,
                        chunk_index=child_index,
                        parent_id=parent.id,
                        is_parent=False,
                        metadata=meta.copy(),
                    )
                )
                overlap_sentences = self._take_overlap(current_sentences)
                current_sentences = overlap_sentences + [sentence]
                current_tokens = sum(_count_tokens(s) for s in current_sentences)
                child_index += 1
            else:
                current_sentences.append(sentence)
                current_tokens += sent_tokens

        if current_sentences:
            content = " ".join(current_sentences)
            children.append(
                Chunk(
                    content=content,
                    source=source,
                    chunk_index=child_index,
                    parent_id=parent.id,
                    is_parent=False,
                    metadata=meta.copy(),
                )
            )

        return children

    def _take_overlap(self, sentences: list[str]) -> list[str]:
        """Return the last N tokens worth of sentences for overlap."""
        result: list[str] = []
        tokens = 0
        for s in reversed(sentences):
            t = _count_tokens(s)
            if tokens + t > self.overlap:
                break
            result.insert(0, s)
            tokens += t
        return result
