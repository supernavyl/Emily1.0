"""Pydantic data models for the Emily Chat conversation database."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationSummary(BaseModel):
    """Lightweight view of a conversation for sidebar display."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    model: str | None = None
    provider: str | None = None
    skill_id: str | None = None
    pinned: bool = False
    archived: bool = False
    tags: list[str] = Field(default_factory=list)
    total_messages: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_thinking_tokens: int = 0
    total_cost_usd: float = 0.0
    parent_id: str | None = None
    branch_from_message_id: str | None = None


class Message(BaseModel):
    """A single message within a conversation."""

    id: str
    conversation_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    content_raw: str | None = None
    thinking_content: str | None = None
    model: str | None = None
    provider: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_thinking: int = 0
    cost_usd: float = 0.0
    latency_ms: int | None = None
    first_token_ms: int | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    edited: bool = False
    stopped: bool = False
    rating: int = 0  # 1 | -1 | 0
    version: int = 1
    parent_message_id: str | None = None


class SearchResult(BaseModel):
    """A single FTS5 search hit."""

    conversation_id: str
    message_id: str
    title: str
    excerpt: str
    match_rank: float
