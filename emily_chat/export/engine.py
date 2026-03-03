"""Export engine — Markdown, JSON, HTML, and PDF conversation export.

All export methods are async-safe.  PDF requires ``weasyprint`` as an
optional dependency; if unavailable, a print-friendly HTML file is
produced instead.
"""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from emily_chat.storage.models import ConversationSummary, Message

_DEFAULT_EXPORT_DIR = Path.home() / "Documents" / "Emily Chat Exports"

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<header>
<h1>{title}</h1>
<p class="meta">{meta}</p>
</header>
<main>
{body}
</main>
<footer>
<p>Exported from Emily Chat on {export_date}</p>
</footer>
</body>
</html>
"""

_HTML_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #0a0a0f; color: #f0f0f5;
    max-width: 800px; margin: 0 auto; padding: 24px;
    line-height: 1.6;
}
header { margin-bottom: 24px; border-bottom: 1px solid #2a2a3a; padding-bottom: 16px; }
h1 { font-size: 1.4em; }
.meta { font-size: 0.85em; color: #8888aa; margin-top: 4px; }
.message { margin: 16px 0; padding: 12px 16px; border-radius: 10px; }
.user { background: #1a1a2e; }
.assistant { background: #111118; }
.role { font-weight: 600; font-size: 0.85em; color: #7c6af7; margin-bottom: 4px; }
.thinking { background: #0d1520; border-left: 3px solid #1e3a5f; padding: 8px 12px;
    margin: 8px 0; font-size: 0.9em; color: #8888aa; }
.thinking summary { cursor: pointer; font-weight: 600; }
pre { background: #0d0d14; padding: 12px; border-radius: 6px; overflow-x: auto;
    font-size: 0.85em; margin: 8px 0; }
code { font-family: "JetBrains Mono", "Fira Code", monospace; }
footer { margin-top: 24px; border-top: 1px solid #2a2a3a; padding-top: 12px;
    font-size: 0.8em; color: #555570; }
@media print {
    body { background: white; color: black; }
    .user { background: #f0f0f3; }
    .assistant { background: white; }
    .thinking { background: #eef2f8; border-color: #b8cce0; color: #333; }
    pre { background: #f5f5f5; }
}
"""


def _escape(text: str) -> str:
    """HTML-escape text.

    Args:
        text: Raw text.

    Returns:
        HTML-escaped string.
    """
    return html.escape(text, quote=True)


def _build_frontmatter(
    conv: ConversationSummary,
    messages: list[Message],
) -> str:
    """Build YAML frontmatter for markdown export.

    Args:
        conv: Conversation summary.
        messages: List of messages.

    Returns:
        YAML frontmatter string with ``---`` delimiters.
    """
    lines = [
        "---",
        f'title: "{conv.title}"',
        f"date: {conv.created_at.isoformat()}",
        f"model: {conv.model or 'unknown'}",
        f"skill: {conv.skill_id or 'none'}",
        f"messages: {len(messages)}",
        f"tokens_in: {conv.total_tokens_in}",
        f"tokens_out: {conv.total_tokens_out}",
        f"cost_usd: {conv.total_cost_usd:.4f}",
        "---",
        "",
    ]
    return "\n".join(lines)


def _build_meta_line(conv: ConversationSummary) -> str:
    """Build a metadata line for HTML export header.

    Args:
        conv: Conversation summary.

    Returns:
        Formatted metadata string.
    """
    parts = [
        f"Model: {conv.model or 'unknown'}",
        f"Messages: {conv.total_messages}",
    ]
    if conv.total_cost_usd > 0:
        parts.append(f"Cost: ${conv.total_cost_usd:.4f}")
    parts.append(f"Created: {conv.created_at.strftime('%Y-%m-%d %H:%M')}")
    return " | ".join(parts)


