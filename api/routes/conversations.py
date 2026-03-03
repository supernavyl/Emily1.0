"""Conversation CRUD routes for the React chat frontend.

Wraps :class:`~emily_chat.storage.database.ConversationDatabase` behind
a RESTful API under ``/api/v1/conversations``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["conversations"])


def _get_db():
    from api.app import _chat_db

    if _chat_db is None:
        raise HTTPException(503, "Chat database not initialised")
    return _chat_db


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    model: str | None = None
    provider: str | None = None
    skill_id: str | None = None


class ConversationPatch(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None
    tags: list[str] | None = None


class MessageRate(BaseModel):
    rating: int = Field(..., ge=-1, le=1)


class MessageEdit(BaseModel):
    content: str


class ForkRequest(BaseModel):
    from_message_id: str


@router.get("/conversations")
async def list_conversations(include_archived: bool = False):
    db = _get_db()
    convs = await db.get_all_conversations(include_archived=include_archived)
    return {"conversations": [c.model_dump(mode="json") for c in convs]}


@router.post("/conversations", status_code=201)
async def create_conversation(body: ConversationCreate):
    from observability.metrics import CONVERSATIONS_TOTAL

    db = _get_db()
    conv = await db.create_conversation(
        title=body.title,
        model=body.model,
        provider=body.provider,
        skill_id=body.skill_id,
    )
    CONVERSATIONS_TOTAL.inc()
    return conv.model_dump(mode="json")


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    db = _get_db()
    conv = await db.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    messages = await db.get_messages(conversation_id)
    return {
        "conversation": conv.model_dump(mode="json"),
        "messages": [m.model_dump(mode="json") for m in messages],
    }


@router.patch("/conversations/{conversation_id}")
async def patch_conversation(conversation_id: str, body: ConversationPatch):
    db = _get_db()
    conv = await db.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    if body.title is not None:
        await db.rename_conversation(conversation_id, body.title)
    if body.pinned is not None:
        await db.pin_conversation(conversation_id, body.pinned)
    if body.archived is not None:
        await db.archive_conversation(conversation_id, body.archived)
    updated = await db.get_conversation(conversation_id)
    return updated.model_dump(mode="json") if updated else {}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    db = _get_db()
    await db.delete_conversation(conversation_id)
    return {"ok": True}


@router.post("/conversations/{conversation_id}/duplicate", status_code=201)
async def duplicate_conversation(conversation_id: str):
    db = _get_db()
    conv = await db.duplicate_conversation(conversation_id)
    if conv is None:
        raise HTTPException(404, "Source conversation not found")
    return conv.model_dump(mode="json")


@router.post("/conversations/{conversation_id}/fork", status_code=201)
async def fork_conversation(conversation_id: str, body: ForkRequest):
    db = _get_db()
    conv = await db.fork_conversation(conversation_id, body.from_message_id)
    if conv is None:
        raise HTTPException(404, "Source conversation not found")
    return conv.model_dump(mode="json")


@router.get("/search")
async def search_conversations(q: str = Query(..., min_length=1), limit: int = 20):
    db = _get_db()
    results = await db.search_fulltext(q, limit=limit)
    return {"results": [r.model_dump(mode="json") for r in results]}


@router.post("/messages/{message_id}/rate")
async def rate_message(message_id: str, body: MessageRate):
    """Set like/dislike rating on a message."""
    db = _get_db()
    updated = await db.rate_message(message_id, body.rating)
    if not updated:
        raise HTTPException(404, "Message not found")
    return {"ok": True}


@router.post("/messages/{message_id}/edit")
async def edit_message(message_id: str, body: MessageEdit):
    """Edit the content of a message."""
    db = _get_db()
    updated = await db.edit_message(message_id, body.content)
    if not updated:
        raise HTTPException(404, "Message not found")
    return {"ok": True}
