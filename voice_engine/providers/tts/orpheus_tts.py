"""Orpheus TTS provider — llama-cpp-python + SNAC, in-process, GPU-pinned.

Token format per Canopy Labs orpheus_tts_pypi/engine_class.py:
    input  = [128259] + tokenize(f"{voice}: {text}") + [128009, 128260, 128261, 128257]
    output = stream of token IDs; IDs >= 128266 are audio codes (id - 128266 = SNAC code)
    7 audio codes = 1 SNAC frame -> decoder -> 24 kHz PCM
"""

from __future__ import annotations

import asyncio
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
_ORPHEUS_START_TOKEN = 128259
_ORPHEUS_END_TOKENS = (128009, 128260, 128261, 128257)
_ORPHEUS_AUDIO_CODE_OFFSET = 128266
_ORPHEUS_STOP_TOKENS = frozenset({128258, 128262})
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

    def _build_input_ids(self, llm: Llama, text: str) -> list[int]:
        """Build the full token ID sequence per Canopy Labs Orpheus format."""
        adapted = f"{self._voice}: {text}"
        body_tokens = llm.tokenize(adapted.encode("utf-8"), add_bos=False, special=False)
        return [_ORPHEUS_START_TOKEN, *body_tokens, *_ORPHEUS_END_TOKENS]

    def _synthesize_sync(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.empty(0, dtype=np.float32)

        llm, decoder = self._ensure_loaded()
        input_ids = self._build_input_ids(llm, text)

        pcm_parts: list[np.ndarray] = []
        code_buffer: list[int] = []
        generated = 0

        for token_id in llm.generate(
            input_ids,
            temp=self._temperature,
            top_p=self._top_p,
            repeat_penalty=self._repetition_penalty,
            reset=True,
        ):
            generated += 1
            if token_id in _ORPHEUS_STOP_TOKENS:
                break
            if generated > self._max_tokens:
                break
            if token_id < _ORPHEUS_AUDIO_CODE_OFFSET:
                continue
            # Canopy Labs tokenization: each of the 7 positions in a frame uses
            # a separate SNAC codebook, offset by position * 4096.
            position = len(code_buffer)
            code = token_id - _ORPHEUS_AUDIO_CODE_OFFSET - (position * 4096)
            if code < 0 or code >= 4096:
                # Out-of-range — model emitted a token at the wrong position.
                # Skip to resync rather than crash SNAC.
                continue
            code_buffer.append(code)
            if len(code_buffer) == _CODES_PER_FRAME:
                pcm_parts.append(decoder.decode_frame([code_buffer]))
                code_buffer = []

        if not pcm_parts:
            logger.warning(
                "Orpheus produced no audio for: %r (generated %d tokens)",
                text[:60],
                generated,
            )
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
