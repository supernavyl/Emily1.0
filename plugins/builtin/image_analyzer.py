"""Built-in image analyzer tool using MiniCPM-V via Ollama."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from plugins.base import BaseTool, ExecutionContext, ToolResult


class ImageAnalyzerTool(BaseTool):
    """
    Analyze images or screenshots using the vision LLM (MiniCPM-V).

    Accepts a file path to an image and returns a description or
    answer to a question about the image.
    """

    name = "image_analyzer"
    description = (
        "Analyze an image or screenshot using the vision model (MiniCPM-V). "
        "Can describe images, answer questions about them, or extract text."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file to analyze.",
            },
            "prompt": {
                "type": "string",
                "description": "Question or instruction about the image. Default: 'Describe this image.'",
                "default": "Describe this image in detail.",
            },
        },
        "required": ["image_path"],
    }
    requires_approval = False
    timeout_seconds = 30

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
        self._ollama_url = ollama_url
        self._vision_model = vision_model

    async def dry_run(self, params: dict[str, Any]) -> str:
        return (
            f"Will analyze image at: {params.get('image_path', '')}\n"
            f"Prompt: {params.get('prompt', 'Describe this image.')}"
        )

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Send an image to the vision model for analysis.

        Args:
            params: Contains "image_path" and optional "prompt".
            context: Execution context.

        Returns:
            ToolResult with the vision model's response.
        """
        image_path = Path(params["image_path"])
        prompt = params.get("prompt", "Describe this image in detail.")

        if not image_path.exists():
            return ToolResult.fail(f"Image file not found: {image_path}")

        # Encode image as base64
        image_b64 = base64.b64encode(image_path.read_bytes()).decode()

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    f"{self._ollama_url}/api/chat",
                    json={
                        "model": self._vision_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                                "images": [image_b64],
                            }
                        ],
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            response_text = data.get("message", {}).get("content", "")
            return ToolResult.ok(response_text, model=self._vision_model)

        except httpx.ConnectError:
            return ToolResult.fail(f"Cannot connect to Ollama at {self._ollama_url}")
        except Exception as exc:
            return ToolResult.fail(str(exc))
