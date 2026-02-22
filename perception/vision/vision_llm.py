"""
Vision LLM integration — MiniCPM-V 2.6 via Ollama.

Provides async wrappers for common vision tasks:
- Scene description
- Text/code extraction (OCR)
- Emotional state inference from face frame
- UI element detection for screen understanding
"""

from __future__ import annotations

import asyncio
from typing import Any

from llm.client import ChatMessage, OllamaClient
from observability.logger import get_logger

log = get_logger(__name__)


class VisionAnalyzer:
    """
    Async vision analysis using MiniCPM-V 2.6.

    All methods accept base64-encoded image strings and return structured analysis.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        vision_model: str = "minicpm-v:2.6",
    ) -> None:
        """
        Args:
            ollama_url: Ollama base URL.
            vision_model: Vision model name in Ollama.
        """
        self._client = OllamaClient(base_url=ollama_url)
        self._model = vision_model

    async def describe_scene(self, image_b64: str, detail_level: str = "medium") -> str:
        """
        Generate a scene description from an image.

        Args:
            image_b64: Base64-encoded image string.
            detail_level: "brief", "medium", or "detailed".

        Returns:
            Scene description string.
        """
        detail_map = {
            "brief": "In one sentence, describe what you see.",
            "medium": "Describe the scene in 2-3 sentences.",
            "detailed": "Provide a detailed description of everything in this image.",
        }
        prompt = detail_map.get(detail_level, detail_map["medium"])
        return await self._query(image_b64, prompt)

    async def extract_text(self, image_b64: str) -> str:
        """
        Extract all visible text from an image (OCR).

        Args:
            image_b64: Base64-encoded image string.

        Returns:
            All text found in the image.
        """
        return await self._query(
            image_b64,
            "Extract all visible text from this image. Return only the text, preserving formatting."
        )

    async def analyze_screen(self, screenshot_b64: str) -> dict[str, Any]:
        """
        Analyze a desktop screenshot for active application and content.

        Args:
            screenshot_b64: Base64-encoded screenshot.

        Returns:
            Dict with "active_app", "content_type", "summary", "text_content".
        """
        prompt = (
            "Analyze this desktop screenshot. Respond with JSON:\n"
            '{"active_app": "...", "content_type": "...", "summary": "...", "text_content": "..."}'
        )
        response = await self._query(screenshot_b64, prompt)
        from llm.structured_output import extract_json
        parsed = extract_json(response)
        if parsed:
            return parsed
        return {"summary": response, "active_app": "unknown", "content_type": "unknown", "text_content": ""}

    async def infer_emotion(self, face_image_b64: str) -> dict[str, float]:
        """
        Infer emotional state from a face image.

        Args:
            face_image_b64: Base64-encoded image containing a face.

        Returns:
            Dict of {emotion: confidence_score}.
        """
        prompt = (
            "Look at the face in this image. What emotion does the person appear to show? "
            "Respond with JSON: {\"primary_emotion\": \"...\", \"confidence\": 0.0-1.0, "
            "\"secondary_emotions\": [\"...\"]}"
        )
        response = await self._query(face_image_b64, prompt)
        from llm.structured_output import extract_json
        parsed = extract_json(response)
        if parsed:
            return {"primary": parsed.get("primary_emotion", "neutral"), "confidence": parsed.get("confidence", 0.5)}
        return {"primary": "neutral", "confidence": 0.5}

    async def _query(self, image_b64: str, prompt: str) -> str:
        """
        Send a vision query to the Ollama model.

        Args:
            image_b64: Base64-encoded image string.
            prompt: Text prompt.

        Returns:
            Model response text.
        """
        try:
            result = await self._client.chat(
                model=self._model,
                messages=[ChatMessage(role="user", content=prompt, images=[image_b64])],
                model_tier="vision",
            )
            return result.content
        except Exception as exc:
            log.error("vision_query_error", error=str(exc))
            return ""