class ExportEngine:
    """Exports Emily Chat conversations to various formats."""

    async def to_markdown(
        self,
        conv: ConversationSummary,
        messages: list[Message],
    ) -> str:
        """Export to Markdown with YAML frontmatter.

        Args:
            conv: Conversation summary.
            messages: Ordered list of messages.

        Returns:
            Full markdown string.
        """
        parts = [_build_frontmatter(conv, messages)]
        parts.append(f"# {conv.title}\n\n")

        for msg in messages:
            if msg.role == "user":
                parts.append(f"## You\n\n{msg.content}\n\n")
            elif msg.role == "assistant":
                parts.append("## Emily\n\n")
                if msg.thinking_content:
                    parts.append(
                        "<details>\n<summary>Thinking</summary>\n\n"
                        f"{msg.thinking_content}\n\n</details>\n\n"
                    )
                parts.append(f"{msg.content}\n\n")

        return "".join(parts)

    async def to_json(
        self,
        conv: ConversationSummary,
        messages: list[Message],
    ) -> str:
        """Export to JSON with full metadata.

        Args:
            conv: Conversation summary.
            messages: Ordered list of messages.

        Returns:
            Pretty-printed JSON string.
        """
        data: dict[str, Any] = {
            "conversation": {
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
                "model": conv.model,
                "provider": conv.provider,
                "skill_id": conv.skill_id,
                "total_messages": conv.total_messages,
                "total_tokens_in": conv.total_tokens_in,
                "total_tokens_out": conv.total_tokens_out,
                "total_cost_usd": conv.total_cost_usd,
                "tags": conv.tags,
            },
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "thinking_content": msg.thinking_content,
                    "model": msg.model,
                    "provider": msg.provider,
                    "tokens_in": msg.tokens_in,
                    "tokens_out": msg.tokens_out,
                    "cost_usd": msg.cost_usd,
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in messages
            ],
            "exported_at": datetime.now(UTC).isoformat(),
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    async def to_html(
        self,
        conv: ConversationSummary,
        messages: list[Message],
    ) -> str:
        """Export to self-contained HTML with dark theme.

        Args:
            conv: Conversation summary.
            messages: Ordered list of messages.

        Returns:
            Complete HTML document string.
        """
        body_parts: list[str] = []

        for msg in messages:
            role_class = "user" if msg.role == "user" else "assistant"
            role_label = "You" if msg.role == "user" else "Emily"

            content = _escape(msg.content).replace("\n", "<br>")
            thinking_block = ""
            if msg.thinking_content:
                thinking_block = (
                    '<div class="thinking">\n'
                    "<details>\n<summary>Thinking</summary>\n"
                    f"<p>{_escape(msg.thinking_content)}</p>\n"
                    "</details>\n</div>\n"
                )

            body_parts.append(
                f'<div class="message {role_class}">\n'
                f'<div class="role">{role_label}</div>\n'
                f"{thinking_block}"
                f"<div>{content}</div>\n"
                f"</div>\n"
            )

        return _HTML_TEMPLATE.format(
            title=_escape(conv.title),
            css=_HTML_CSS,
            meta=_escape(_build_meta_line(conv)),
            body="\n".join(body_parts),
            export_date=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )

    async def to_pdf(
        self,
        conv: ConversationSummary,
        messages: list[Message],
    ) -> bytes:
        """Export to PDF via weasyprint, with HTML fallback.

        Args:
            conv: Conversation summary.
            messages: Ordered list of messages.

        Returns:
            PDF bytes, or HTML bytes if weasyprint is unavailable.
        """
        html_content = await self.to_html(conv, messages)
        try:
            import weasyprint  # type: ignore[import-untyped]

            doc = weasyprint.HTML(string=html_content)
            return doc.write_pdf()
        except ImportError:
            return html_content.encode("utf-8")

    async def export(
        self,
        conv: ConversationSummary,
        messages: list[Message],
        fmt: str,
        output_dir: Path | None = None,
    ) -> Path:
        """Full export pipeline: render and save to file.

        Args:
            conv: Conversation summary.
            messages: Ordered list of messages.
            fmt: Format string: ``"markdown"``, ``"json"``, ``"html"``,
                or ``"pdf"``.
            output_dir: Override output directory.

        Returns:
            Path to the saved file.

        Raises:
            ValueError: If the format is unknown.
        """
        out = output_dir or _DEFAULT_EXPORT_DIR
        out.mkdir(parents=True, exist_ok=True)

        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in conv.title)[
            :50
        ].strip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if fmt == "markdown":
            content = await self.to_markdown(conv, messages)
            path = out / f"{safe_title}_{timestamp}.md"
            path.write_text(content, encoding="utf-8")
        elif fmt == "json":
            content = await self.to_json(conv, messages)
            path = out / f"{safe_title}_{timestamp}.json"
            path.write_text(content, encoding="utf-8")
        elif fmt == "html":
            content = await self.to_html(conv, messages)
            path = out / f"{safe_title}_{timestamp}.html"
            path.write_text(content, encoding="utf-8")
        elif fmt == "pdf":
            pdf_bytes = await self.to_pdf(conv, messages)
            path = out / f"{safe_title}_{timestamp}.pdf"
            path.write_bytes(pdf_bytes)
        else:
            raise ValueError(f"Unknown export format: {fmt!r}")

        return path
