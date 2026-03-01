"""
Emily FastAPI web application — full dashboard + API.

Provides:
- Professional dark-themed dashboard with sidebar navigation
- REST API for all Emily subsystems
- WebSocket for real-time chat, logs, and status streaming
- Prometheus metrics proxy
- Memory inspector, agent viewer, audit console, config viewer

Run with:
    uvicorn api.app:app --host 0.0.0.0 --port 8000

API secret: set EMILY_API_SECRET in .env or environment (not in config.yaml).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

from api.routes import audio as audio_routes  # noqa: E402
from api.routes import chat_v1 as chat_v1_routes  # noqa: E402
from api.routes import conversations as conversations_routes  # noqa: E402
from api.routes import graph as graph_routes  # noqa: E402
from api.routes import integrations as integrations_routes  # noqa: E402
from api.routes import models_v1 as models_v1_routes  # noqa: E402
from api.routes import people as people_routes  # noqa: E402
from api.routes import query as query_routes  # noqa: E402
from api.routes import settings as settings_routes  # noqa: E402
from api.routes import singing as singing_routes  # noqa: E402
from api.routes import tts as tts_routes  # noqa: E402
from api.routes import vault as vault_routes  # noqa: E402
from api.routes import voice_engine as voice_engine_routes  # noqa: E402
from config import get_settings  # noqa: E402
from observability.logger import get_logger  # noqa: E402

log = get_logger(__name__)

_chat_db = None


def get_chat_db() -> Any:
    """Return the shared :class:`ConversationDatabase` (or ``None`` before startup)."""
    return _chat_db


# ---------------------------------------------------------------------------
# Lifespan: connect knowledge OS services on startup, close on shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Connect the knowledge store, vault, and query engine at startup."""
    settings = get_settings()

    from llm.tabbyapi_client import TabbyAPIClient
    from memory.knowledge_store import KnowledgeStore
    from memory.query_engine import MemoryQueryEngine
    from proactive.engine import ProactiveEngine
    from security.vault.vault import CredentialVault

    # Knowledge store — self-bootstrapping (applies schema on connect)
    store = KnowledgeStore(db_path=settings.knowledge.db_path)
    await store.connect()

    # Vault — starts locked; user unlocks via POST /vault/unlock
    vault = CredentialVault(
        db_path=settings.vault.db_path,
        auto_lock_minutes=settings.vault.auto_lock_minutes,
        audit_log_path=settings.vault.audit_log_path,
    )

    # LLM client for query classification (TabbyAPI fast model)
    llm_client = TabbyAPIClient(
        base_url=settings.llm.tabbyapi_base_url,
        api_key=settings.llm.tabbyapi_api_key,
    )

    # Query engine
    query_engine = MemoryQueryEngine(
        llm_client=llm_client,
        knowledge_store=store,
        vault=vault,
        nano_model=settings.llm.models.fast,  # fast model via TabbyAPI
    )

    # Proactive engine
    proactive = ProactiveEngine(store=store, vault=vault)

    # Wire up FastAPI dependency overrides
    application.dependency_overrides[people_routes._get_store] = lambda: store  # pyright: ignore[reportPrivateUsage]
    application.dependency_overrides[vault_routes._get_vault] = lambda: vault  # pyright: ignore[reportPrivateUsage]
    application.dependency_overrides[query_routes._get_query_engine] = lambda: query_engine  # pyright: ignore[reportPrivateUsage]
    application.dependency_overrides[graph_routes._get_store] = lambda: store  # pyright: ignore[reportPrivateUsage]
    application.dependency_overrides[graph_routes._get_proactive] = lambda: proactive  # pyright: ignore[reportPrivateUsage]

    # TTS engine for voice test and audio routes
    # Load lazily in background — don't block lifespan (Kokoro model download
    # can exceed uvicorn's startup timeout and cancel the lifespan coroutine).
    from voice.tts import TTSManager

    tts_manager = TTSManager(settings.tts)

    async def _load_tts_background() -> None:
        try:
            await tts_manager.load()
            log.info("api_tts_loaded")
        except BaseException as exc:
            # Catch BaseException — spaCy auto-download can raise SystemExit
            log.warning("api_tts_load_failed", error=str(exc)[:200])

    asyncio.create_task(_load_tts_background())

    # Singing manager — load engines in background; wire route regardless
    if settings.singing.enabled:
        from voice.singing import SingingManager as _SingingManager

        singing_manager = _SingingManager(settings.singing)

        async def _load_singing_background() -> None:
            try:
                await singing_manager.load()
                log.info("api_singing_loaded")
            except BaseException as exc:
                log.warning("api_singing_load_failed", error=str(exc)[:200])

        asyncio.create_task(_load_singing_background())
        singing_routes.configure(singing_manager)

    # Voice engine is managed by Bootstrap, not the API lifespan.
    # Just wire up audio state for the /audio routes.
    audio_routes.set_audio_state(
        input_device=settings.audio.input_device,
        output_device=settings.audio.output_device,
        tts_manager=tts_manager,
    )

    # Chat database — shared with React frontend routes
    global _chat_db
    from emily_chat.storage.database import ConversationDatabase

    _chat_db = ConversationDatabase()
    await _chat_db.init()

    log.info("knowledge_os_services_started")

    yield  # application runs here

    # Shutdown
    if _chat_db:
        await _chat_db.close()
        _chat_db = None
    await vault.close()
    await store.close()
    await llm_client.close()
    log.info("knowledge_os_services_stopped")


