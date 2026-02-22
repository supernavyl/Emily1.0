"""Markdown renderer — CommonMark + GFM + LaTeX + Mermaid + Pygments.

Converts raw markdown to Qt-renderable HTML and provides
:class:`MarkdownTextBrowser`, a streaming-capable widget that
interleaves rendered prose with standalone :class:`CodeBlockWidget`
instances.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
import shutil
from functools import lru_cache
from typing import Any

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

logger = logging.getLogger(__name__)

_LATEX_BLOCK_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_LATEX_INLINE_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")

_MERMAID_FENCE_RE = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Pygments highlighter (inline CSS — QTextBrowser has no class support)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _formatter() -> HtmlFormatter:
    """Shared Pygments HTML formatter with inline styles for dark theme."""
    return HtmlFormatter(
        noclasses=True,
        nowrap=False,
        style="monokai",
    )


def _highlight_code(code: str, lang: str) -> str:
    """Syntax-highlight *code* as HTML using Pygments.

    Args:
        code: Raw source code.
        lang: Language identifier (e.g. ``"python"``).

    Returns:
        HTML string with inline-styled syntax highlighting.
    """
    try:
        lexer = get_lexer_by_name(lang, stripall=True)
    except ClassNotFound:
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            return f"<pre><code>{_escape(code)}</code></pre>"
    return pygments_highlight(code, lexer, _formatter())


def _escape(text: str) -> str:
    """HTML-escape text for safe embedding."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# LaTeX rendering (matplotlib)
# ---------------------------------------------------------------------------

