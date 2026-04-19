"""Orpheus TTS provider — llama-cpp-python + SNAC, in-process, GPU-pinned."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import numpy as np
from llama_cpp import Llama  # type: ignore[import-untyped]

from observability.logger import get_logger
from voice_engine.providers.base import TTSProvider
from voice_engine.providers.tts.snac_stream_decoder import SNACStreamDecoder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = get_logger(__name__)

ORPHEUS_SAMPLE_RATE = 24000
_AUDIO_CODE_RE = re.compile(r"<\|audio_code:(\d+)\|>")
_EOT_TOKEN = "<|eot|>"
_VALID_VOICES = frozenset({"tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe"})
_CODES_PER_FRAME = 7


class OrpheusTTS(TTSProvider):
    """Orpheus 3B GGUF inference (llama-cpp-python) with SNAC decoding."""

    def __init__(
        self,
        model_path: str,
        voice: str = "tara",
        main_gpu: int = 1,
        n_gpu_layers: int = -1,
        temperature: float = 0.6,
        top_p: float = 0.9,
        repetition_penalty: float = 1.1,
        max_tokens: int = 1200,
        snac_device: str = "cuda:1",
        n_ctx: int = 2048,
    ) -> None:
        if voice not in _VALID_VOICES:
            logger.warning("Unknown Orpheus voice %r; falling back to 'tara'", voice)
            voice = "tara"

        self._model_path = model_path
        self._voice = voice
        self._main_gpu = main_gpu
        self._n_gpu_layers = n_gpu_layers
        self._temperature = temperature
        self._top_p = top_p
        self._repetition_penalty = repetition_penalty
        self._max_tokens = max_tokens
        self._snac_device = snac_device
        self._n_ctx = n_ctx

        self._llm: Llama | None = None
        self._decoder: SNACStreamDecoder | None = None
        logger.info(
            "OrpheusTTS configured: voice=%s main_gpu=%d snac=%s model=%s",
            voice,
            main_gpu,
            snac_device,
            model_path,
        )

    def set_voice(self, voice: str) -> None:
        if voice in _VALID_VOICES:
            self._voice = voice
            logger.info("OrpheusTTS voice changed to %s", voice)
        else:
            logger.warning("Ignoring unknown Orpheus voice: %s", voice)

    def _ensure_loaded(self) -> tuple[Llama, SNACStreamDecoder]:
        if self._llm is None:
            logger.info("Loading Orpheus GGUF: %s (main_gpu=%d)", self._model_path, self._main_gpu)
            self._llm = Llama(
                model_path=self._model_path,
                n_gpu_layers=self._n_gpu_layers,
                main_gpu=self._main_gpu,
                n_ctx=self._n_ctx,
                logits_all=False,
                verbose=False,
            )
            logger.info("Orpheus GGUF loaded.")
        if self._decoder is None:
            self._decoder = SNACStreamDecoder(device=self._snac_device)
        return self._llm, self._decoder

    def _build_prompt(self, text: str) -> str:
        return f"<custom_token_3><|audio|>{self._voice}: {text}<|eot|>"

    def _synthesize_sync(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.empty(0, dtype=np.float32)

        llm, decoder = self._ensure_loaded()
        prompt = self._build_prompt(text)

        stream = llm.create_completion(
            prompt=prompt,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            top_p=self._top_p,
            repeat_penalty=self._repetition_penalty,
            stream=True,
            stop=[_EOT_TOKEN],
        )

        pcm_parts: list[np.ndarray] = []
        code_buffer: list[int] = []
        for chunk in stream:
            piece = chunk["choices"][0]["text"] or ""
            if _EOT_TOKEN in piece:
                break
            for match in _AUDIO_CODE_RE.finditer(piece):
                code_buffer.append(int(match.group(1)))
                if len(code_buffer) == _CODES_PER_FRAME:
                    pcm_parts.append(decoder.decode_frame([code_buffer]))
                    code_buffer = []

        if not pcm_parts:
            logger.warning("Orpheus produced no audio for: %s", text[:60])
            return np.empty(0, dtype=np.float32)

        return np.concatenate(pcm_parts)

    async def synthesize(self, text: str) -> np.ndarray:
        if not text.strip():
            return np.empty(0, dtype=np.float32)
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, self._synthesize_sync, text)
        logger.debug("Orpheus synthesized %d samples for: %s", len(audio), text[:60])
        return audio

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
    ) -> AsyncIterator[np.ndarray]:
        async for text in text_chunks:
            if not text.strip():
                continue
            audio = await self.synthesize(text)
            if len(audio) > 0:
                yield audio
