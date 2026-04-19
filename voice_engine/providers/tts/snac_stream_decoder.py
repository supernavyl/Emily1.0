"""SNAC neural codec wrapper for streaming Orpheus TTS audio decoding.

Orpheus emits 7 SNAC code tokens per audio frame across 3 hierarchical
codebooks. We accept one full frame at a time, feed it to the SNAC model,
and return float32 PCM samples at 24 kHz.
"""

from __future__ import annotations

import numpy as np
import torch
from snac import SNAC  # type: ignore[import-untyped]

from observability.logger import get_logger

logger = get_logger(__name__)

SNAC_SAMPLE_RATE = 24000
SNAC_MODEL_ID = "hubertsiuzdak/snac_24khz"
CODES_PER_FRAME = 7


class SNACStreamDecoder:
    """Decode Orpheus SNAC audio token frames to 24 kHz float32 PCM."""

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self.sample_rate = SNAC_SAMPLE_RATE
        logger.info("Loading SNAC model '%s' on %s ...", SNAC_MODEL_ID, device)
        self._model = SNAC.from_pretrained(SNAC_MODEL_ID).to(device).eval()
        logger.info("SNAC model ready on %s.", device)

    def decode_frame(self, codes: list[list[int]]) -> np.ndarray:
        """Decode one or more 7-token SNAC frames to PCM.

        Args:
            codes: A list of frames; each frame is a list of 7 integers from
                the SNAC codebook (as emitted by Orpheus).

        Returns:
            Float32 1-D PCM array at 24 kHz.
        """
        if not codes:
            return np.empty(0, dtype=np.float32)

        level_0: list[int] = []
        level_1: list[int] = []
        level_2: list[int] = []
        for frame in codes:
            if len(frame) != CODES_PER_FRAME:
                msg = f"expected 7 codes per frame, got {len(frame)}"
                raise ValueError(msg)
            level_0.append(frame[0])
            level_1.extend([frame[1], frame[4]])
            level_2.extend([frame[2], frame[3], frame[5], frame[6]])

        t0 = torch.tensor([level_0], dtype=torch.int32, device=self.device)
        t1 = torch.tensor([level_1], dtype=torch.int32, device=self.device)
        t2 = torch.tensor([level_2], dtype=torch.int32, device=self.device)

        with torch.inference_mode():
            audio = self._model.decode([t0, t1, t2])

        return audio.squeeze().detach().cpu().numpy().astype(np.float32)

    def reset(self) -> None:
        """SNAC is stateless per-frame; placeholder for future streaming state."""
        return