# Paths that do not require Bearer auth (docs and static)
_AUTH_SKIP_PREFIXES = ("/docs", "/redoc", "/openapi.json")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Require Bearer token for API requests when API secret is configured."""

    async def dispatch(
        self,
        request: Request,
        call_next: Any,
    ) -> JSONResponse:
        if request.url.path.startswith(_AUTH_SKIP_PREFIXES):
            return await call_next(request)
        secret = _get_api_secret()
        if not secret:
            return await call_next(request)
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer ") or auth[7:].strip() != secret:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing Bearer token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests with body larger than configured limit."""

    def __init__(self, app: Any, max_bytes: int = 1_000_000) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self._max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                pass
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory per-IP rate limit."""

    def __init__(
        self,
        app: Any,
        requests: int = 100,
        window_s: int = 60,
    ) -> None:
        super().__init__(app)
        self._requests = requests
        self._window_s = window_s
        self._counts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        if request.url.path.startswith(_AUTH_SKIP_PREFIXES):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.time()
        self._counts[client] = [t for t in self._counts[client] if now - t < self._window_s]
        if len(self._counts[client]) >= self._requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )
        self._counts[client].append(now)
        return await call_next(request)


def _get_api_secret() -> str | None:
    """API secret from config or EMILY_API_SECRET env (used by middleware)."""
    s = get_settings()
    if s.api.secret_key:
        return s.api.secret_key
    return os.environ.get("EMILY_API_SECRET") or None


app = FastAPI(
    title="Emily API",
    description="Cognitive AI OS — Dashboard + REST + WebSocket API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=_lifespan,
)

settings_for_middleware = get_settings()
app.add_middleware(
    MaxBodySizeMiddleware,
    max_bytes=settings_for_middleware.api.max_body_size_bytes,
)
app.add_middleware(
    RateLimitMiddleware,
    requests=settings_for_middleware.api.rate_limit_requests,
    window_s=settings_for_middleware.api.rate_limit_window_s,
)
app.add_middleware(BearerAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_for_middleware.api.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Knowledge OS routers
# ---------------------------------------------------------------------------

app.include_router(people_routes.router)
app.include_router(vault_routes.router)
app.include_router(query_routes.router)
app.include_router(graph_routes.router)
app.include_router(audio_routes.router)
app.include_router(voice_engine_routes.router)
app.include_router(conversations_routes.router)
app.include_router(chat_v1_routes.router)
app.include_router(models_v1_routes.router)
app.include_router(tts_routes.router)
app.include_router(settings_routes.router)
app.include_router(integrations_routes.router)
app.include_router(singing_routes.router)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    stream: bool = True
    model_tier: str = "auto"


class ChatResponse(BaseModel):
    response: str
    model_used: str
    latency_ms: float
    critic_score: float | None = None


# ---------------------------------------------------------------------------
# State (injected at startup from Bootstrap)
# ---------------------------------------------------------------------------

_start_time = time.time()
_bootstrap: Any = None


def set_bootstrap(bootstrap: Any) -> None:
    global _bootstrap
    _bootstrap = bootstrap


# ---------------------------------------------------------------------------
# Helper: collect system metrics from prometheus_client in-process
# ---------------------------------------------------------------------------


def _get_prometheus_snapshot() -> dict[str, Any]:
    """Read all Emily metrics directly from the in-process prometheus registry."""
    try:
        from prometheus_client import REGISTRY

        metrics: dict[str, Any] = {}
        for metric in REGISTRY.collect():
            if not metric.name.startswith("emily_"):
                continue
            for sample in metric.samples:
                name = sample.name
                labels = sample.labels
                value = sample.value
                key = name
                if labels:
                    label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
                    key = f"{name}{{{label_str}}}"
                metrics[key] = value
        return metrics
    except Exception as exc:
        log.warning("prometheus_snapshot_failed", error=str(exc))
        return {}


async def _get_system_resources_async() -> dict[str, Any]:
    """Async wrapper for _get_system_resources to avoid blocking the event loop."""
    return await asyncio.to_thread(_get_system_resources)


def _get_system_resources() -> dict[str, Any]:
    """Get CPU, RAM, VRAM usage via psutil and nvidia-smi."""
    info: dict[str, Any] = {
        "cpu_percent": 0,
        "ram_percent": 0,
        "ram_used_gb": 0,
        "ram_total_gb": 0,
        "vram_used_mb": 0,
        "vram_total_mb": 0,
    }
    try:
        import psutil

        info["cpu_percent"] = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        info["ram_percent"] = ram.percent
        info["ram_used_gb"] = round(ram.used / (1024**3), 1)
        info["ram_total_gb"] = round(ram.total / (1024**3), 1)
    except ImportError:
        pass
    try:
        import subprocess

        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(",")
            info["vram_used_mb"] = int(parts[0].strip())
            info["vram_total_mb"] = int(parts[1].strip())
    except Exception as exc:
        log.debug("vram_query_failed", error=str(exc))
    return info


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "uptime_s": round(time.time() - _start_time, 1)})


@app.get("/status")
async def get_status() -> JSONResponse:
    fsm_state = "UNKNOWN"
    fsm_history: list[list[str]] = []
    if _bootstrap and hasattr(_bootstrap, "fsm"):
        fsm_state = _bootstrap.fsm.current_state.name
        try:
            fsm_history = [[f, t] for f, t in _bootstrap.fsm.history(10)]
        except Exception as exc:
            log.warning("fsm_history_failed", error=str(exc))

    resources = await _get_system_resources_async()
    prom = _get_prometheus_snapshot()

    emotional_state = {}
    for dim in ("engagement", "confidence", "concern", "enthusiasm"):
        key = f"emily_emotional_state{{dimension={dim}}}"
        if key in prom:
            emotional_state[dim] = round(prom[key], 3)
        else:
            emotional_state[dim] = 0.5

    return JSONResponse(
        {
            "fsm_state": fsm_state,
            "uptime_s": round(time.time() - _start_time, 1),
            "resources": resources,
            "emotional_state": emotional_state,
            "fsm_history": fsm_history,
            "metrics": {
                "conversations_total": prom.get(
                    "emily_conversations_total_total",
                    0,
                ),
                "llm_requests_total": sum(
                    v for k, v in prom.items() if k.startswith("emily_llm_requests_total_total")
                ),
                "tool_calls_total": sum(
                    v for k, v in prom.items() if k.startswith("emily_tool_calls_total_total")
                ),
                "wake_words_detected": prom.get(
                    "emily_wake_words_detected_total_total",
                    0,
                ),
                "critic_retries": prom.get(
                    "emily_critic_retries_total_total",
                    0,
                ),
                "stt_errors": prom.get("emily_stt_errors_total_total", 0),
                "rag_docs_ingested": sum(
                    v
                    for k, v in prom.items()
                    if k.startswith("emily_rag_documents_ingested_total_total")
                ),
                "active_agents": prom.get("emily_active_agents", 0),
                "queue_depth": prom.get("emily_agent_queue_depth", 0),
                "working_memory_tokens": prom.get(
                    "emily_working_memory_tokens",
                    0,
                ),
            },
        }
    )


@app.get("/agents")
async def get_agents() -> JSONResponse:
    agents: list[dict[str, Any]] = []
    core_agents = [
        {"name": "ConversationAgent", "type": "core", "role": "Real-time dialogue"},
        {"name": "PlannerAgent", "type": "core", "role": "Task decomposition"},
        {"name": "MemoryAgent", "type": "core", "role": "Cross-tier memory ops"},
        {"name": "ReflectionAgent", "type": "core", "role": "Idle-time consolidation"},
        {"name": "ResearchAgent", "type": "specialist", "role": "RAG + web search"},
        {"name": "CodeAgent", "type": "specialist", "role": "Code gen + sandbox"},
        {"name": "MonitorAgent", "type": "specialist", "role": "Resource monitoring"},
        {"name": "ToolBuilderAgent", "type": "specialist", "role": "Dynamic tool gen"},
    ]
    for a in core_agents:
        a["status"] = "active"
        agents.append(a)
    return JSONResponse({"agents": agents})


@app.get("/memory/working")
async def get_working_memory() -> JSONResponse:
    return JSONResponse(
        {
            "entries": [],
            "token_count": 0,
            "session_id": None,
            "note": "Live data available when MemoryManager is connected to Bootstrap.",
        }
    )


@app.get("/memory/episodic")
async def get_recent_episodes(n: int = 20) -> JSONResponse:
    return JSONResponse(
        {
            "sessions": [],
            "total_count": 0,
        }
    )


@app.get("/memory/procedural")
async def get_procedural_memory() -> JSONResponse:
    proc_path = Path("data/procedural.json")
    if proc_path.exists():
        try:
            raw = await asyncio.to_thread(proc_path.read_text)
            data = json.loads(raw)
            return JSONResponse({"data": data})
        except Exception as exc:
            log.warning("procedural_memory_read_failed", error=str(exc))
    return JSONResponse({"data": {}})


@app.get("/logs/recent")
async def get_recent_logs(n: int = 100) -> JSONResponse:
    log_path = Path("logs/emily.log")
    lines: list[dict[str, Any]] = []
    if log_path.exists():
        try:
            raw_text = await asyncio.to_thread(log_path.read_text)
            raw_lines = raw_text.strip().splitlines()
            for line in raw_lines[-n:]:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    lines.append({"event": line, "level": "raw"})
        except Exception as exc:
            log.warning("recent_logs_read_failed", error=str(exc))
    audit_path = Path("logs/audit.log")
    audit_lines: list[dict[str, Any]] = []
    if audit_path.exists():
        try:
            raw = await asyncio.to_thread(audit_path.read_text)
            for line in raw.strip().splitlines()[-n:]:
                with contextlib.suppress(json.JSONDecodeError):
                    audit_lines.append(json.loads(line))
        except Exception as exc:
            log.warning("audit_log_read_failed", error=str(exc))
    return JSONResponse({"logs": lines, "audit": audit_lines})


@app.get("/security/audit")
async def get_audit_log(n: int = 50) -> JSONResponse:
    if _bootstrap and hasattr(_bootstrap, "security"):
        audit_entries = await _bootstrap.security.audit_log.get_recent(n)
        return JSONResponse({"entries": [e.to_dict() for e in audit_entries]})  # pyright: ignore[reportUnknownMemberType]
    audit_path = Path("logs/audit.log")
    entries: list[dict[str, Any]] = []
    if audit_path.exists():
        try:
            raw = await asyncio.to_thread(audit_path.read_text)
            for line in raw.strip().splitlines()[-n:]:
                with contextlib.suppress(json.JSONDecodeError):
                    entries.append(json.loads(line))
        except Exception as exc:
            log.warning("audit_log_fallback_read_failed", error=str(exc))
    return JSONResponse({"entries": entries})


@app.post("/security/audit/verify")
async def verify_audit_log() -> JSONResponse:
    if _bootstrap and hasattr(_bootstrap, "security"):
        valid, errors = await _bootstrap.security.audit_log.verify()
        return JSONResponse({"valid": valid, "errors": errors})
    return JSONResponse({"valid": True, "errors": []})


@app.get("/metrics/summary")
async def get_metrics_summary() -> JSONResponse:
    return JSONResponse({"metrics": _get_prometheus_snapshot()})


@app.get("/self-improvement")
async def get_self_improvement() -> JSONResponse:
    result: dict[str, Any] = {"performance": [], "gaps": [], "rag_quality": {}}
    if _bootstrap and hasattr(_bootstrap, "self_improvement"):
        eng = _bootstrap.self_improvement
        try:
            summaries = eng.performance.get_all_summaries(24.0)
            result["performance"] = [
                {
                    "category": s.category,
                    "metric": s.metric,
                    "count": s.count,
                    "mean": round(s.mean, 4),
                    "median": round(s.median, 4),
                    "p95": round(s.p95, 4),
                    "std": round(s.std, 4),
                }
                for s in summaries
            ]
        except Exception as exc:
            log.warning("self_improvement_performance_failed", error=str(exc))
        try:
            gaps = eng.gap_logger.get_unresolved(limit=20)
            result["gaps"] = [
                {
                    "gap_id": g.gap_id,
                    "type": g.gap_type,
                    "description": g.description,
                    "confidence": g.confidence,
                    "ts": g.ts,
                }
                for g in gaps
            ]
        except Exception as exc:
            log.warning("self_improvement_gaps_failed", error=str(exc))
        try:
            result["rag_quality"] = eng.rag_feedback.compute_document_quality()
        except Exception as exc:
            log.warning("self_improvement_rag_quality_failed", error=str(exc))
    return JSONResponse(result)


@app.get("/config")
async def get_config() -> JSONResponse:
    try:
        from config import get_settings

        s = get_settings()
        sanitized: dict[str, Any] = {}
        for section_name in [
            "llm",
            "audio",
            "wake_word",
            "vad",
            "stt",
            "tts",
            "voice_engine",
            "memory",
            "rag",
            "agents",
            "tools",
            "vision",
            "persona",
            "security",
            "self_improvement",
            "api",
            "observability",
        ]:
            section = getattr(s, section_name, None)
            if section:
                d = section.model_dump()
                for key in ("secret_key", "key_file", "api_key", "token"):
                    if key in d:
                        d[key] = "***"
                sanitized[section_name] = d
        sanitized["name"] = s.name
        sanitized["version"] = s.version
        sanitized["log_level"] = s.log_level
        return JSONResponse(sanitized)
    except Exception as exc:
        return JSONResponse({"error": str(exc)})


# #region agent log — debug log proxy for browser JS
@app.post("/api/debug-log")
async def debug_log_proxy(request: Request) -> JSONResponse:
    """Proxy: browser JS posts debug logs here, we write to the debug log file."""
    import json as _json

    try:
        body = await request.json()
        body["timestamp"] = body.get("timestamp", int(time.time() * 1000))
        settings = get_settings()
        log_path = Path(settings.logs_dir) / "debug.log"

        def _write() -> None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a") as f:
                f.write(_json.dumps(body) + "\n")

        await asyncio.to_thread(_write)
    except Exception as exc:
        log.warning("debug_log_write_failed", error=str(exc))
    return JSONResponse({"ok": True})


# #endregion


# ---------------------------------------------------------------------------
# Chat (SSE streaming + non-streaming)
# ---------------------------------------------------------------------------

_EMILY_SYSTEM_PROMPT = (
    "You are Emily, a warm and helpful AI assistant. "
    "Keep responses concise and conversational. "
    "Never use emojis, emoticons, or markdown formatting in your responses."
)


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Non-streaming chat via TabbyAPI (ExLlamaV2 abliterated model)."""
    from llm.client import ChatMessage
    from llm.tabbyapi_client import TabbyAPIClient

    settings = get_settings()
    t0 = time.monotonic()
    client = TabbyAPIClient(
        base_url=settings.llm.tabbyapi_base_url,
        api_key=settings.llm.tabbyapi_api_key,
    )
    try:
        result = await client.chat(
            model=settings.llm.models.fast,
            messages=[
                ChatMessage(role="system", content=_EMILY_SYSTEM_PROMPT),
                ChatMessage(role="user", content=request.message),
            ],
        )
        return ChatResponse(
            response=result.content,
            model_used=result.model,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
    except Exception as exc:
        log.error("chat_endpoint_error", error=str(exc))
        return ChatResponse(
            response=f"Sorry, I couldn't process that: {exc}",
            model_used="error",
            latency_ms=(time.monotonic() - t0) * 1000,
        )
    finally:
        await client.close()


@app.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest) -> StreamingResponse:
    """Streaming chat via TabbyAPI (ExLlamaV2 abliterated model) with SSE."""
    from llm.client import ChatMessage
    from llm.tabbyapi_client import TabbyAPIClient

    settings = get_settings()

    async def generate() -> AsyncIterator[str]:
        client = TabbyAPIClient(
            base_url=settings.llm.tabbyapi_base_url,
            api_key=settings.llm.tabbyapi_api_key,
        )
        try:
            async for chunk in client.chat_stream(
                model=settings.llm.models.fast,
                messages=[
                    ChatMessage(role="system", content=_EMILY_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=request.message),
                ],
            ):
                if chunk.content:
                    yield f"data: {chunk.content}\n\n"
        except Exception as exc:
            log.error("chat_stream_error", error=str(exc))
            yield f"data: Sorry, I couldn't process that: {exc}\n\n"
        finally:
            await client.close()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Voice transcript SSE — streams voice pipeline messages to the chat UI
