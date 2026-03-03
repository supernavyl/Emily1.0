"""Built-in singing and music generation tool for Emily."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from config import SingingConfig, get_settings
from observability.logger import get_logger
from plugins.base import BaseTool, ExecutionContext, ToolResult, ValidationResult
from voice.singing import SingingManager

log = get_logger(__name__)


class SingingTool(BaseTool):
    """Generate music, convert singing voice, or create full songs.

    Modes:
      - ``generate``       — create instrumental music from a text prompt (MusicGen)
      - ``voice_convert``  — convert input audio to Emily's singing voice (RVC)
      - ``full_song``      — generate a complete song with vocals (Suno API)
    """

    name = "sing"
    description = (
        "Generate music or sing a song. "
        "Supports text-to-music generation, singing voice conversion, "
        "and full song creation with vocals and instruments."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "What to sing or generate — lyrics, description, or style prompt.",
            },
            "style": {
                "type": "string",
                "description": "Music style hint (e.g. pop, jazz, lo-fi, classical).",
            },
            "duration_seconds": {
                "type": "integer",
                "description": "Target duration in seconds. Default: 30.",
                "default": 30,
            },
            "mode": {
                "type": "string",
                "enum": ["generate", "voice_convert", "full_song"],
                "description": (
                    "generate = instrumental music from prompt, "
                    "voice_convert = convert input audio to Emily's voice, "
                    "full_song = complete song with vocals via cloud API."
                ),
                "default": "generate",
            },
            "input_audio_path": {
                "type": "string",
                "description": "Path to input audio file (required for voice_convert mode).",
            },
        },
        "required": ["prompt"],
    }
    requires_approval = False
    timeout_seconds = 180

    def __init__(self, singing_config: SingingConfig | None = None) -> None:
        self._config = singing_config or get_settings().singing
        self._manager: SingingManager | None = None
        self._loaded = False

    async def _ensure_loaded(self) -> SingingManager:
        """Lazy-load the singing manager on first use."""
        if self._manager is None:
            self._manager = SingingManager(self._config)
        if not self._loaded:
            await self._manager.load()
            self._loaded = True
        return self._manager

    async def dry_run(self, params: dict[str, Any]) -> str:
        """Describe what this tool would do without executing.

        Args:
            params: Tool parameters.

        Returns:
            Human-readable description.
        """
        mode = params.get("mode", "generate")
        prompt = params.get("prompt", "")
        style = params.get("style")
        duration = params.get("duration_seconds", 30)

        descriptions = {
            "generate": f'Generate {duration}s of instrumental music: "{prompt}"'
            + (f" in {style} style" if style else ""),
            "voice_convert": f'Convert audio to Emily\'s singing voice: "{prompt}"',
            "full_song": f'Generate a full song with vocals: "{prompt}"'
            + (f" in {style} style" if style else ""),
        }
        return descriptions.get(mode, f'Generate music: "{prompt}"')

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        """Validate parameters before execution.

        Args:
            params: Tool parameters.

        Returns:
            ValidationResult with any errors.
        """
        base = await super().validate(params)
        if not base.valid:
            return base

        mode = params.get("mode", "generate")
        if mode not in {"generate", "voice_convert", "full_song"}:
            return ValidationResult.fail(
                f"Invalid mode: {mode}. Must be generate, voice_convert, or full_song."
            )

        if mode == "voice_convert":
            audio_path = params.get("input_audio_path")
            if not audio_path:
                return ValidationResult.fail("voice_convert mode requires input_audio_path.")
            if not Path(audio_path).exists():
                return ValidationResult.fail(f"Input audio file not found: {audio_path}")

        duration = params.get("duration_seconds", 30)
        if isinstance(duration, int) and (duration < 1 or duration > 300):
            return ValidationResult.fail("duration_seconds must be between 1 and 300.")

        return ValidationResult.ok()

    async def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Execute the singing/music generation tool.

        Args:
            params: Tool parameters.
            context: Execution context.

        Returns:
            ToolResult containing the generated audio info.
        """
        t0 = time.monotonic()

        prompt: str = params["prompt"]
        style: str | None = params.get("style")
        duration: int = params.get("duration_seconds", 30)
        mode: str = params.get("mode", "generate")
        input_audio: str | None = params.get("input_audio_path")

        try:
            manager = await self._ensure_loaded()

            chunks: list[bytes] = []
            async for chunk in manager.sing(
                prompt,
                style=style,
                duration_seconds=duration,
                mode=mode,
                input_audio_path=input_audio,
            ):
                chunks.append(chunk)

            total_bytes = sum(len(c) for c in chunks)
            total_samples = total_bytes // 2
            duration_actual = total_samples / 24_000

            output_dir = Path(self._config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"emily_song_{int(time.time())}.pcm"
            await asyncio.to_thread(output_path.write_bytes, b"".join(chunks))

            elapsed = (time.monotonic() - t0) * 1000.0
            return ToolResult.ok(
                output={
                    "status": "completed",
                    "mode": mode,
                    "prompt": prompt,
                    "style": style,
                    "duration_seconds": round(duration_actual, 1),
                    "output_path": str(output_path),
                    "total_bytes": total_bytes,
                    "sample_rate": 24_000,
                    "format": "int16_pcm",
                },
                execution_time_ms=elapsed,
                engine_used=mode,
            )

        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000.0
            log.error("singing_tool_failed", error=str(exc)[:200])
            return ToolResult.fail(str(exc), execution_time_ms=elapsed)
