"""
Tier 2: Working Memory — active conversation context with token-budget-aware trimming.

Working memory holds the current conversation turns for the LLM context window.
When the token budget is approached, low-importance turns are dropped to keep
the most relevant context within the limit.

Importance scoring:
- Recent turns get higher base weight (recency bias)
- Turns with explicit user corrections are pinned (never dropped)
- Turns containing key decisions or facts are elevated
- The MemoryAgent can manually pin any turn via pin()
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import tiktoken

from config import WorkingMemoryConfig
from llm.client import ChatMessage
from observability.logger import get_logger
from observability.metrics import WORKING_MEMORY_TOKENS

log = get_logger(__name__)

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """
    Count the number of tokens in a text string using cl100k_base tokenizer.

    Args:
        text: The text to count tokens for.

    Returns:
        Token count.
    """
    return len(_TOKENIZER.encode(text))


@dataclass
class WorkingMemoryEntry:
    """A single entry in working memory."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "user"  # "user" | "assistant" | "system" | "tool"
    content: str = ""
    importance: float = 0.5  # 0.0 (disposable) to 1.0 (critical)
    pinned: bool = False
    timestamp: float = field(default_factory=time.time)
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.token_count:
            self.token_count = count_tokens(self.content)


class WorkingMemory:
    """
    Token-budget-aware conversation context window.

    Maintains a list of WorkingMemoryEntry objects. When the total token
    count approaches max_tokens, entries are trimmed in ascending importance
    order (keeping system prompt and pinned entries).
    """

    def __init__(self, config: WorkingMemoryConfig) -> None:
        """
        Args:
            config: Working memory configuration.
        """
        self._config = config
        self._entries: list[WorkingMemoryEntry] = []
        self._session_id = str(uuid.uuid4())

    def add(
        self,
        role: str,
        content: str,
        importance: float = 0.5,
        pinned: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> WorkingMemoryEntry:
        """
        Add a new turn to working memory.

        If adding the entry would exceed the token budget, trimming is
        performed first to make room.

        Args:
            role: Message role ("user", "assistant", "system", "tool").
            content: Message text.
            importance: Importance score [0.0, 1.0].
            pinned: If True, this entry is never removed by trimming.
            metadata: Optional metadata dict.

        Returns:
            The created WorkingMemoryEntry.
        """
        entry = WorkingMemoryEntry(
            role=role,
            content=content,
            importance=importance,
            pinned=pinned,
            metadata=metadata or {},
        )

        # Auto-pin based on importance threshold
        if importance >= self._config.pin_important_threshold:
            entry.pinned = True

        self._entries.append(entry)
        self._maybe_trim()
        self._update_metrics()
        return entry

    def pin(self, entry_id: str) -> bool:
        """
        Pin an entry by ID so it is never trimmed.

        Args:
            entry_id: The entry's UUID.

        Returns:
            True if found and pinned.
        """
        for entry in self._entries:
            if entry.id == entry_id:
                entry.pinned = True
                return True
        return False

    def set_importance(self, entry_id: str, importance: float) -> bool:
        """
        Update the importance score of an existing entry.

        Args:
            entry_id: The entry's UUID.
            importance: New importance score [0.0, 1.0].

        Returns:
            True if found and updated.
        """
        for entry in self._entries:
            if entry.id == entry_id:
                entry.importance = importance
                if importance >= self._config.pin_important_threshold:
                    entry.pinned = True
                return True
        return False

    def _maybe_trim(self) -> None:
        """
        Trim unpinned, low-importance entries if the token budget is exceeded.
        Keeps system entries and pinned entries. Sorts by importance ascending,
        removes from lowest importance first.
        """
        total = self.total_tokens
        if total <= self._config.max_tokens:
            return

        # Collect trimmable entries (not pinned, not system role)
        trimmable = [
            e for e in self._entries
            if not e.pinned and e.role != "system"
        ]
        trimmable.sort(key=lambda e: (e.importance, e.timestamp))

        for entry in trimmable:
            if self.total_tokens <= self._config.max_tokens:
                break
            self._entries.remove(entry)
            log.debug(
                "working_memory_trimmed",
                entry_id=entry.id,
                importance=entry.importance,
                tokens=entry.token_count,
            )

    def to_messages(self) -> list[ChatMessage]:
        """
        Convert working memory to a list of ChatMessage objects for LLM inference.

        Returns:
            Ordered list of ChatMessage objects.
        """
        return [
            ChatMessage(role=e.role, content=e.content)
            for e in self._entries
        ]

    def to_dict_list(self) -> list[dict[str, str]]:
        """
        Convert to plain dict list for serialization.

        Returns:
            List of {"role": str, "content": str} dicts.
        """
        return [{"role": e.role, "content": e.content} for e in self._entries]

    def clear(self, keep_system: bool = True) -> None:
        """
        Clear working memory.

        Args:
            keep_system: If True, preserve system-role entries.
        """
        if keep_system:
            self._entries = [e for e in self._entries if e.role == "system"]
        else:
            self._entries.clear()
        self._session_id = str(uuid.uuid4())
        self._update_metrics()

    def _update_metrics(self) -> None:
        """Update Prometheus metric for working memory token usage."""
        WORKING_MEMORY_TOKENS.set(self.total_tokens)

    @property
    def total_tokens(self) -> int:
        """Total token count across all entries."""
        return sum(e.token_count for e in self._entries)

    @property
    def entry_count(self) -> int:
        """Number of entries in working memory."""
        return len(self._entries)

    @property
    def session_id(self) -> str:
        """Current session identifier."""
        return self._session_id

    @property
    def entries(self) -> list[WorkingMemoryEntry]:
        """Read-only view of all entries."""
        return list(self._entries)

    def get_transcript(self) -> str:
        """
        Return the full conversation as a plain text transcript.

        Returns:
            Multi-line string with role-prefixed turns.
        """
        lines = []
        for entry in self._entries:
            if entry.role == "system":
                continue
            role_label = "Emily" if entry.role == "assistant" else entry.role.capitalize()
            lines.append(f"{role_label}: {entry.content}")
        return "\n".join(lines)
