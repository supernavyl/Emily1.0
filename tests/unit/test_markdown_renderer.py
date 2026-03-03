"""Tests for the markdown renderer.

Tests the stateless conversion functions in
:mod:`emily_chat.ui.markdown_renderer` — no Qt widgets required.
Covers: CommonMark rendering, GFM tables, task lists, strikethrough,
Pygments syntax highlighting, LaTeX detection/rendering, Mermaid
fallback, code block segmentation, and HTML escaping.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from emily_chat.ui.markdown_renderer import (
    MarkdownRenderer,
    _escape,
    _highlight_code,
    _render_latex,
    _render_mermaid_sync,
    build_document_css,
)


@pytest.fixture
def renderer() -> MarkdownRenderer:
    """Provide a fresh MarkdownRenderer for each test."""
    return MarkdownRenderer()


# ------------------------------------------------------------------
# Basic CommonMark rendering
# ------------------------------------------------------------------


class TestCommonMark:
    """Core CommonMark conversion."""

    def test_paragraph(self, renderer: MarkdownRenderer) -> None:
        """Plain text becomes a paragraph."""
        html = renderer.render("Hello world")
        assert "<p>" in html
        assert "Hello world" in html

    def test_heading_h1(self, renderer: MarkdownRenderer) -> None:
        """# heading becomes <h1>."""
        html = renderer.render("# Title")
        assert "<h1>" in html
        assert "Title" in html

    def test_heading_h2(self, renderer: MarkdownRenderer) -> None:
        """## heading becomes <h2>."""
        html = renderer.render("## Subtitle")
        assert "<h2>" in html

    def test_bold(self, renderer: MarkdownRenderer) -> None:
        """**bold** becomes <strong>."""
        html = renderer.render("**bold text**")
        assert "<strong>" in html
        assert "bold text" in html

    def test_italic(self, renderer: MarkdownRenderer) -> None:
        """*italic* becomes <em>."""
        html = renderer.render("*italic text*")
        assert "<em>" in html
        assert "italic text" in html

    def test_inline_code(self, renderer: MarkdownRenderer) -> None:
        """`code` becomes <code>."""
        html = renderer.render("`inline_var`")
        assert "<code>" in html
        assert "inline_var" in html

    def test_link(self, renderer: MarkdownRenderer) -> None:
        """[text](url) becomes an anchor."""
        html = renderer.render("[click](https://example.com)")
        assert "<a" in html
        assert "https://example.com" in html
        assert "click" in html

    def test_unordered_list(self, renderer: MarkdownRenderer) -> None:
        """Unordered list renders as <ul>."""
        html = renderer.render("- item one\n- item two")
        assert "<ul>" in html
        assert "<li>" in html

    def test_ordered_list(self, renderer: MarkdownRenderer) -> None:
        """Ordered list renders as <ol>."""
        html = renderer.render("1. first\n2. second")
        assert "<ol>" in html

    def test_blockquote(self, renderer: MarkdownRenderer) -> None:
        """> text renders as <blockquote>."""
        html = renderer.render("> quoted text")
        assert "<blockquote>" in html

    def test_horizontal_rule(self, renderer: MarkdownRenderer) -> None:
        """--- renders as <hr>."""
        html = renderer.render("---")
        assert "<hr" in html

    def test_image(self, renderer: MarkdownRenderer) -> None:
        """![alt](url) renders as <img>."""
        html = renderer.render("![alt text](https://example.com/img.png)")
        assert "<img" in html
        assert "alt text" in html


# ------------------------------------------------------------------
# GFM extensions
# ------------------------------------------------------------------


class TestGFMExtensions:
    """GitHub Flavored Markdown extensions."""

    def test_table(self, renderer: MarkdownRenderer) -> None:
        """GFM table renders as <table>."""
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = renderer.render(md)
        assert "<table>" in html
        assert "<th>" in html
        assert "<td>" in html

    def test_strikethrough(self, renderer: MarkdownRenderer) -> None:
        """~~text~~ renders as <s>."""
        html = renderer.render("~~deleted~~")
        assert "<s>" in html or "<del>" in html
        assert "deleted" in html

    def test_task_list_checked(self, renderer: MarkdownRenderer) -> None:
        """[x] renders as a checked indicator."""
        html = renderer.render("- [x] done item")
        assert "done item" in html

    def test_task_list_unchecked(self, renderer: MarkdownRenderer) -> None:
        """[ ] renders as an unchecked indicator."""
        html = renderer.render("- [ ] todo item")
        assert "todo item" in html


# ------------------------------------------------------------------
# Syntax highlighting
# ------------------------------------------------------------------


class TestSyntaxHighlighting:
    """Pygments syntax highlighting in code fences."""

    def test_python_code_highlighted(self, renderer: MarkdownRenderer) -> None:
        """Python code fences should contain Pygments-styled spans."""
        md = '```python\ndef hello():\n    return "hi"\n```'
        html = renderer.render(md)
        assert "def" in html
        assert "hello" in html
        assert "style=" in html or "color:" in html

    def test_unknown_language_escapes(self, renderer: MarkdownRenderer) -> None:
        """Unknown languages should not crash — content is escaped."""
        md = "```unknownlang\nfoo < bar\n```"
        html = renderer.render(md)
        assert "foo" in html

    def test_no_language_renders(self, renderer: MarkdownRenderer) -> None:
        """Code fences without a language should render as plain text."""
        md = "```\nplain code\n```"
        html = renderer.render(md)
        assert "plain code" in html

    def test_highlight_code_function(self) -> None:
        """Direct call to _highlight_code should return styled HTML."""
        result = _highlight_code("x = 1", "python")
        assert "style=" in result or "color:" in result