# ---------------------------------------------------------------------------


@app.get("/chat/voice-transcript")
async def voice_transcript_sse() -> StreamingResponse:
    """SSE endpoint that tails logs/voice_transcript.jsonl for new entries."""
    import json as _json

    transcript_path = Path("logs/voice_transcript.jsonl")

    # Each connection starts from the current end of file
    initial_offset = 0
    if transcript_path.exists():
        with contextlib.suppress(Exception):
            initial_offset = len(transcript_path.read_text().strip().splitlines())

    async def generate() -> AsyncIterator[str]:
        offset = initial_offset
        while True:
            if transcript_path.exists():
                try:
                    lines = transcript_path.read_text().strip().splitlines()
                    if len(lines) > offset:
                        for line in lines[offset:]:
                            try:
                                entry = _json.loads(line)
                                yield f"data: {_json.dumps(entry)}\n\n"
                            except _json.JSONDecodeError:
                                continue
                        offset = len(lines)
                except Exception:
                    pass
            await asyncio.sleep(1.5)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# WebSocket — chat + log_stream + status_update
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("websocket_connected", client=str(websocket.client))
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_input":
                text = data.get("text", "")
                words = f"Echo: {text}".split()
                for word in words:
                    await websocket.send_json({"type": "token", "text": word + " "})
                    await asyncio.sleep(0.05)
                await websocket.send_json({"type": "done"})

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})

            elif msg_type == "get_status":
                resources = _get_system_resources()
                fsm_state = "UNKNOWN"
                if _bootstrap and hasattr(_bootstrap, "fsm"):
                    fsm_state = _bootstrap.fsm.current_state.name
                await websocket.send_json(
                    {
                        "type": "status_update",
                        "fsm_state": fsm_state,
                        "uptime_s": round(time.time() - _start_time, 1),
                        "resources": resources,
                    }
                )

            elif msg_type == "get_logs":
                n = data.get("n", 50)
                audit_path = Path("logs/audit.log")
                entries: list[dict[str, Any]] = []
                if audit_path.exists():
                    with contextlib.suppress(Exception):
                        raw = audit_path.read_text().strip().splitlines()
                        for line in raw[-n:]:
                            with contextlib.suppress(json.JSONDecodeError):
                                entries.append(json.loads(line))
                await websocket.send_json({"type": "log_stream", "entries": entries})

    except WebSocketDisconnect:
        log.info("websocket_disconnected")
    except Exception as exc:
        log.error("websocket_error", error=str(exc))


# ---------------------------------------------------------------------------
# Dashboard HTML — served at GET /
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the main Emily dashboard from an external HTML file."""
    html_path = Path(__file__).parent / "dashboard.html"
    content = await asyncio.to_thread(html_path.read_text, "utf-8")
    return HTMLResponse(content=content)


@app.get("/voice-dashboard", response_class=HTMLResponse)
async def voice_dashboard() -> HTMLResponse:
    """Serve the dedicated voice mode dashboard from an external HTML file."""
    html_path = Path(__file__).parent / "voice_dashboard.html"
    content = await asyncio.to_thread(html_path.read_text, "utf-8")
    return HTMLResponse(content=content)
