"""LlamaCpp provider — in-process GGUF inference for the desktop chat.

Lists GGUF models from the main Emily config (config.yaml) and optionally
scans the models directory. Streams via llama-cpp-python in a thread-pool
executor. Optional dependency: llama-cpp-python is in gpu-cuda extra.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from emily_chat.models.providers.base import BaseProvider
from emily_chat.models.registry import ModelSpec
from emily_chat.models.streaming_engine import (
    ChunkType,
    GenerationSettings,
    StreamChunk,
)

logger = logging.getLogger(__name__)

_SENTINEL = object()


def _find_config_path() -> Path | None:
    """Return path to main Emily config.yaml, or None if not found."""
    import os

    env_path = os.environ.get("EMILY_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
    cwd = Path.cwd() / "config.yaml"
    if cwd.exists():
        return cwd
    # Assume emily_chat/models/providers/llamacpp.py -> project root 3 levels up
    root = Path(__file__).resolve().parents[3] / "config.yaml"
    if root.exists():
        return root
    return None


def load_llamacpp_config() -> tuple[str, dict[str, dict[str, Any]]] | None:
    """Load llm.llamacpp section from config.yaml.

    Returns:
        (models_dir, models_dict) or None if config missing/disabled.
        models_dict maps tier name to {filename, n_gpu_layers, n_ctx, n_batch, alias_of?}.
    """
    path = _find_config_path()
    if not path:
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text()) or {}
        llm = data.get("llm") or {}
        lc = llm.get("llamacpp") or {}
        if not lc.get("enabled", True):
            return None
        models_dir = lc.get("models_dir", "models")
        models_raw = lc.get("models") or {}
        models: dict[str, dict[str, Any]] = {}
        for tier, cfg in models_raw.items():
            if isinstance(cfg, dict):
                models[tier] = {
                    "filename": cfg.get("filename", ""),
                    "n_gpu_layers": cfg.get("n_gpu_layers", -1),
                    "n_ctx": cfg.get("n_ctx", 8192),
                    "n_batch": cfg.get("n_batch", 512),
                    "alias_of": cfg.get("alias_of"),
                }
            else:
                models[tier] = {
                    "filename": "",
                    "n_gpu_layers": -1,
                    "n_ctx": 8192,
                    "n_batch": 512,
                    "alias_of": None,
                }
        return (models_dir, models)
    except Exception as e:
        logger.warning("llamacpp_config_load_failed", path=str(path), error=str(e))
        return None


def list_gguf_models() -> list[tuple[str, ModelSpec]]:
    """List GGUF models from config and optionally scan models_dir.

    Returns:
        List of (registry_key, ModelSpec) for each available model.
    """
    result: list[tuple[str, ModelSpec]] = []
    cfg = load_llamacpp_config()
    if not cfg:
        return result
    models_dir_str, models_dict = cfg
    models_dir = Path(models_dir_str)
    if not models_dir.is_absolute():
        config_dir = _find_config_path()
        base = config_dir.parent if config_dir else Path.cwd()
        models_dir = base / models_dir_str
    seen_filenames: set[str] = set()
    for tier, opts in models_dict.items():
        if opts.get("alias_of"):
            continue
        filename = opts.get("filename", "")
        if not filename:
            continue
        gguf_path = models_dir / filename
        if not gguf_path.exists():
            logger.debug("llamacpp_gguf_skip_missing", tier=tier, path=str(gguf_path))
            continue
        seen_filenames.add(filename)
        display = f"Emily — Local GGUF ({tier})"
        spec = ModelSpec(
            display=display,
            provider="llamacpp",
            model_id=tier,
            input_usd=0.0,
            output_usd=0.0,
            speed="hardware-dependent",
            tier="local",
            notes=f"llama.cpp tier: {tier}. 100% local.",
        )
        result.append((f"llamacpp-{tier}", spec))
    try:
        for gguf in models_dir.glob("*.gguf"):
            if gguf.name in seen_filenames:
                continue
            stem = gguf.stem
            key = f"llamacpp-file-{stem}"
            spec = ModelSpec(
                display=f"Emily — Local GGUF ({stem})",
                provider="llamacpp",
                model_id=str(gguf.resolve()),
                input_usd=0.0,
                output_usd=0.0,
                speed="hardware-dependent",
                tier="local",
                notes=f"Discovered GGUF: {gguf.name}",
            )
            result.append((key, spec))
    except Exception as e:
        logger.debug("llamacpp_scan_dir_failed", path=str(models_dir), error=str(e))
    return result


class LlamaCppProvider(BaseProvider):
    """In-process GGUF streaming via llama-cpp-python.

    Loads models on first use and caches by tier/path. Requires
    llama-cpp-python (e.g. from gpu-cuda extra).
    """

    def __init__(
        self,
        models_dir: str = "models",
        models: dict[str, dict[str, Any]] | None = None,
        config_base_path: Path | None = None,
    ) -> None:
        """
        Args:
            models_dir: Directory containing GGUF files.
            models: Tier -> {filename, n_gpu_layers, n_ctx, n_batch}. If None, loaded from config.
            config_base_path: Base path for resolving models_dir if relative.
        """
        if models is not None:
            self._models_dir = Path(models_dir)
            self._models = models
        else:
            cfg = load_llamacpp_config()
            if cfg:
                md, m = cfg
                self._models_dir = Path(md)
                if not self._models_dir.is_absolute() and config_base_path:
                    self._models_dir = config_base_path / md
                elif not self._models_dir.is_absolute():
                    root = _find_config_path()
                    base = root.parent if root else Path.cwd()
                    self._models_dir = base / md
                self._models = m
            else:
                self._models_dir = Path(models_dir)
                self._models = {}
        self._cache: dict[str, Any] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def _get_or_load_llama(self, model_id: str) -> Any:
        """Load and cache a Llama instance by tier or path."""
        if model_id in self._cache:
            return self._cache[model_id]
        try:
            from llama_cpp import Llama  # type: ignore[import-untyped]
        except ImportError:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                "Install with: uv sync --extra gpu-cuda (or pip install llama-cpp-python)"
            )
        if model_id in self._models:
            opts = self._models[model_id]
            alias = opts.get("alias_of")
            if alias and alias in self._cache:
                self._cache[model_id] = self._cache[alias]
                return self._cache[model_id]
            if alias:
                await self._get_or_load_llama(alias)
                self._cache[model_id] = self._cache[alias]
                return self._cache[model_id]
            filename = opts.get("filename", "")
            path = self._models_dir / filename
            n_gpu_layers = opts.get("n_gpu_layers", -1)
            n_ctx = opts.get("n_ctx", 8192)
            n_batch = opts.get("n_batch", 512)
        else:
            path = Path(model_id)
            if not path.exists():
                raise FileNotFoundError(f"GGUF path not found: {model_id}")
            n_gpu_layers = -1
            n_ctx = 8192
            n_batch = 512
        loop = asyncio.get_running_loop()
        model = await loop.run_in_executor(
            None,
            lambda: Llama(
                model_path=str(path),
                n_gpu_layers=n_gpu_layers,
                n_ctx=n_ctx,
                n_batch=n_batch,
                verbose=False,
            ),
        )
        self._cache[model_id] = model
        return model

    async def stream(
        self,
        messages: list[dict],
        system_prompt: str,
        settings: GenerationSettings,
        model_spec: ModelSpec,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion from the in-process GGUF model."""
        model_id = model_spec.model_id
        llm = await self._get_or_load_llama(model_id)
        full_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            *[{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
        ]
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=64)
        loop = asyncio.get_running_loop()

        def _run() -> None:
            try:
                for chunk in llm.create_chat_completion(
                    messages=full_messages,
                    temperature=settings.temperature,
                    top_p=settings.top_p,
                    max_tokens=settings.max_tokens if settings.max_tokens > 0 else 4096,
                    repeat_penalty=1.1,
                    stream=True,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except BaseException as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(e)))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

        loop.run_in_executor(None, _run)
        prompt_tokens = 0
        completion_tokens = 0
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, tuple) and item[0] == "error":
                yield StreamChunk(type=ChunkType.ERROR, content=item[1])
                return
            delta = item.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield StreamChunk(type=ChunkType.TEXT, content=content)
            finish = item.get("choices", [{}])[0].get("finish_reason")
            if item.get("usage"):
                prompt_tokens = item["usage"].get("prompt_tokens", 0)
                completion_tokens = item["usage"].get("completion_tokens", 0)
            if finish is not None:
                break
        yield StreamChunk(
            type=ChunkType.USAGE,
            tokens=completion_tokens,
            metadata={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
            },
        )
        yield StreamChunk(type=ChunkType.STOP)

    def validate_key(self, api_key: str) -> bool:
        """No API key required for local inference."""
        return True

    async def close(self) -> None:
        """Unload all cached models."""
        for _key, llm in list(self._cache.items()):
            try:
                if hasattr(llm, "close"):
                    llm.close()
            except Exception:
                pass
        self._cache.clear()
