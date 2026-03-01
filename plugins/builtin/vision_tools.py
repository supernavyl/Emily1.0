"""Vision tools — Emily's eyes.

Gives Emily on-demand visual perception of the computer and her environment:
  - see_screen   : take a screenshot and describe / analyze what's on screen
  - read_screen  : take a screenshot and extract all visible text (OCR)
  - see_webcam   : grab a webcam frame and describe what / who Emily sees
  - look_at      : analyze any image file or URL with a custom prompt

Capture backend is auto-selected:
  Wayland → grim (saves PNG to temp file)
  X11     → mss library (in-memory, fastest)
  Fallback → scrot, spectacle, gnome-screenshot
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from observability.logger import get_logger
from plugins.base import BaseTool, ExecutionContext, ToolResult, ValidationResult

log = get_logger(__name__)

_OLLAMA_URL = "http://localhost:11434"
_VISION_MODEL = "minicpm-v:latest"


# ─────────────────────────────────────────────────────────────────────────────
# Screenshot capture — X11 / Wayland aware
# ─────────────────────────────────────────────────────────────────────────────


def _is_wayland() -> bool:
    return (
        os.environ.get("WAYLAND_DISPLAY") is not None
        or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
    )


async def _screenshot_mss() -> bytes | None:
    """Capture screen using mss (X11 / XWayland)."""
    try:
        import mss  # type: ignore[import-untyped]
        from PIL import Image  # type: ignore[import-untyped]

        def _grab() -> bytes:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                if img.width > 1280:
                    ratio = 1280 / img.width
                    img = img.resize((1280, int(img.height * ratio)))
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                return buf.getvalue()

        return await asyncio.to_thread(_grab)
    except Exception as exc:
        log.debug("mss_screenshot_failed", error=str(exc))
        return None


async def _screenshot_grim() -> bytes | None:
    """Capture screen using grim (Wayland native)."""
    if not shutil.which("grim"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            "grim",
            tmp,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        if proc.returncode == 0 and Path(tmp).exists():
            data = Path(tmp).read_bytes()
            return data
    except Exception as exc:
        log.debug("grim_screenshot_failed", error=str(exc))
    finally:
        with contextlib.suppress(OSError):
            Path(tmp).unlink(missing_ok=True)
    return None


async def _screenshot_scrot() -> bytes | None:
    """Capture screen using scrot (X11 fallback)."""
    if not shutil.which("scrot"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            "scrot",
            tmp,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        if proc.returncode == 0 and Path(tmp).exists():
            return Path(tmp).read_bytes()
    except Exception as exc:
        log.debug("scrot_screenshot_failed", error=str(exc))
    finally:
        with contextlib.suppress(OSError):
            Path(tmp).unlink(missing_ok=True)
    return None


async def _screenshot_spectacle() -> bytes | None:
    """Capture screen using KDE spectacle (Wayland fallback)."""
    if not shutil.which("spectacle"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            "spectacle",
            "--background",
            "--nonotify",
            "--fullscreen",
            "-o",
            tmp,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=8.0)
        if proc.returncode == 0 and Path(tmp).exists():
            return Path(tmp).read_bytes()
    except Exception as exc:
        log.debug("spectacle_screenshot_failed", error=str(exc))
    finally:
        with contextlib.suppress(OSError):
            Path(tmp).unlink(missing_ok=True)
    return None


async def take_screenshot() -> tuple[bytes | None, str]:
    """Take a screenshot using the best available method. Returns (png_bytes, method)."""
    if _is_wayland():
        data = await _screenshot_grim()
        if data:
            return data, "grim"
        data = await _screenshot_spectacle()
        if data:
            return data, "spectacle"
        # XWayland fallback
        data = await _screenshot_mss()
        if data:
            return data, "mss/xwayland"
    else:
        data = await _screenshot_mss()
        if data:
            return data, "mss"
        data = await _screenshot_scrot()
        if data:
            return data, "scrot"
    return None, "none"


# ─────────────────────────────────────────────────────────────────────────────
# Vision model query
# ─────────────────────────────────────────────────────────────────────────────


async def _ask_vision(image_b64: str, prompt: str, timeout: float = 30.0) -> str:
    """Send an image + prompt to MiniCPM-V via Ollama."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{_OLLAMA_URL}/api/chat",
                json={
                    "model": _VISION_MODEL,
                    "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
    except httpx.ConnectError:
        return "[error: cannot connect to Ollama vision model]"
    except Exception as exc:
        log.error("vision_query_error", error=str(exc))
        return f"[error: {exc}]"


# ─────────────────────────────────────────────────────────────────────────────
# 1. See Screen
# ─────────────────────────────────────────────────────────────────────────────


class SeeScreenTool(BaseTool):
    """Take a screenshot and describe what's currently on screen."""

    name = "see_screen"
    description = (
        "Take a screenshot of the current screen and use the vision model to "
        "describe or answer questions about what's visible. "
        "Use this to see what the user is looking at, read on-screen content, "
        "understand the current application, or help with anything visual on screen."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "What to look for or ask about. Default: describe everything visible. "
                    "Examples: 'what app is open?', 'what does this error say?', "
                    "'what is the user working on?'"
                ),
                "default": "Describe everything currently visible on this screen in detail. What app is open? What content is shown?",
            },
            "save_path": {
                "type": "string",
                "description": "Optional path to save the screenshot PNG to.",
            },
        },
    }
    requires_approval = False
    timeout_seconds = 40

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "Will take a screenshot and analyze what's on screen"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        prompt = params.get(
            "prompt",
            "Describe everything currently visible on this screen in detail. What app is open? What content is shown?",
        )
        save_path = params.get("save_path")
        t0 = time.monotonic()

        png_bytes, method = await take_screenshot()
        if not png_bytes:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(
                error="Could not capture screen — no screenshot backend available (try: pacman -S grim scrot mss)",
                execution_time_ms=elapsed,
            )

        if save_path:
            try:
                Path(save_path).write_bytes(png_bytes)
            except OSError as exc:
                log.warning("screenshot_save_failed", error=str(exc))

        image_b64 = base64.b64encode(png_bytes).decode()
        description = await _ask_vision(image_b64, prompt, timeout=35.0)

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(
            output=description,
            execution_time_ms=elapsed,
            capture_method=method,
            screenshot_size_kb=round(len(png_bytes) / 1024, 1),
            saved_to=save_path,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Read Screen (OCR)
# ─────────────────────────────────────────────────────────────────────────────


class ReadScreenTool(BaseTool):
    """Take a screenshot and extract all visible text (OCR via vision model)."""

    name = "read_screen"
    description = (
        "Take a screenshot and extract all visible text from the screen using the vision model. "
        "Use this to read error messages, code on screen, terminal output, "
        "documents, or any text the user is looking at without needing to copy-paste."
    )
    parameters = {
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "description": "Optional: which region to focus on (e.g., 'top half', 'terminal window', 'error dialog').",
            },
        },
    }
    requires_approval = False
    timeout_seconds = 40

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "Will take a screenshot and extract all text from the screen"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        region = params.get("region", "")
        t0 = time.monotonic()

        png_bytes, method = await take_screenshot()
        if not png_bytes:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(error="Could not capture screen", execution_time_ms=elapsed)

        image_b64 = base64.b64encode(png_bytes).decode()

        region_hint = f" Focus on the {region}." if region else ""
        prompt = (
            f"Extract ALL visible text from this screenshot exactly as it appears.{region_hint} "
            "Include code, error messages, UI labels, terminal output, menus — everything. "
            "Preserve formatting and line breaks."
        )

        text = await _ask_vision(image_b64, prompt, timeout=35.0)
        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(
            output=text,
            execution_time_ms=elapsed,
            capture_method=method,
            char_count=len(text),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. See Webcam
# ─────────────────────────────────────────────────────────────────────────────


class SeeWebcamTool(BaseTool):
    """Grab a frame from the webcam and describe what Emily sees."""

    name = "see_webcam"
    description = (
        "Capture a frame from the webcam and describe what Emily sees — who is in front "
        "of the computer, their apparent expression or emotion, or anything else visible. "
        "Use this for presence detection, facial expression reading, or environment awareness."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "What to look for. Default: describe person and environment.",
                "default": "Describe the person or environment you see in this webcam frame. Note their expression, posture, and anything else visible.",
            },
            "device": {
                "type": "integer",
                "description": "Webcam device index. Default: 0.",
                "default": 0,
            },
        },
    }
    requires_approval = False
    timeout_seconds = 40

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will capture webcam frame from device {params.get('device', 0)} and analyze"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        import importlib.util

        if importlib.util.find_spec("cv2") is None:
            return ValidationResult.fail("opencv-python not installed (pip install opencv-python)")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        prompt = params.get(
            "prompt",
            "Describe the person or environment you see in this webcam frame. Note their expression, posture, and anything else visible.",
        )
        device = int(params.get("device", 0))
        t0 = time.monotonic()

        def _grab_frame() -> bytes | None:
            import cv2  # type: ignore[import-untyped]

            cap = cv2.VideoCapture(device)
            if not cap.isOpened():
                return None
            try:
                # Skip a few frames to let camera exposure settle
                for _ in range(3):
                    cap.read()
                ret, frame = cap.read()
                if not ret or frame is None:
                    return None
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return buf.tobytes()
            finally:
                cap.release()

        try:
            jpg_bytes = await asyncio.to_thread(_grab_frame)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(error=f"Webcam capture failed: {exc}", execution_time_ms=elapsed)

        if not jpg_bytes:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(
                error=f"Could not open webcam device {device}",
                execution_time_ms=elapsed,
            )

        image_b64 = base64.b64encode(jpg_bytes).decode()
        description = await _ask_vision(image_b64, prompt, timeout=35.0)

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(
            output=description,
            execution_time_ms=elapsed,
            device=device,
            frame_size_kb=round(len(jpg_bytes) / 1024, 1),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Look At (analyze any image file or URL)
# ─────────────────────────────────────────────────────────────────────────────


class LookAtTool(BaseTool):
    """Analyze any image — file path or URL — with a custom prompt."""

    name = "look_at"
    description = (
        "Analyze any image using the vision model. Accepts a local file path or HTTP URL. "
        "Use this to describe images, extract text from them, answer questions about them, "
        "or identify objects/people/content in photos, diagrams, screenshots, etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "File path (/home/user/photo.jpg) or HTTP/HTTPS URL to the image.",
            },
            "prompt": {
                "type": "string",
                "description": "What to ask about the image. Default: describe in detail.",
                "default": "Describe this image in detail.",
            },
        },
        "required": ["source"],
    }
    requires_approval = False
    timeout_seconds = 45

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will analyze image: {params.get('source', '')}"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        source = params.get("source", "").strip()
        if not source:
            return ValidationResult.fail("source is required")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        source = params["source"].strip()
        prompt = params.get("prompt", "Describe this image in detail.")
        t0 = time.monotonic()

        # Load image bytes
        if source.startswith(("http://", "https://")):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(source)
                    resp.raise_for_status()
                    img_bytes = resp.content
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                return ToolResult.fail(
                    error=f"Failed to fetch image URL: {exc}", execution_time_ms=elapsed
                )
        else:
            path = Path(source).expanduser()
            if not path.exists():
                elapsed = (time.monotonic() - t0) * 1000
                return ToolResult.fail(error=f"File not found: {path}", execution_time_ms=elapsed)
            img_bytes = path.read_bytes()

        image_b64 = base64.b64encode(img_bytes).decode()
        description = await _ask_vision(image_b64, prompt, timeout=40.0)

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(
            output=description,
            execution_time_ms=elapsed,
            source=source,
            image_size_kb=round(len(img_bytes) / 1024, 1),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Watch Screen (detect changes over time)
# ─────────────────────────────────────────────────────────────────────────────


class WatchScreenTool(BaseTool):
    """Take multiple screenshots over a time window and summarize what changed."""

    name = "watch_screen"
    description = (
        "Watch the screen for a short period and summarize what happened — "
        "what changed, what the user did, what appeared or disappeared. "
        "Useful for monitoring long-running tasks, understanding workflow, "
        "or noticing when something finishes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "duration_s": {
                "type": "number",
                "description": "How many seconds to watch the screen. Default: 10.",
                "default": 10,
            },
            "interval_s": {
                "type": "number",
                "description": "Seconds between screenshots. Default: 3.",
                "default": 3,
            },
            "focus": {
                "type": "string",
                "description": "Optional: what to watch for (e.g., 'when the build finishes', 'what the user types').",
            },
        },
    }
    requires_approval = False
    timeout_seconds = 90

    async def dry_run(self, params: dict[str, Any]) -> str:
        d = params.get("duration_s", 10)
        return f"Will watch screen for {d} seconds and summarize changes"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        duration = float(params.get("duration_s", 10))
        if duration > 60:
            return ValidationResult.fail("Maximum watch duration is 60 seconds")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        duration = float(params.get("duration_s", 10))
        interval = float(params.get("interval_s", 3))
        focus = params.get("focus", "")
        t0 = time.monotonic()

        snapshots: list[str] = []
        n = max(2, int(duration / interval) + 1)

        for i in range(n):
            png_bytes, _ = await take_screenshot()
            if png_bytes:
                image_b64 = base64.b64encode(png_bytes).decode()
                brief_prompt = "In one sentence, describe what is visible on this screen right now."
                desc = await _ask_vision(image_b64, brief_prompt, timeout=15.0)
                snapshots.append(f"[t+{i * interval:.0f}s] {desc}")
            if i < n - 1:
                await asyncio.sleep(interval)

        if not snapshots:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(
                error="No screenshots could be captured", execution_time_ms=elapsed
            )

        # Final synthesis
        timeline = "\n".join(snapshots)
        focus_hint = f" Pay special attention to: {focus}." if focus else ""
        synthesis_prompt = (
            f"Here is a timeline of screen observations taken {interval}s apart:\n\n"
            f"{timeline}\n\n"
            f"Summarize what happened on screen during this observation window.{focus_hint}"
        )

        # Use text-only query for the synthesis (no image needed)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{_OLLAMA_URL}/api/chat",
                    json={
                        "model": "llama3",  # text model for synthesis
                        "messages": [{"role": "user", "content": synthesis_prompt}],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                summary = resp.json().get("message", {}).get("content", "\n".join(snapshots))
        except Exception:
            # Fallback: just return the raw timeline
            summary = timeline

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(
            output=summary,
            execution_time_ms=elapsed,
            snapshots=snapshots,
            frames_captured=len(snapshots),
            duration_s=duration,
        )
