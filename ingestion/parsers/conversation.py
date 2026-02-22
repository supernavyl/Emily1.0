"""
Conversation transcript parser.

Converts Emily session transcripts (stored in data/transcripts/) into
ParsedDocument objects for feeding to the ExtractionPipeline. Handles
both the plain-text format written by EpisodicMemory and JSON transcripts
from the API.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class ParsedTranscript:
    """A parsed conversation transcript ready for entity extraction."""

    session_id: str = ""
    full_text: str = ""           # Concatenated speaker turns
    raw_turns: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.raw_turns is None:
            self.raw_turns = []


async def parse_transcript_file(path: Path) -> ParsedTranscript:
    """
    Parse a transcript file (plain text or JSON) into a ParsedTranscript.

    Plain-text format (one utterance per line):
        Emily: Hello, how can I help?
        User: I need to schedule a meeting with Alice.

    JSON format (list of {"role": str, "content": str}):
        [{"role": "assistant", "content": "..."}, ...]

    Args:
        path: Path to the transcript file.

    Returns:
        ParsedTranscript object.
    """
    session_id = path.stem  # filename without extension = session UUID
    raw = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")

    transcript = ParsedTranscript(session_id=session_id)

    if raw.strip().startswith("["):
        # JSON transcript
        try:
            turns = json.loads(raw)
            transcript.raw_turns = turns
            transcript.full_text = "\n".join(
                f"{t.get('role', 'unknown').title()}: {t.get('content', '')}"
                for t in turns
            )
        except json.JSONDecodeError:
            transcript.full_text = raw
    else:
        # Plain text transcript
        transcript.full_text = raw
        lines = raw.strip().splitlines()
        for line in lines:
            if ": " in line:
                role, _, content = line.partition(": ")
                transcript.raw_turns.append({"role": role.lower(), "content": content})
            else:
                transcript.raw_turns.append({"role": "unknown", "content": line})

    log.info(
        "transcript_parsed",
        session_id=session_id,
        turns=len(transcript.raw_turns),
        chars=len(transcript.full_text),
    )
    return transcript