def _render_latex(expression: str, *, inline: bool = True) -> str:
    """Render a LaTeX expression to a base64-encoded PNG ``<img>`` tag.

    Uses matplotlib's mathtext engine.  If matplotlib is unavailable or
    the expression is invalid, returns the raw LaTeX in a ``<code>`` tag.

    Args:
        expression: The raw LaTeX (without ``$`` delimiters).
        inline: ``True`` for inline math, ``False`` for block (display).

    Returns:
        An HTML ``<img>`` tag, or a ``<code>`` fallback.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import mathtext
    except ImportError:
        return f"<code>${expression}$</code>"

    try:
        buf = io.BytesIO()
        dpi = 150 if inline else 200
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.text(
            0, 0,
            f"${expression}$",
            fontsize=14 if inline else 18,
            color="white",
        )
        fig.savefig(
            buf, format="png", dpi=dpi,
            bbox_inches="tight", pad_inches=0.05,
            transparent=True,
        )
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode()
        style = "" if inline else 'style="display:block;margin:12px auto;"'
        return f'<img src="data:image/png;base64,{b64}" alt="{_escape(expression)}" {style}/>'
    except Exception:
        logger.debug("LaTeX render failed for: %s", expression[:80])
        return f"<code>${expression}$</code>"


def _replace_latex(html: str) -> str:
    """Post-process HTML to replace LaTeX ``$$...$$`` and ``$...$`` with rendered PNGs."""
    html = _LATEX_BLOCK_RE.sub(
        lambda m: _render_latex(m.group(1).strip(), inline=False), html
    )
    html = _LATEX_INLINE_RE.sub(
        lambda m: _render_latex(m.group(1).strip(), inline=True), html
    )
    return html


# ---------------------------------------------------------------------------
# Mermaid rendering (subprocess to mmdc if available)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _mmdc_available() -> bool:
    """Check whether the mermaid-cli ``mmdc`` binary is on PATH."""
    return shutil.which("mmdc") is not None


def _render_mermaid_sync(source: str) -> str:
    """Render Mermaid diagram to SVG synchronously, with code-block fallback.

    Args:
        source: Raw mermaid source.

    Returns:
        An HTML ``<img>`` tag with an SVG data URI, or a styled ``<pre>``
        fallback.
    """
    if not _mmdc_available():
        return (
            '<pre style="background:#0d1520;border:1px solid #1e3a5f;'
            'border-radius:6px;padding:8px;font-size:12px;">'
            f"<code>{_escape(source)}</code></pre>"
        )

    import subprocess

    try:
        result = subprocess.run(
            ["mmdc", "-i", "/dev/stdin", "-o", "/dev/stdout", "-e", "svg",
             "-b", "transparent", "-t", "dark"],
            input=source.encode(),
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout:
            b64 = base64.b64encode(result.stdout).decode()
            return (
                f'<img src="data:image/svg+xml;base64,{b64}" '
                f'alt="mermaid diagram" style="max-width:100%;"/>'
            )
    except Exception:
        logger.debug("Mermaid render failed")

    return (
        '<pre style="background:#0d1520;border:1px solid #1e3a5f;'
        'border-radius:6px;padding:8px;font-size:12px;">'
        f"<code>{_escape(source)}</code></pre>"
    )


def _replace_mermaid(html: str) -> str:
    """Post-process HTML to replace mermaid code fences with rendered SVGs."""
    return _MERMAID_FENCE_RE.sub(
        lambda m: _render_mermaid_sync(_unescape(m.group(1).strip())), html
    )


def _unescape(text: str) -> str:
    """Reverse HTML escaping for code block content."""
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )


# ---------------------------------------------------------------------------
# MarkdownRenderer — stateless converter
# ---------------------------------------------------------------------------


class MarkdownRenderer:
    """Converts raw markdown to Qt-renderable HTML.

    Supports CommonMark, GFM tables, task lists, strikethrough,
    footnotes, Pygments syntax highlighting, LaTeX math, and Mermaid
    diagrams.
    """

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark", {"html": False, "typographer": True})
        self._md.enable(["table", "strikethrough"])
        tasklists_plugin(self._md)
        footnote_plugin(self._md)
        front_matter_plugin(self._md)

        self._md.options["highlight"] = self._highlight_callback

    @staticmethod
    def _highlight_callback(code: str, lang: str, _attrs: str) -> str:
        """markdown-it highlight callback for fenced code blocks.

        Returns raw HTML that markdown-it wraps in ``<pre><code>``.

        Args:
            code: Code block content.
            lang: Language identifier from the fence info string.
            _attrs: Unused extra attributes string.

        Returns:
            Syntax-highlighted HTML, or plain escaped HTML.
        """
        if not lang:
            return _escape(code)
        if lang.lower() == "mermaid":
            return _escape(code)
        return _highlight_code(code, lang)

    def render(self, markdown: str) -> str:
        """Convert markdown source to HTML.

        Args:
            markdown: Raw markdown text.

        Returns:
            HTML string ready for ``QTextBrowser.setHtml()``.
        """
        html = self._md.render(markdown)
        html = _replace_latex(html)
        html = _replace_mermaid(html)
        return html

    def render_with_code_blocks(self, markdown: str) -> list[dict[str, Any]]:
        """Convert markdown to a list of segments — prose HTML and code blocks.

        Splits at fenced code block boundaries so that
        :class:`CodeBlockWidget` instances can be embedded between HTML
        segments.

        Args:
            markdown: Raw markdown text.

        Returns:
            A list of dicts.  Each dict has ``"type"`` (``"html"`` or
            ``"code"``) and type-specific keys:

            - ``{"type": "html", "content": "<p>...</p>"}``
            - ``{"type": "code", "lang": "python", "content": "print(1)"}``
        """
        tokens = self._md.parse(markdown)
        segments: list[dict[str, Any]] = []
        prose_tokens: list[Any] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.type == "fence" and tok.tag == "code":
                if prose_tokens:
                    html = self._render_tokens(prose_tokens)
                    html = _replace_latex(html)
                    if html.strip():
                        segments.append({"type": "html", "content": html})
                    prose_tokens = []
                lang = tok.info.strip().split()[0] if tok.info.strip() else ""
                code = tok.content
                if lang.lower() == "mermaid":
                    svg = _render_mermaid_sync(code.strip())
                    segments.append({"type": "html", "content": svg})
                else:
                    segments.append({
                        "type": "code",
                        "lang": lang,
                        "content": code.rstrip("\n"),
                    })
                i += 1
            else:
                prose_tokens.append(tok)
                i += 1

        if prose_tokens:
            html = self._render_tokens(prose_tokens)
            html = _replace_latex(html)
            if html.strip():
                segments.append({"type": "html", "content": html})

        return segments

    def _render_tokens(self, tokens: list[Any]) -> str:
        """Render a subset of parsed tokens back to HTML.

        Args:
            tokens: Token list from ``MarkdownIt.parse()``.

        Returns:
            Rendered HTML string.
        """
        return self._md.renderer.render(tokens, self._md.options, {})


# ---------------------------------------------------------------------------
# Default document CSS for QTextBrowser HTML rendering
# ---------------------------------------------------------------------------

DOCUMENT_CSS = """
body {{
    font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 14px;
    color: {text_primary};
    line-height: 1.6;
    margin: 0;
    padding: 0;
}}
a {{
    color: {link_color};
    text-decoration: none;
}}
a:hover {{
    text-decoration: underline;
}}
h1, h2, h3, h4, h5, h6 {{
    color: {text_primary};
    margin-top: 16px;
    margin-bottom: 8px;
}}
h1 {{ font-size: 22px; }}
h2 {{ font-size: 18px; }}
h3 {{ font-size: 16px; }}
code {{
    background-color: {code_bg};
    border-radius: 3px;
    padding: 1px 4px;
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 13px;
}}
pre {{
    background-color: {code_bg};
    border: 1px solid {code_border};
    border-radius: 6px;
    padding: 10px;
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 13px;
    overflow-x: auto;
}}
pre code {{
    background: transparent;
    padding: 0;
}}
blockquote {{
    border-left: 3px solid {accent};
    margin-left: 0;
    padding-left: 12px;
    color: {text_secondary};
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
}}
th, td {{
    border: 1px solid {border};
    padding: 6px 10px;
    text-align: left;
}}
th {{
    background-color: {surface_raised};
    font-weight: 600;
}}
tr:nth-child(even) {{
    background-color: {surface};
}}
hr {{
    border: none;
    border-top: 1px solid {border};
    margin: 16px 0;
}}
ul, ol {{
    padding-left: 24px;
}}
li {{
    margin-bottom: 4px;
}}
img {{
    max-width: 100%;
}}
del {{
    color: {text_muted};
}}
"""


def build_document_css(palette: dict[str, str]) -> str:
    """Build the CSS for the QTextBrowser document stylesheet.

    Args:
        palette: Theme palette dict (from :data:`theme_engine.PALETTES`).

    Returns:
        CSS string.
    """
    return DOCUMENT_CSS.format(
        text_primary=palette.get("text_primary", "#f0f0f5"),
        text_secondary=palette.get("text_secondary", "#8888aa"),
        text_muted=palette.get("text_muted", "#555570"),
        link_color=palette.get("link_color", palette.get("accent", "#7c6af7")),
        code_bg=palette.get("code_bg", "#0d0d14"),
        code_border=palette.get("code_border", palette.get("border", "#2a2a3a")),
        accent=palette.get("accent", "#7c6af7"),
        surface=palette.get("surface", "#111118"),
        surface_raised=palette.get("surface_raised", "#1a1a24"),
        border=palette.get("border", "#2a2a3a"),
    )
