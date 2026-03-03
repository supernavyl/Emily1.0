"""Tests for the ExportEngine — markdown, JSON, HTML, and PDF export."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from emily_chat.export.engine import ExportEngine
from emily_chat.storage.models import ConversationSummary, Message


def _make_conv(**overrides) -> ConversationSummary:
    """Create a test ConversationSummary."""
    defaults = {
        "id": "conv-1",
        "title": "Test Conversation",
        "created_at": datetime(2025, 6, 15, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2025, 6, 15, 13, 0, tzinfo=UTC),
        "model": "gpt-5",
        "provider": "openai",
        "skill_id": "code",
        "total_messages": 2,
        "total_tokens_in": 100,
        "total_tokens_out": 200,
        "total_cost_usd": 0.0042,
    }
    defaults.update(overrides)
    return ConversationSummary(**defaults)


def _make_messages() -> list[Message]:
    """Create test messages."""
    return [
        Message(
            id="msg-1",
            conversation_id="conv-1",
            role="user",
            content="Hello Emily, can you help me?",
            created_at=datetime(2025, 6, 15, 12, 0, tzinfo=UTC),
        ),
        Message(
            id="msg-2",
            conversation_id="conv-1",
            role="assistant",
            content="Of course! I'd be happy to help.",
            thinking_content="The user wants help. I should respond warmly.",
            model="gpt-5",
            provider="openai",
            tokens_in=50,
            tokens_out=100,
            cost_usd=0.0042,
            created_at=datetime(2025, 6, 15, 12, 1, tzinfo=UTC),
        ),
    ]


@pytest.fixture()
def engine() -> ExportEngine:
    """Return a fresh ExportEngine."""
    return ExportEngine()


class TestMarkdownExport:
    """Tests for to_markdown."""

    @pytest.mark.asyncio()
    async def test_has_frontmatter(self, engine: ExportEngine) -> None:
        md = await engine.to_markdown(_make_conv(), _make_messages())
        assert md.startswith("---")
        assert "title:" in md
        assert "---" in md[3:]

    @pytest.mark.asyncio()
    async def test_frontmatter_has_cost(self, engine: ExportEngine) -> None:
        md = await engine.to_markdown(_make_conv(), _make_messages())
        assert "cost_usd:" in md

    @pytest.mark.asyncio()
    async def test_frontmatter_has_model(self, engine: ExportEngine) -> None:
        md = await engine.to_markdown(_make_conv(), _make_messages())
        assert "model: gpt-5" in md

    @pytest.mark.asyncio()
    async def test_user_message_included(self, engine: ExportEngine) -> None:
        md = await engine.to_markdown(_make_conv(), _make_messages())
        assert "Hello Emily" in md

    @pytest.mark.asyncio()
    async def test_assistant_message_included(self, engine: ExportEngine) -> None:
        md = await engine.to_markdown(_make_conv(), _make_messages())
        assert "happy to help" in md

    @pytest.mark.asyncio()
    async def test_thinking_in_details(self, engine: ExportEngine) -> None:
        md = await engine.to_markdown(_make_conv(), _make_messages())
        assert "<details>" in md
        assert "Thinking" in md

    @pytest.mark.asyncio()
    async def test_title_heading(self, engine: ExportEngine) -> None:
        md = await engine.to_markdown(_make_conv(), _make_messages())
        assert "# Test Conversation" in md


class TestJsonExport:
    """Tests for to_json."""

    @pytest.mark.asyncio()
    async def test_valid_json(self, engine: ExportEngine) -> None:
        result = await engine.to_json(_make_conv(), _make_messages())
        data = json.loads(result)
        assert "conversation" in data
        assert "messages" in data

    @pytest.mark.asyncio()
    async def test_roundtrip_title(self, engine: ExportEngine) -> None:
        result = await engine.to_json(_make_conv(), _make_messages())
        data = json.loads(result)
        assert data["conversation"]["title"] == "Test Conversation"

    @pytest.mark.asyncio()
    async def test_message_count(self, engine: ExportEngine) -> None:
        result = await engine.to_json(_make_conv(), _make_messages())
        data = json.loads(result)
        assert len(data["messages"]) == 2

    @pytest.mark.asyncio()
    async def test_thinking_separate_field(self, engine: ExportEngine) -> None:
        result = await engine.to_json(_make_conv(), _make_messages())
        data = json.loads(result)
        assistant_msg = data["messages"][1]
        assert assistant_msg["thinking_content"] is not None

    @pytest.mark.asyncio()
    async def test_has_exported_at(self, engine: ExportEngine) -> None:
        result = await engine.to_json(_make_conv(), _make_messages())
        data = json.loads(result)
        assert "exported_at" in data

    @pytest.mark.asyncio()
    async def test_cost_preserved(self, engine: ExportEngine) -> None:
        result = await engine.to_json(_make_conv(), _make_messages())
        data = json.loads(result)
        assert data["conversation"]["total_cost_usd"] == pytest.approx(0.0042)


class TestHtmlExport:
    """Tests for to_html."""

    @pytest.mark.asyncio()
    async def test_self_contained(self, engine: ExportEngine) -> None:
        html = await engine.to_html(_make_conv(), _make_messages())
        assert "<!DOCTYPE html>" in html
        assert "<style>" in html
        assert "</html>" in html

    @pytest.mark.asyncio()
    async def test_has_title(self, engine: ExportEngine) -> None:
        html = await engine.to_html(_make_conv(), _make_messages())
        assert "Test Conversation" in html

    @pytest.mark.asyncio()
    async def test_has_messages(self, engine: ExportEngine) -> None:
        html = await engine.to_html(_make_conv(), _make_messages())
        assert "Hello Emily" in html
        assert "happy to help" in html

    @pytest.mark.asyncio()
    async def test_thinking_block(self, engine: ExportEngine) -> None:
        html = await engine.to_html(_make_conv(), _make_messages())
        assert "Thinking" in html
        assert "<details>" in html

    @pytest.mark.asyncio()
    async def test_user_and_assistant_classes(self, engine: ExportEngine) -> None:
        html = await engine.to_html(_make_conv(), _make_messages())
        assert 'class="message user"' in html
        assert 'class="message assistant"' in html

    @pytest.mark.asyncio()
    async def test_has_export_footer(self, engine: ExportEngine) -> None:
        html = await engine.to_html(_make_conv(), _make_messages())
        assert "Exported from Emily Chat" in html


class TestPdfExport:
    """Tests for to_pdf fallback (no weasyprint)."""

    @pytest.mark.asyncio()
    async def test_fallback_returns_bytes(self, engine: ExportEngine) -> None:
        result = await engine.to_pdf(_make_conv(), _make_messages())
        assert isinstance(result, bytes)
        assert b"<!DOCTYPE html>" in result


class TestExportPipeline:
    """Tests for the full export() method."""

    @pytest.mark.asyncio()
    async def test_markdown_file_created(self, engine: ExportEngine, tmp_path: Path) -> None:
        path = await engine.export(_make_conv(), _make_messages(), "markdown", tmp_path)
        assert path.exists()
        assert path.suffix == ".md"

    @pytest.mark.asyncio()
    async def test_json_file_created(self, engine: ExportEngine, tmp_path: Path) -> None:
        path = await engine.export(_make_conv(), _make_messages(), "json", tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

    @pytest.mark.asyncio()
    async def test_html_file_created(self, engine: ExportEngine, tmp_path: Path) -> None:
        path = await engine.export(_make_conv(), _make_messages(), "html", tmp_path)
        assert path.exists()
        assert path.suffix == ".html"

    @pytest.mark.asyncio()
    async def test_pdf_file_created(self, engine: ExportEngine, tmp_path: Path) -> None:
        path = await engine.export(_make_conv(), _make_messages(), "pdf", tmp_path)
        assert path.exists()
        assert path.suffix == ".pdf"

    @pytest.mark.asyncio()
    async def test_unknown_format_raises(self, engine: ExportEngine, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown export format"):
            await engine.export(_make_conv(), _make_messages(), "docx", tmp_path)