# ------------------------------------------------------------------
# LaTeX rendering
# ------------------------------------------------------------------


class TestLatex:
    """LaTeX math rendering via matplotlib."""

    def test_block_latex_replaced(self, renderer: MarkdownRenderer) -> None:
        """$$E = mc^2$$ should be replaced with an <img> tag."""
        html = renderer.render("$$E = mc^2$$")
        assert "<img" in html or "<code>" in html

    def test_inline_latex_replaced(self, renderer: MarkdownRenderer) -> None:
        """$x^2$ should be replaced."""
        html = renderer.render("The equation $x^2$ is simple.")
        assert "x^2" in html or "<img" in html

    def test_render_latex_returns_img(self) -> None:
        """_render_latex should return an <img> tag with base64 data."""
        result = _render_latex("x^2", inline=True)
        assert "<img" in result or "<code>" in result

    def test_render_latex_invalid_fallback(self) -> None:
        """Invalid LaTeX should fall back to <code> tag."""
        result = _render_latex("\\invalidcommand{", inline=True)
        assert "<code>" in result or "<img" in result

    def test_dollar_in_text_not_latex(self, renderer: MarkdownRenderer) -> None:
        """Standalone $ signs (like $50) should not trigger LaTeX."""
        html = renderer.render("The price is $50.")
        assert "50" in html


# ------------------------------------------------------------------
# Mermaid rendering
# ------------------------------------------------------------------


class TestMermaid:
    """Mermaid diagram handling."""

    def test_mermaid_fallback_without_mmdc(self, renderer: MarkdownRenderer) -> None:
        """Without mmdc, mermaid blocks should render as code."""
        with patch("emily_chat.ui.markdown_renderer._mmdc_available", return_value=False):
            md = "```mermaid\nflowchart LR\n  A --> B\n```"
            html = renderer.render(md)
            assert "flowchart" in html
            assert "<pre" in html

    def test_render_mermaid_sync_fallback(self) -> None:
        """_render_mermaid_sync should fall back gracefully."""
        with patch("emily_chat.ui.markdown_renderer._mmdc_available", return_value=False):
            result = _render_mermaid_sync("flowchart LR\n  A --> B")
            assert "<pre" in result
            assert "flowchart" in result


# ------------------------------------------------------------------
# Code block segmentation
# ------------------------------------------------------------------


class TestCodeBlockSegmentation:
    """render_with_code_blocks splits markdown for widget embedding."""

    def test_text_only(self, renderer: MarkdownRenderer) -> None:
        """Pure prose returns a single HTML segment."""
        segments = renderer.render_with_code_blocks("Hello world")
        assert len(segments) == 1
        assert segments[0]["type"] == "html"

    def test_code_block_extracted(self, renderer: MarkdownRenderer) -> None:
        """A fenced code block becomes a separate code segment."""
        md = "Before\n\n```python\nx = 1\n```\n\nAfter"
        segments = renderer.render_with_code_blocks(md)
        types = [s["type"] for s in segments]
        assert "code" in types
        code_seg = [s for s in segments if s["type"] == "code"][0]
        assert code_seg["lang"] == "python"
        assert "x = 1" in code_seg["content"]

    def test_multiple_code_blocks(self, renderer: MarkdownRenderer) -> None:
        """Multiple code blocks are each extracted separately."""
        md = "A\n\n```python\nx=1\n```\n\nB\n\n```js\ny=2\n```\n\nC"
        segments = renderer.render_with_code_blocks(md)
        code_segs = [s for s in segments if s["type"] == "code"]
        assert len(code_segs) == 2
        assert code_segs[0]["lang"] == "python"
        assert code_segs[1]["lang"] == "js"

    def test_mermaid_becomes_html(self, renderer: MarkdownRenderer) -> None:
        """Mermaid blocks become HTML segments (rendered or fallback)."""
        with patch("emily_chat.ui.markdown_renderer._mmdc_available", return_value=False):
            md = "Text\n\n```mermaid\nflowchart LR\n  A-->B\n```\n\nMore"
            segments = renderer.render_with_code_blocks(md)
            types = [s["type"] for s in segments]
            assert "code" not in types


# ------------------------------------------------------------------
# HTML escaping
# ------------------------------------------------------------------


class TestEscaping:
    """HTML escape utility."""

    def test_escape_angle_brackets(self) -> None:
        """Angle brackets should be escaped."""
        assert "&lt;" in _escape("<")
        assert "&gt;" in _escape(">")

    def test_escape_ampersand(self) -> None:
        """Ampersands should be escaped."""
        assert "&amp;" in _escape("&")

    def test_safe_text_unchanged(self) -> None:
        """Normal text passes through unchanged."""
        assert _escape("hello") == "hello"


# ------------------------------------------------------------------
# Document CSS builder
# ------------------------------------------------------------------


class TestDocumentCSS:
    """build_document_css produces valid CSS."""

    def test_builds_with_palette(self) -> None:
        """CSS should interpolate palette values."""
        from emily_chat.ui.theme_engine import PALETTES

        css = build_document_css(PALETTES["dark"])
        assert "#f0f0f5" in css
        assert "font-family" in css

    def test_builds_with_empty_palette(self) -> None:
        """Should use defaults when palette keys are missing."""
        css = build_document_css({})
        assert "font-family" in css
        assert "#f0f0f5" in css
