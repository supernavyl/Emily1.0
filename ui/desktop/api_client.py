"""HTTP/SSE client for talking to Emily's FastAPI backend."""

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class EmilyAPIClient(QObject):
    """Async-friendly API client using Qt's network stack.

    All signals are emitted on the main thread, so widgets can connect directly.
    """

    # Chat streaming signals
    meta_received = Signal(dict)  # model info
    text_received = Signal(str)  # content chunk
    thinking_received = Signal(str)  # thinking chunk
    usage_received = Signal(dict)  # token counts + cost
    stream_error = Signal(str)  # error message
    stream_done = Signal()  # generation complete

    # Data fetch signals
    models_loaded = Signal(dict)
    skills_loaded = Signal(dict)
    health_received = Signal(dict)

    def __init__(self, base_url: str = "http://localhost:8000", parent: QObject | None = None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self._nam = QNetworkAccessManager(self)
        self._active_reply: QNetworkReply | None = None
        self._sse_buffer = ""

    # ------------------------------------------------------------------
    # Chat streaming (SSE)
    # ------------------------------------------------------------------

    def send_message(
        self,
        message: str,
        model_id: str = "auto",
        skill_id: str = "normal",
        messages: list[dict[str, str]] | None = None,
        conversation_id: str | None = None,
    ) -> None:
        """Start an SSE streaming chat request."""
        self.abort_stream()

        url = QUrl(f"{self.base_url}/api/v1/chat/stream")
        req = QNetworkRequest(url)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")

        payload = {
            "message": message,
            "model_id": model_id,
            "skill_id": skill_id,
            "messages": messages or [],
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        body = QByteArray(json.dumps(payload).encode())
        reply = self._nam.post(req, body)
        self._active_reply = reply
        self._sse_buffer = ""
        reply.readyRead.connect(self._on_sse_data)
        reply.finished.connect(self._on_sse_finished)
        reply.errorOccurred.connect(self._on_sse_error)

    def abort_stream(self) -> None:
        """Cancel any in-flight stream."""
        if self._active_reply and self._active_reply.isRunning():
            self._active_reply.abort()
        self._active_reply = None
        self._sse_buffer = ""

    def _on_sse_data(self) -> None:
        reply = self._active_reply
        if not reply:
            return
        raw = bytes(reply.readAll().data()).decode("utf-8", errors="replace")
        self._sse_buffer += raw

        while "\n\n" in self._sse_buffer:
            block, self._sse_buffer = self._sse_buffer.split("\n\n", 1)
            self._parse_sse_block(block)

    def _parse_sse_block(self, block: str) -> None:
        event_type = ""
        data_lines: list[str] = []
        for line in block.strip().splitlines():
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_lines.append(line[6:])
            elif line.startswith("data:"):
                data_lines.append(line[5:])

        if not data_lines:
            return

        raw_data = "\n".join(data_lines)
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            return

        if event_type == "meta":
            self.meta_received.emit(data)
        elif event_type == "text":
            self.text_received.emit(data.get("text", ""))
        elif event_type == "thinking":
            self.thinking_received.emit(data.get("text", ""))
        elif event_type == "usage":
            self.usage_received.emit(data)
        elif event_type == "error":
            self.stream_error.emit(data.get("message", "Unknown error"))
        elif event_type == "done":
            self.stream_done.emit()

    def _on_sse_finished(self) -> None:
        # Process any remaining buffer
        if self._sse_buffer.strip():
            self._parse_sse_block(self._sse_buffer)
            self._sse_buffer = ""
        self._active_reply = None

    def _on_sse_error(self, code: QNetworkReply.NetworkError) -> None:
        if code == QNetworkReply.NetworkError.OperationCanceledError:
            return  # User aborted
        reply = self._active_reply
        msg = reply.errorString() if reply else f"Network error: {code}"
        self.stream_error.emit(msg)

    # ------------------------------------------------------------------
    # REST endpoints
    # ------------------------------------------------------------------

    def fetch_models(self) -> None:
        url = QUrl(f"{self.base_url}/api/v1/models")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_json_reply(reply, self.models_loaded))

    def fetch_skills(self) -> None:
        url = QUrl(f"{self.base_url}/api/v1/skills")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_json_reply(reply, self.skills_loaded))

    def fetch_health(self) -> None:
        url = QUrl(f"{self.base_url}/health")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_json_reply(reply, self.health_received))

    def _handle_json_reply(self, reply: QNetworkReply, signal: Signal) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            return
        raw = bytes(reply.readAll().data()).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            signal.emit(data)
        except json.JSONDecodeError:
            pass
        reply.deleteLater()
