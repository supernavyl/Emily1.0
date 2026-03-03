"""
Ingestion coordinator — routes files to the correct parser and feeds results
through the ExtractionPipeline into the knowledge store.

Watched directories (via watchdog):
  knowledge/       — PDFs, text, markdown
  inbox/contacts/  — .vcf vCard files
  inbox/calendar/  — .ics iCalendar files
  data/transcripts/— conversation transcripts

The coordinator can be used in two modes:
1. One-shot: call ingest_path() or ingest_directory() directly.
2. Watch mode: call start_watching() to react to filesystem events in real time.

All ingestion is funnelled through ExtractionPipeline so deduplication and
fact validation are always applied.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from extraction.pipeline import ExtractionPipeline, ExtractionResult
from ingestion.parsers.conversation import parse_transcript_file
from ingestion.parsers.ical import parse_ical_file
from ingestion.parsers.pdf import parse_pdf, parse_text_file
from ingestion.parsers.vcard import parse_vcard_file
from memory.knowledge_models import (
    EntityRecord,
    EventRecord,
    PersonRecord,
)
from memory.knowledge_store import KnowledgeStore
from observability.logger import get_logger

log = get_logger(__name__)

# Supported file extensions and their parser type
_EXTENSION_MAP: dict[str, str] = {
    ".vcf": "vcard",
    ".ics": "ical",
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "text",
    ".markdown": "text",
    ".json": "conversation",  # transcript JSON
}


class IngestionCoordinator:
    """
    Routes files to parsers and feeds extracted content to the knowledge store.

    Uses ExtractionPipeline for entity extraction so all knowledge flows
    through the same deduplication and confidence-filtering logic.
    """

    def __init__(
        self,
        pipeline: ExtractionPipeline,
        store: KnowledgeStore,
    ) -> None:
        """
        Args:
            pipeline: Connected ExtractionPipeline for LLM-based extraction.
            store: Connected KnowledgeStore for persistence.
        """
        self._pipeline = pipeline
        self._store = store
        self._watcher: Any = None

    async def ingest_path(self, path: Path) -> ExtractionResult | None:
        """
        Ingest a single file into the knowledge store.

        Args:
            path: Path to the file to ingest.

        Returns:
            ExtractionResult summary, or None if the file type is unsupported.
        """
        suffix = path.suffix.lower()
        parser_type = _EXTENSION_MAP.get(suffix)

        if parser_type is None:
            log.warning("unsupported_file_type", path=str(path), suffix=suffix)
            return None

        session_id = str(uuid.uuid4())
        log.info("ingesting_file", path=str(path), type=parser_type, session=session_id)

        try:
            if parser_type == "vcard":
                return await self._ingest_vcard(path, session_id)
            elif parser_type == "ical":
                return await self._ingest_ical(path, session_id)
            elif parser_type == "pdf":
                return await self._ingest_document(path, session_id, is_pdf=True)
            elif parser_type == "text":
                return await self._ingest_document(path, session_id, is_pdf=False)
            elif parser_type == "conversation":
                return await self._ingest_transcript(path, session_id)
        except Exception as exc:
            log.error("ingestion_error", path=str(path), error=str(exc))
            return None

    async def ingest_directory(
        self,
        directory: Path,
        recursive: bool = False,
    ) -> list[ExtractionResult]:
        """
        Ingest all supported files in a directory.

        Args:
            directory: Directory to scan.
            recursive: If True, scan subdirectories recursively.

        Returns:
            List of ExtractionResult objects (one per successfully ingested file).
        """
        pattern = "**/*" if recursive else "*"
        results = []

        for path in directory.glob(pattern):
            if not path.is_file():
                continue
            result = await self.ingest_path(path)
            if result:
                results.append(result)

        log.info(
            "directory_ingested",
            directory=str(directory),
            files_processed=len(results),
        )
        return results

    def start_watching(
        self,
        watch_dirs: list[Path],
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """
        Start watchdog file-system observer to auto-ingest new files.

        Args:
            watch_dirs: Directories to watch for new files.
            loop: Event loop to schedule async ingest calls into.
        """
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            coordinator = self

            class _Handler(FileSystemEventHandler):
                def on_created(self, event: Any) -> None:
                    if event.is_directory:
                        return
                    path = Path(event.src_path)
                    if path.suffix.lower() not in _EXTENSION_MAP:
                        return
                    _loop = loop or asyncio.get_event_loop()
                    _loop.call_soon_threadsafe(
                        asyncio.ensure_future,
                        coordinator.ingest_path(path),
                    )
                    log.info("watchdog_file_detected", path=str(path))

            observer = Observer()
            for watch_dir in watch_dirs:
                watch_dir.mkdir(parents=True, exist_ok=True)
                observer.schedule(_Handler(), str(watch_dir), recursive=True)

            observer.start()
            self._watcher = observer
            log.info("watchdog_started", dirs=[str(d) for d in watch_dirs])

        except ImportError:
            log.warning("watchdog_not_available")

    def stop_watching(self) -> None:
        """Stop the watchdog observer if running."""
        if self._watcher:
            self._watcher.stop()
            self._watcher.join()
            self._watcher = None
            log.info("watchdog_stopped")

    # ------------------------------------------------------------------
    # Private ingestion methods
    # ------------------------------------------------------------------

    async def _ingest_vcard(self, path: Path, session_id: str) -> ExtractionResult:
        """Import contacts from a vCard file."""
        contacts = await parse_vcard_file(path)
        combined_result = ExtractionResult(session_id=session_id)

        for contact in contacts:
            # Create entity + person directly (no LLM needed for structured vCard data)
            entity = EntityRecord(
                canonical_name=contact.full_name,
                type="person",
                source_ids=[session_id],
            )
            await self._store.upsert_entity(entity)

            person = PersonRecord(
                entity_id=entity.id,
                full_name=contact.full_name,
                email_addresses=contact.email_addresses,
                phone_numbers=contact.phone_numbers,
                employer=contact.organization,
                occupation=contact.title,
                home_location=contact.home_location,
                work_location=contact.work_location,
                notes=contact.notes,
                important_dates=({"birthday": contact.birthday} if contact.birthday else {}),
            )
            await self._store.upsert_person(person)
            combined_result.entities_created += 1

            # Run LLM extraction on the raw text for any additional facts
            if contact.raw_text:
                sub_result = await self._pipeline.process(
                    contact.raw_text,
                    session_id=session_id,
                    auto_confirm_low_confidence=True,
                )
                combined_result.facts_created += sub_result.facts_created

        log.info(
            "vcard_ingestion_complete",
            session=session_id,
            contacts=len(contacts),
        )
        return combined_result

    async def _ingest_ical(self, path: Path, session_id: str) -> ExtractionResult:
        """Import events from an iCalendar file."""
        events = await parse_ical_file(path)
        result = ExtractionResult(session_id=session_id)

        for parsed in events:
            event = EventRecord(
                title=parsed.title,
                event_type=parsed.event_type,
                datetime=parsed.datetime_str,
                duration_minutes=parsed.duration_minutes,
                location=parsed.location,
                description=parsed.description,
                action_items=[],
                source_id=session_id,
            )
            await self._store.upsert_event(event)
            result.entities_created += 1  # repurpose as event count

            # Extract entities from description/attendees
            if parsed.raw_text:
                sub = await self._pipeline.process(parsed.raw_text, session_id=session_id)
                result.facts_created += sub.facts_created

        log.info("ical_ingestion_complete", session=session_id, events=len(events))
        return result

    async def _ingest_document(
        self,
        path: Path,
        session_id: str,
        is_pdf: bool,
    ) -> ExtractionResult:
        """Extract entities from a PDF or text document."""
        if is_pdf:
            doc = await parse_pdf(path)
        else:
            doc = await parse_text_file(path)

        if not doc.full_text.strip():
            return ExtractionResult(session_id=session_id)

        # Chunk large documents to stay within LLM context window
        text = doc.full_text
        chunk_size = 4000
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

        combined = ExtractionResult(session_id=session_id)
        for chunk in chunks:
            sub = await self._pipeline.process(chunk, session_id=session_id)
            combined.entities_created += sub.entities_created
            combined.entities_merged += sub.entities_merged
            combined.relationships_created += sub.relationships_created
            combined.facts_created += sub.facts_created

        log.info("document_ingested", path=str(path), chunks=len(chunks))
        return combined

    async def _ingest_transcript(self, path: Path, session_id: str) -> ExtractionResult:
        """Extract entities from a conversation transcript."""
        transcript = await parse_transcript_file(path)
        if not transcript.full_text.strip():
            return ExtractionResult(session_id=session_id)

        result = await self._pipeline.process(
            transcript.full_text,
            session_id=transcript.session_id or session_id,
        )
        log.info("transcript_ingested", session=session_id)
        return result
