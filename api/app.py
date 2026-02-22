"""
Emily FastAPI web application — full dashboard + API.

Provides:
- Professional dark-themed dashboard with sidebar navigation
- REST API for all Emily subsystems
- WebSocket for real-time chat, logs, and status streaming
- Prometheus metrics proxy
- Memory inspector, agent viewer, audit console, config viewer

Run with:
    uvicorn api.app:app --host 0.0.0.0 --port 8080

API secret: set EMILY_API_SECRET in .env or environment (not in config.yaml).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from observability.logger import get_logger
from api.routes import people as people_routes
from api.routes import vault as vault_routes
from api.routes import query as query_routes
from api.routes import graph as graph_routes
from api.routes import audio as audio_routes
from api.routes import voice_engine as voice_engine_routes

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: connect knowledge OS services on startup, close on shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Connect the knowledge store, vault, and query engine at startup."""
    settings = get_settings()

    from memory.knowledge_store import KnowledgeStore
    from security.vault.vault import CredentialVault
    from llm.client import OllamaClient
    from memory.query_engine import MemoryQueryEngine
    from proactive.engine import ProactiveEngine

    # Knowledge store — self-bootstrapping (applies schema on connect)
    store = KnowledgeStore(db_path=settings.knowledge.db_path)
    await store.connect()

    # Vault — starts locked; user unlocks via POST /vault/unlock
    vault = CredentialVault(
        db_path=settings.vault.db_path,
        auto_lock_minutes=settings.vault.auto_lock_minutes,
        audit_log_path=settings.vault.audit_log_path,
    )

    # LLM client for query classification (used by MemoryQueryEngine)
    llm_client = OllamaClient(base_url=settings.llm.ollama_base_url)

    # Query engine
    query_engine = MemoryQueryEngine(
        llm_client=llm_client,
        knowledge_store=store,
        vault=vault,
        nano_model=settings.llm.models.nano,
    )

    # Proactive engine
    proactive = ProactiveEngine(store=store, vault=vault)

    # Wire up FastAPI dependency overrides
    application.dependency_overrides[people_routes._get_store] = lambda: store
    application.dependency_overrides[vault_routes._get_vault] = lambda: vault
    application.dependency_overrides[query_routes._get_query_engine] = lambda: query_engine
    application.dependency_overrides[graph_routes._get_store] = lambda: store
    application.dependency_overrides[graph_routes._get_proactive] = lambda: proactive

    # TTS engine for voice test and audio routes
    from voice.tts import TTSManager

    tts_manager = TTSManager(settings.tts)
    await tts_manager.load()

    # Voice engine (if enabled and running standalone without bootstrap)
    ve_instance = None
    if hasattr(settings, "voice_engine") and settings.voice_engine.enabled:
        try:
            from conversation.voice_engine import VoiceEngine
            from core.bus import PerceptionBus

            bus = PerceptionBus()
            await bus.start_publisher()
            await bus.start_subscriber()
            ve_instance = VoiceEngine(settings, bus)
            voice_engine_routes.configure_voice_engine_routes(engine=ve_instance)
        except ImportError:
            log.warning("voice_engine_module_unavailable_in_api")
        except Exception as exc:
            log.warning("voice_engine_skipped_bus_in_use", error=str(exc))

    # Audio device state for the /audio routes
    audio_routes.set_audio_state(
        input_device=settings.audio.input_device,
        output_device=settings.audio.output_device,
        tts_manager=tts_manager,
        voice_engine=ve_instance,
    )

    log.info("knowledge_os_services_started")

    yield  # application runs here

    # Shutdown
    await vault.close()
    await store.close()
    await llm_client.close()
    log.info("knowledge_os_services_stopped")


# Paths that do not require Bearer auth (docs and static)
_AUTH_SKIP_PREFIXES = ("/docs", "/redoc", "/openapi.json")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Require Bearer token for API requests when API secret is configured."""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        if request.url.path.startswith(_AUTH_SKIP_PREFIXES):
            return await call_next(request)
        secret = _get_api_secret()
        if not secret:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "API secret not configured. Set EMILY_API_SECRET in .env or environment."
                },
            )
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

    def __init__(self, app, max_bytes: int = 1_000_000):  # noqa: ANN001
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
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

    def __init__(self, app, requests: int = 100, window_s: int = 60):  # noqa: ANN001
        super().__init__(app)
        self._requests = requests
        self._window_s = window_s
        self._counts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
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
    info: dict[str, Any] = {"cpu_percent": 0, "ram_percent": 0, "ram_used_gb": 0, "ram_total_gb": 0, "vram_used_mb": 0, "vram_total_mb": 0}
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
            capture_output=True, text=True, timeout=3,
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

    return JSONResponse({
        "fsm_state": fsm_state,
        "uptime_s": round(time.time() - _start_time, 1),
        "resources": resources,
        "emotional_state": emotional_state,
        "fsm_history": fsm_history,
        "metrics": {
            "conversations_total": prom.get("emily_conversations_total_total", 0),
            "llm_requests_total": sum(v for k, v in prom.items() if k.startswith("emily_llm_requests_total_total")),
            "tool_calls_total": sum(v for k, v in prom.items() if k.startswith("emily_tool_calls_total_total")),
            "wake_words_detected": prom.get("emily_wake_words_detected_total_total", 0),
            "critic_retries": prom.get("emily_critic_retries_total_total", 0),
            "stt_errors": prom.get("emily_stt_errors_total_total", 0),
            "rag_docs_ingested": sum(v for k, v in prom.items() if k.startswith("emily_rag_documents_ingested_total_total")),
            "active_agents": prom.get("emily_active_agents", 0),
            "queue_depth": prom.get("emily_agent_queue_depth", 0),
            "working_memory_tokens": prom.get("emily_working_memory_tokens", 0),
        },
    })


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
    return JSONResponse({
        "entries": [],
        "token_count": 0,
        "session_id": None,
        "note": "Live data available when MemoryManager is connected to Bootstrap.",
    })


@app.get("/memory/episodic")
async def get_recent_episodes(n: int = 20) -> JSONResponse:
    return JSONResponse({
        "sessions": [],
        "total_count": 0,
    })


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
                try:
                    audit_lines.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            log.warning("audit_log_read_failed", error=str(exc))
    return JSONResponse({"logs": lines, "audit": audit_lines})


@app.get("/security/audit")
async def get_audit_log(n: int = 50) -> JSONResponse:
    if _bootstrap and hasattr(_bootstrap, "security"):
        entries = await _bootstrap.security.audit_log.get_recent(n)
        return JSONResponse({"entries": [e.to_dict() for e in entries]})
    audit_path = Path("logs/audit.log")
    entries: list[dict[str, Any]] = []
    if audit_path.exists():
        try:
            raw = await asyncio.to_thread(audit_path.read_text)
            for line in raw.strip().splitlines()[-n:]:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
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
                {"category": s.category, "metric": s.metric, "count": s.count,
                 "mean": round(s.mean, 4), "median": round(s.median, 4),
                 "p95": round(s.p95, 4), "std": round(s.std, 4)}
                for s in summaries
            ]
        except Exception as exc:
            log.warning("self_improvement_performance_failed", error=str(exc))
        try:
            gaps = eng.gap_logger.get_unresolved(limit=20)
            result["gaps"] = [
                {"gap_id": g.gap_id, "type": g.gap_type, "description": g.description,
                 "confidence": g.confidence, "ts": g.ts}
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
            "llm", "audio", "wake_word", "vad", "stt", "tts",
            "voice_engine", "memory", "rag", "agents", "tools",
            "vision", "persona", "security", "self_improvement",
            "api", "observability",
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
    """Non-streaming chat via Ollama LLM."""
    from llm.client import ChatMessage, OllamaClient

    settings = get_settings()
    t0 = time.monotonic()
    client = OllamaClient(base_url=settings.llm.ollama_base_url)
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
    """Streaming chat via Ollama LLM with SSE."""
    from llm.client import ChatMessage, OllamaClient

    settings = get_settings()

    async def generate() -> AsyncIterator[str]:
        client = OllamaClient(base_url=settings.llm.ollama_base_url)
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
        try:
            initial_offset = len(transcript_path.read_text().strip().splitlines())
        except Exception:
            pass

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
                prom = _get_prometheus_snapshot()
                fsm_state = "UNKNOWN"
                if _bootstrap and hasattr(_bootstrap, "fsm"):
                    fsm_state = _bootstrap.fsm.current_state.name
                await websocket.send_json({
                    "type": "status_update",
                    "fsm_state": fsm_state,
                    "uptime_s": round(time.time() - _start_time, 1),
                    "resources": resources,
                })

            elif msg_type == "get_logs":
                n = data.get("n", 50)
                audit_path = Path("logs/audit.log")
                entries: list[dict[str, Any]] = []
                if audit_path.exists():
                    try:
                        raw = audit_path.read_text().strip().splitlines()
                        for line in raw[-n:]:
                            try:
                                entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                    except Exception:
                        pass
                await websocket.send_json({"type": "log_stream", "entries": entries})

    except WebSocketDisconnect:
        log.info("websocket_disconnected")
    except Exception as exc:
        log.error("websocket_error", error=str(exc))


# ---------------------------------------------------------------------------
# Dashboard HTML — served at GET /
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Emily — Dashboard</title>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.3/dist/cdn.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg-primary: #0a0a0f;
  --bg-secondary: #10101a;
  --bg-card: #151520;
  --bg-card-hover: #1a1a28;
  --bg-input: #12121c;
  --border: #1e1e30;
  --border-light: #2a2a40;
  --text-primary: #e4e4ed;
  --text-secondary: #8888a0;
  --text-muted: #555570;
  --accent: #7c5cfc;
  --accent-glow: #7c5cfc44;
  --accent-light: #a78bfa;
  --green: #34d399;
  --red: #f87171;
  --yellow: #fbbf24;
  --blue: #60a5fa;
  --cyan: #22d3ee;
  --sidebar-w: 220px;
  --header-h: 56px;
  --radius: 10px;
  --radius-sm: 6px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: var(--bg-primary); color: var(--text-primary); height: 100vh; overflow: hidden; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-light); border-radius: 3px; }

/* LAYOUT */
.layout { display: grid; grid-template-columns: var(--sidebar-w) 1fr; grid-template-rows: var(--header-h) 1fr; height: 100vh; }
.header { grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; background: var(--bg-secondary); border-bottom: 1px solid var(--border); z-index: 10; }
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h1 { font-size: 1.2rem; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--cyan)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: -0.02em; }
.header-left .version { font-size: 0.7rem; color: var(--text-muted); background: var(--bg-card); padding: 2px 8px; border-radius: 20px; border: 1px solid var(--border); }
.header-right { display: flex; align-items: center; gap: 16px; }
.status-badge { display: flex; align-items: center; gap: 6px; font-size: 0.75rem; font-weight: 600; padding: 4px 12px; border-radius: 20px; border: 1px solid var(--border); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.uptime { font-size: 0.75rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }

/* SIDEBAR */
.sidebar { background: var(--bg-secondary); border-right: 1px solid var(--border); padding: 16px 0; display: flex; flex-direction: column; gap: 2px; overflow-y: auto; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 20px; font-size: 0.82rem; font-weight: 500; color: var(--text-secondary); cursor: pointer; border-left: 3px solid transparent; transition: all 0.15s; }
.nav-item:hover { background: var(--bg-card); color: var(--text-primary); }
.nav-item.active { color: var(--accent-light); border-left-color: var(--accent); background: var(--accent-glow); }
.nav-icon { width: 18px; text-align: center; font-size: 0.9rem; }
.nav-section { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); padding: 16px 20px 6px; font-weight: 600; }

/* MAIN CONTENT */
.main { overflow-y: auto; padding: 20px; }
.panel { display: none; }
.panel.active { display: block; }

/* CARDS + GRID */
.grid { display: grid; gap: 16px; }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-1 { grid-template-columns: 1fr; }
.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; transition: border-color 0.2s; }
.card:hover { border-color: var(--border-light); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.card-title { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); font-weight: 600; }
.card-value { font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.card-sub { font-size: 0.72rem; color: var(--text-secondary); margin-top: 4px; }

/* STAT CARDS */
.stat-icon { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1rem; }

/* GAUGE */
.gauge-bar { height: 6px; background: var(--bg-primary); border-radius: 3px; margin-top: 10px; overflow: hidden; }
.gauge-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; }

/* TABLES */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th { text-align: left; padding: 10px 12px; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
td { padding: 10px 12px; border-bottom: 1px solid var(--border); color: var(--text-secondary); }
tr:hover td { background: var(--bg-card-hover); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.68rem; font-weight: 600; }
.badge-green { background: #34d39920; color: var(--green); }
.badge-blue { background: #60a5fa20; color: var(--blue); }
.badge-yellow { background: #fbbf2420; color: var(--yellow); }
.badge-red { background: #f8717120; color: var(--red); }
.badge-purple { background: #7c5cfc20; color: var(--accent-light); }

/* VOICE MODE */
.voice-status-orb { width: 64px; height: 64px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; position: relative; transition: box-shadow 0.4s, background 0.4s; }
.voice-status-orb.listening { background: radial-gradient(circle, #60a5fa 0%, #1e3a5f 100%); box-shadow: 0 0 24px 8px #60a5fa44; animation: orb-pulse 1.5s ease-in-out infinite; }
.voice-status-orb.responding { background: radial-gradient(circle, #a78bfa 0%, #3b2d6e 100%); box-shadow: 0 0 24px 8px #7c5cfc44; animation: orb-pulse 1.0s ease-in-out infinite; }
.voice-status-orb.processing { background: radial-gradient(circle, #fbbf24 0%, #5c4a10 100%); box-shadow: 0 0 24px 8px #fbbf2444; animation: orb-pulse 0.7s ease-in-out infinite; }
.voice-status-orb.idle { background: radial-gradient(circle, #34d399 0%, #0f3d2a 100%); box-shadow: 0 0 12px 4px #34d39922; }
.voice-status-orb.error { background: radial-gradient(circle, #f87171 0%, #5c1a1a 100%); box-shadow: 0 0 16px 6px #f8717133; }
@keyframes orb-pulse { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.08); opacity: 0.85; } }
.voice-hero { display: flex; align-items: center; gap: 20px; padding: 8px 0; }
.voice-hero-state { font-size: 1.8rem; font-weight: 800; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; }
.voice-hero-sub { font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px; }
.transcript-container { display: flex; flex-direction: column; height: 340px; overflow-y: auto; padding: 12px; gap: 6px; background: var(--bg-primary); border: 1px solid var(--border); border-radius: var(--radius); }
.transcript-entry { display: flex; gap: 10px; padding: 8px 12px; border-radius: 8px; font-size: 0.82rem; line-height: 1.5; animation: transcript-in 0.25s ease-out; }
@keyframes transcript-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
.transcript-entry.user { background: #1e3a5f20; border-left: 3px solid var(--blue); }
.transcript-entry.emily { background: #7c5cfc10; border-left: 3px solid var(--accent); }
.transcript-role { font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; min-width: 48px; padding-top: 2px; }
.transcript-role.user { color: var(--blue); }
.transcript-role.emily { color: var(--accent-light); }
.transcript-ts { font-size: 0.65rem; color: var(--text-muted); min-width: 56px; padding-top: 3px; font-variant-numeric: tabular-nums; }
.transcript-text { flex: 1; color: var(--text-primary); }
.telemetry-label { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); font-weight: 600; margin-bottom: 6px; }
.telemetry-value { font-size: 1.1rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.telemetry-bar { height: 6px; background: var(--bg-primary); border-radius: 3px; overflow: hidden; margin-top: 6px; }
.telemetry-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
.voice-controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.voice-controls select { background: var(--bg-input); border: 1px solid var(--border); color: var(--text-primary); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 0.8rem; outline: none; cursor: pointer; min-width: 180px; }
.voice-btn { background: var(--accent); color: #fff; border: none; padding: 8px 18px; border-radius: var(--radius-sm); font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.voice-btn:hover { background: #6d4ae0; transform: translateY(-1px); }
.voice-btn.secondary { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); }
.voice-btn.secondary:hover { background: var(--bg-card-hover); border-color: var(--border-light); }
.voice-btn.danger { background: var(--red); }
.voice-btn.danger:hover { background: #e05050; }
.empty-transcript { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); gap: 8px; }
.empty-transcript .icon { font-size: 2.5rem; opacity: 0.3; }
.empty-transcript .label { font-size: 0.82rem; }
.breakdown-row { display: flex; justify-content: space-between; padding: 3px 0; font-size: 0.75rem; }
.breakdown-key { color: var(--text-secondary); }
.breakdown-val { color: var(--text-primary); font-weight: 600; font-variant-numeric: tabular-nums; }

/* LOGS CONSOLE */
.log-console { background: var(--bg-primary); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; height: calc(100vh - var(--header-h) - 120px); overflow-y: auto; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.72rem; line-height: 1.7; }
.log-line { padding: 1px 0; display: flex; gap: 8px; }
.log-ts { color: var(--text-muted); min-width: 80px; flex-shrink: 0; }
.log-level { min-width: 55px; font-weight: 700; flex-shrink: 0; }
.log-level.info { color: var(--blue); }
.log-level.warning { color: var(--yellow); }
.log-level.error { color: var(--red); }
.log-level.debug { color: var(--text-muted); }
.log-event { color: var(--text-secondary); }
.log-filters { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
.log-filters select, .log-filters input { background: var(--bg-input); border: 1px solid var(--border); color: var(--text-primary); padding: 6px 10px; border-radius: var(--radius-sm); font-size: 0.75rem; outline: none; }

/* CONFIG */
.config-section { margin-bottom: 16px; }
.config-section-title { font-size: 0.8rem; font-weight: 700; color: var(--accent-light); padding: 8px 0 6px; border-bottom: 1px solid var(--border); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.04em; }
.config-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.78rem; }
.config-key { color: var(--text-secondary); }
.config-val { color: var(--text-primary); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; }

/* TABS */
.tabs { display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
.tab { padding: 8px 16px; font-size: 0.78rem; font-weight: 600; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; }
.tab:hover { color: var(--text-primary); }
.tab.active { color: var(--accent-light); border-bottom-color: var(--accent); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* CHART CONTAINER */
.chart-box { position: relative; height: 200px; }

/* JSON VIEWER */
.json-viewer { background: var(--bg-primary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: var(--cyan); overflow: auto; max-height: 500px; white-space: pre-wrap; word-break: break-all; }

@media (max-width: 1200px) { .grid-4 { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 768px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar { display: none; }
  .grid-4, .grid-3 { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>
<div class="layout" x-data="dashboard()" x-init="init()">

  <!-- HEADER -->
  <div class="header">
    <div class="header-left">
      <h1>EMILY</h1>
      <span class="version">v1.0.0</span>
    </div>
    <div class="header-right">
      <div class="status-badge">
        <div class="status-dot" :style="'background:' + fsmColor()"></div>
        <span x-text="status.fsm_state || 'LOADING'"></span>
      </div>
      <span class="uptime" x-text="'Uptime: ' + formatUptime(status.uptime_s)"></span>
    </div>
  </div>

  <!-- SIDEBAR -->
  <div class="sidebar">
    <div class="nav-section">Main</div>
    <div class="nav-item" :class="page==='dashboard' && 'active'" @click="page='dashboard'">
      <span class="nav-icon">&#9632;</span> Dashboard
    </div>
    <div class="nav-item" :class="page==='voice-mode' && 'active'" @click="page='voice-mode'; loadVoiceMode()">
      <span class="nav-icon">&#127908;</span> Voice Mode
    </div>
    <div class="nav-section">System</div>
    <div class="nav-item" :class="page==='agents' && 'active'" @click="page='agents'">
      <span class="nav-icon">&#9881;</span> Agents
    </div>
    <div class="nav-item" :class="page==='memory' && 'active'" @click="page='memory'">
      <span class="nav-icon">&#9731;</span> Memory
    </div>
    <div class="nav-item" :class="page==='logs' && 'active'" @click="page='logs'; loadLogs()">
      <span class="nav-icon">&#9776;</span> Logs & Audit
    </div>
    <div class="nav-section">Settings</div>
    <div class="nav-item" :class="page==='metrics' && 'active'" @click="page='metrics'; loadMetrics()">
      <span class="nav-icon">&#9733;</span> Metrics
    </div>
    <div class="nav-item" :class="page==='self-improve' && 'active'" @click="page='self-improve'; loadSelfImprovement()">
      <span class="nav-icon">&#10548;</span> Self-Improvement
    </div>
    <div class="nav-item" :class="page==='config' && 'active'" @click="page='config'; loadConfig()">
      <span class="nav-icon">&#9881;</span> Config
    </div>
    <div class="nav-section">Voice</div>
    <div class="nav-item" :class="page==='voice' && 'active'" @click="page='voice'; loadVoice()">
      <span class="nav-icon">&#9835;</span> Voice & Audio
    </div>
  </div>

  <!-- MAIN CONTENT -->
  <div class="main">

    <!-- ==================== DASHBOARD ==================== -->
    <div class="panel" :class="page==='dashboard' && 'active'">
      <!-- Stat cards row -->
      <div class="grid grid-4" style="margin-bottom:16px">
        <div class="card">
          <div class="card-header">
            <span class="card-title">CPU</span>
            <div class="stat-icon" style="background:#60a5fa20;color:var(--blue)">%</div>
          </div>
          <div class="card-value" x-text="(status.resources?.cpu_percent||0).toFixed(1) + '%'"></div>
          <div class="gauge-bar"><div class="gauge-fill" :style="'width:' + (status.resources?.cpu_percent||0) + '%;background:var(--blue)'"></div></div>
        </div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">RAM</span>
            <div class="stat-icon" style="background:#34d39920;color:var(--green)">M</div>
          </div>
          <div class="card-value" x-text="(status.resources?.ram_percent||0).toFixed(1) + '%'"></div>
          <div class="card-sub" x-text="(status.resources?.ram_used_gb||0) + ' / ' + (status.resources?.ram_total_gb||0) + ' GB'"></div>
          <div class="gauge-bar"><div class="gauge-fill" :style="'width:' + (status.resources?.ram_percent||0) + '%;background:var(--green)'"></div></div>
        </div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">VRAM</span>
            <div class="stat-icon" style="background:#7c5cfc20;color:var(--accent)">G</div>
          </div>
          <div class="card-value" x-text="vramPercent() + '%'"></div>
          <div class="card-sub" x-text="(status.resources?.vram_used_mb||0) + ' / ' + (status.resources?.vram_total_mb||0) + ' MB'"></div>
          <div class="gauge-bar"><div class="gauge-fill" :style="'width:' + vramPercent() + '%;background:var(--accent)'"></div></div>
        </div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">FSM State</span>
          </div>
          <div class="card-value" :style="'color:' + fsmColor()" x-text="status.fsm_state || '...'"></div>
          <div class="card-sub">Cognitive state machine</div>
        </div>
      </div>

      <!-- Metric counters row -->
      <div class="grid grid-4" style="margin-bottom:16px">
        <div class="card">
          <div class="card-title">LLM Requests</div>
          <div class="card-value" style="color:var(--blue)" x-text="status.metrics?.llm_requests_total||0"></div>
        </div>
        <div class="card">
          <div class="card-title">Tool Calls</div>
          <div class="card-value" style="color:var(--cyan)" x-text="status.metrics?.tool_calls_total||0"></div>
        </div>
        <div class="card">
          <div class="card-title">Wake Words</div>
          <div class="card-value" style="color:var(--green)" x-text="status.metrics?.wake_words_detected||0"></div>
        </div>
        <div class="card">
          <div class="card-title">Critic Retries</div>
          <div class="card-value" style="color:var(--yellow)" x-text="status.metrics?.critic_retries||0"></div>
        </div>
      </div>

      <!-- Emotional state + Queue info -->
      <div class="grid grid-2">
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Emotional State</div>
          <div class="chart-box"><canvas id="emotionChart"></canvas></div>
        </div>
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">System Overview</div>
          <div style="display:flex;flex-direction:column;gap:10px;">
            <div class="config-row"><span class="config-key">Active Agents</span><span class="config-val" x-text="status.metrics?.active_agents||0"></span></div>
            <div class="config-row"><span class="config-key">Queue Depth</span><span class="config-val" x-text="status.metrics?.queue_depth||0"></span></div>
            <div class="config-row"><span class="config-key">Working Memory Tokens</span><span class="config-val" x-text="status.metrics?.working_memory_tokens||0"></span></div>
            <div class="config-row"><span class="config-key">Conversations</span><span class="config-val" x-text="status.metrics?.conversations_total||0"></span></div>
            <div class="config-row"><span class="config-key">RAG Docs Ingested</span><span class="config-val" x-text="status.metrics?.rag_docs_ingested||0"></span></div>
            <div class="config-row"><span class="config-key">STT Errors</span><span class="config-val" x-text="status.metrics?.stt_errors||0"></span></div>
            <div class="config-row"><span class="config-key">Uptime</span><span class="config-val" x-text="formatUptime(status.uptime_s)"></span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== VOICE MODE ==================== -->
    <div class="panel" :class="page==='voice-mode' && 'active'">

      <div style="display:flex;justify-content:flex-end;margin-bottom:12px;">
        <a href="/voice-dashboard" target="_blank" class="voice-btn secondary" style="text-decoration:none;font-size:0.78rem;">&#8599; Open Dedicated Voice Dashboard</a>
      </div>

      <!-- Hero: status orb + FSM state -->
      <div class="card" style="margin-bottom:16px">
        <div class="voice-hero">
          <div class="voice-status-orb"
               :class="(voiceEngineData.fsm_state||'IDLE').toLowerCase()">
            &#127908;
          </div>
          <div>
            <div class="voice-hero-state" :style="'color:' + voiceFsmColor()"
                 x-text="voiceEngineData.fsm_state || 'IDLE'"></div>
            <div class="voice-hero-sub">
              <span x-text="voiceEngineData.voice_mode === 'full_duplex' ? 'Full-Duplex' : 'Legacy'"></span>
              &middot;
              <span :style="'color:' + (voiceEngineData.running ? 'var(--green)' : 'var(--red)')"
                    x-text="voiceEngineData.running ? 'Pipeline Active' : 'Pipeline Stopped'"></span>
              <template x-if="voiceEngineData.state_duration_s > 0">
                <span> &middot; <span x-text="voiceEngineData.state_duration_s + 's'"></span> in state</span>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Status cards row -->
      <div class="grid grid-4" style="margin-bottom:16px">
        <div class="card">
          <div class="card-title">TTS Engine</div>
          <div class="card-value" :style="'color:' + (voiceStatus.tts_available ? 'var(--green)' : 'var(--yellow)')"
               x-text="voiceStatus.tts_available ? 'READY' : 'N/A'"></div>
        </div>
        <div class="card">
          <div class="card-title">STT Engine</div>
          <div class="card-value" :style="'color:' + (voiceStatus.stt_available ? 'var(--green)' : 'var(--yellow)')"
               x-text="voiceStatus.stt_available ? 'READY' : 'N/A'"></div>
        </div>
        <div class="card">
          <div class="card-title">Backchannels</div>
          <div class="card-value" style="color:var(--cyan)"
               x-text="voiceEngineData.stats?.backchannels_generated || 0"></div>
        </div>
        <div class="card">
          <div class="card-title">Interrupts</div>
          <div class="card-value" style="color:var(--yellow)"
               x-text="voiceEngineData.stats?.interrupts_handled || 0"></div>
        </div>
      </div>

      <!-- Live transcript -->
      <div class="card" style="margin-bottom:16px">
        <div class="card-header">
          <span class="card-title">Live Voice Transcript</span>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="font-size:0.7rem;color:var(--text-muted);"
                  x-text="voiceTranscript.length + ' entries'"></span>
            <button class="voice-btn secondary" style="padding:4px 12px;font-size:0.72rem;"
                    @click="clearTranscript()">Clear</button>
          </div>
        </div>
        <div class="transcript-container" id="voiceTranscriptBox">
          <template x-if="voiceTranscript.length === 0">
            <div class="empty-transcript">
              <div class="icon">&#127908;</div>
              <div class="label">Waiting for voice activity...</div>
              <div style="font-size:0.72rem;color:var(--text-muted);">Transcript entries will appear here when Emily's voice pipeline is active</div>
            </div>
          </template>
          <template x-for="t in voiceTranscript" :key="t.id">
            <div class="transcript-entry" :class="t.role">
              <span class="transcript-ts" x-text="t.time"></span>
              <span class="transcript-role" :class="t.role" x-text="t.role === 'emily' ? 'Emily' : 'User'"></span>
              <span class="transcript-text" x-text="t.text"></span>
            </div>
          </template>
        </div>
      </div>

      <!-- Voice controls bar -->
      <div class="card" style="margin-bottom:16px">
        <div class="card-title" style="margin-bottom:10px">Quick Controls</div>
        <div class="voice-controls">
          <select x-model="selectedInputDevice" @change="setInputDevice()">
            <option value="">Mic: System Default</option>
            <template x-for="d in audioDevices.input_devices" :key="d.index">
              <option :value="d.index" x-text="'Mic: ' + d.name + (d.is_default_input ? ' (default)' : '')"></option>
            </template>
          </select>
          <select x-model="selectedOutputDevice" @change="setOutputDevice()">
            <option value="">Speaker: System Default</option>
            <template x-for="d in audioDevices.output_devices" :key="d.index">
              <option :value="d.index" x-text="'Speaker: ' + d.name + (d.is_default_output ? ' (default)' : '')"></option>
            </template>
          </select>
          <button class="voice-btn" @click="testTTS()">
            &#128266; Test Speaker
          </button>
          <button class="voice-btn secondary" @click="previewVoice()">
            &#127925; Preview Voice
          </button>
          <span style="font-size:0.72rem;color:var(--text-muted);" x-text="ttsTestStatus || voicePreviewStatus"></span>
        </div>
      </div>

      <!-- Telemetry grid -->
      <div class="grid grid-2">
        <!-- Emotion detection -->
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">User Emotion</div>
          <template x-if="voiceEngineData.emotion">
            <div>
              <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:12px;">
                <span class="telemetry-value" style="color:var(--accent-light);text-transform:capitalize;"
                      x-text="voiceEngineData.emotion.primary || 'neutral'"></span>
                <span style="font-size:0.75rem;color:var(--text-muted);"
                      x-text="((voiceEngineData.emotion.confidence||0)*100).toFixed(0) + '% confidence'"></span>
              </div>
              <div class="telemetry-label">Valence</div>
              <div class="telemetry-bar"><div class="telemetry-fill" :style="'width:' + ((voiceEngineData.emotion.valence||0)*100) + '%;background:var(--green)'"></div></div>
              <div class="telemetry-label" style="margin-top:8px">Arousal</div>
              <div class="telemetry-bar"><div class="telemetry-fill" :style="'width:' + ((voiceEngineData.emotion.arousal||0)*100) + '%;background:var(--yellow)'"></div></div>
              <div class="telemetry-label" style="margin-top:8px">Engagement</div>
              <div class="telemetry-bar"><div class="telemetry-fill" :style="'width:' + ((voiceEngineData.emotion.engagement||0)*100) + '%;background:var(--blue)'"></div></div>
              <div class="telemetry-label" style="margin-top:8px">Cognitive Load</div>
              <div class="telemetry-bar"><div class="telemetry-fill" :style="'width:' + ((voiceEngineData.emotion.cognitive_load||0)*100) + '%;background:var(--cyan)'"></div></div>
            </div>
          </template>
          <div x-show="!voiceEngineData.emotion" style="color:var(--text-muted);font-size:0.78rem;">No emotion data — voice engine not active</div>
        </div>

        <!-- Turn signal -->
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Turn Detection</div>
          <template x-if="voiceEngineData.turnSignal">
            <div>
              <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:8px;">
                <span class="telemetry-value" :style="'color:' + (voiceEngineData.turnSignal.action === 'TAKE_TURN' ? 'var(--green)' : voiceEngineData.turnSignal.action === 'WAIT' ? 'var(--yellow)' : 'var(--text-secondary)')"
                      x-text="voiceEngineData.turnSignal.action"></span>
                <span style="font-size:0.78rem;color:var(--text-muted);"
                      x-text="'Score: ' + voiceEngineData.turnSignal.score"></span>
              </div>
              <div class="card-title" style="margin-bottom:6px;margin-top:12px">Confidence Breakdown</div>
              <template x-for="(val, key) in (voiceEngineData.turnSignal.breakdown || {})" :key="key">
                <div class="breakdown-row">
                  <span class="breakdown-key" x-text="key"></span>
                  <span class="breakdown-val" x-text="val"></span>
                </div>
              </template>
            </div>
          </template>
          <div x-show="!voiceEngineData.turnSignal" style="color:var(--text-muted);font-size:0.78rem;">No turn signal — voice engine not active</div>
        </div>

        <!-- Latency budget -->
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Latency Budget</div>
          <template x-if="voiceEngineData.latencyStages && Object.keys(voiceEngineData.latencyStages).length > 0">
            <div class="table-wrap">
              <table>
                <thead><tr><th>Stage</th><th>P50</th><th>P95</th><th>P99</th></tr></thead>
                <tbody>
                  <template x-for="(data, stage) in voiceEngineData.latencyStages" :key="stage">
                    <tr>
                      <td style="color:var(--text-primary);font-weight:500" x-text="stage"></td>
                      <td x-text="(data.p50 || 0) + 'ms'"></td>
                      <td :style="'color:' + ((data.p95||0) > 300 ? 'var(--red)' : 'var(--text-secondary)')"
                          x-text="(data.p95 || 0) + 'ms'"></td>
                      <td x-text="(data.p99 || 0) + 'ms'"></td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </template>
          <div x-show="!voiceEngineData.latencyStages || Object.keys(voiceEngineData.latencyStages).length === 0"
               style="color:var(--text-muted);font-size:0.78rem;">No latency data — voice engine not active</div>
        </div>

        <!-- Rhythm sync -->
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Rhythm Synchronization</div>
          <template x-if="voiceEngineData.rhythm">
            <div>
              <div class="card-title" style="margin-bottom:6px">User Profile</div>
              <div class="breakdown-row">
                <span class="breakdown-key">Speaking rate</span>
                <span class="breakdown-val" x-text="(voiceEngineData.rhythm.user?.speaking_rate_syl_s || 0) + ' syl/s'"></span>
              </div>
              <div class="breakdown-row">
                <span class="breakdown-key">Pause duration</span>
                <span class="breakdown-val" x-text="(voiceEngineData.rhythm.user?.pause_duration_ms || 0) + 'ms'"></span>
              </div>
              <div class="breakdown-row">
                <span class="breakdown-key">Response latency</span>
                <span class="breakdown-val" x-text="(voiceEngineData.rhythm.user?.response_latency_ms || 0) + 'ms'"></span>
              </div>
              <div class="card-title" style="margin-bottom:6px;margin-top:10px">Emily Targets</div>
              <div class="breakdown-row">
                <span class="breakdown-key">Speaking rate</span>
                <span class="breakdown-val" x-text="(voiceEngineData.rhythm.emily?.speaking_rate_syl_s || 0) + ' syl/s'"></span>
              </div>
              <div class="breakdown-row">
                <span class="breakdown-key">Phrase length</span>
                <span class="breakdown-val" x-text="(voiceEngineData.rhythm.emily?.phrase_length_words || 0) + ' words'"></span>
              </div>
              <div class="breakdown-row" style="margin-top:8px;">
                <span class="breakdown-key">Entrainment</span>
                <span class="breakdown-val" style="color:var(--accent-light)" x-text="voiceEngineData.rhythm.entrainment || 0"></span>
              </div>
            </div>
          </template>
          <div x-show="!voiceEngineData.rhythm" style="color:var(--text-muted);font-size:0.78rem;">No rhythm data — voice engine not active</div>
        </div>
      </div>

    </div>

    <!-- ==================== AGENTS ==================== -->
    <div class="panel" :class="page==='agents' && 'active'">
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">Registered Agents</div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Type</th><th>Role</th><th>Status</th></tr></thead>
            <tbody>
              <template x-for="a in agents" :key="a.name">
                <tr>
                  <td style="color:var(--text-primary);font-weight:600" x-text="a.name"></td>
                  <td><span class="badge" :class="a.type==='core'?'badge-purple':'badge-blue'" x-text="a.type"></span></td>
                  <td x-text="a.role"></td>
                  <td><span class="badge badge-green" x-text="a.status"></span></td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ==================== MEMORY ==================== -->
    <div class="panel" :class="page==='memory' && 'active'">
      <div class="tabs">
        <div class="tab" :class="memTab==='working' && 'active'" @click="memTab='working'">Working Memory</div>
        <div class="tab" :class="memTab==='episodic' && 'active'" @click="memTab='episodic'">Episodic</div>
        <div class="tab" :class="memTab==='procedural' && 'active'" @click="memTab='procedural'; loadProcedural()">Procedural</div>
      </div>
      <div class="tab-panel" :class="memTab==='working' && 'active'">
        <div class="card">
          <div class="card-title" style="margin-bottom:8px">Working Memory (Active Context)</div>
          <div class="config-row"><span class="config-key">Token Count</span><span class="config-val" x-text="status.metrics?.working_memory_tokens||0"></span></div>
          <div style="margin-top:12px;color:var(--text-muted);font-size:0.78rem;">Working memory entries appear here during active conversation sessions.</div>
        </div>
      </div>
      <div class="tab-panel" :class="memTab==='episodic' && 'active'">
        <div class="card">
          <div class="card-title" style="margin-bottom:8px">Recent Episodes</div>
          <div style="color:var(--text-muted);font-size:0.78rem;">Episodic session records appear here after completed conversations.</div>
        </div>
      </div>
      <div class="tab-panel" :class="memTab==='procedural' && 'active'">
        <div class="card">
          <div class="card-title" style="margin-bottom:8px">Procedural Memory (User Profile + Self-Model)</div>
          <div class="json-viewer" x-text="JSON.stringify(proceduralData, null, 2)"></div>
        </div>
      </div>
    </div>

    <!-- ==================== LOGS & AUDIT ==================== -->
    <div class="panel" :class="page==='logs' && 'active'">
      <div class="tabs">
        <div class="tab" :class="logTab==='audit' && 'active'" @click="logTab='audit'">Audit Log</div>
        <div class="tab" :class="logTab==='console' && 'active'" @click="logTab='console'">Console</div>
      </div>
      <div class="tab-panel" :class="logTab==='audit' && 'active'">
        <div style="display:flex;gap:8px;margin-bottom:12px;">
          <button class="chat-input-bar" style="padding:0" @click="verifyAudit()">
            <button style="background:var(--accent);color:#fff;border:none;padding:6px 14px;border-radius:var(--radius-sm);font-size:0.75rem;cursor:pointer;">Verify Chain</button>
          </button>
          <span style="font-size:0.75rem;align-self:center;" :style="'color:' + (auditValid===true?'var(--green)':auditValid===false?'var(--red)':'var(--text-muted)')" x-text="auditValid===true?'Chain valid':auditValid===false?'CHAIN BROKEN':'Not verified'"></span>
        </div>
        <div class="card" style="padding:0;">
          <div class="table-wrap">
            <table>
              <thead><tr><th>Seq</th><th>Time</th><th>Event</th><th>Actor</th><th>Hash</th></tr></thead>
              <tbody>
                <template x-for="e in auditEntries" :key="e.seq">
                  <tr>
                    <td style="font-variant-numeric:tabular-nums" x-text="e.seq"></td>
                    <td style="font-size:0.7rem;color:var(--text-muted)" x-text="new Date(e.ts*1000).toLocaleTimeString()"></td>
                    <td><span class="badge badge-blue" x-text="e.event"></span></td>
                    <td x-text="e.actor"></td>
                    <td style="font-family:monospace;font-size:0.65rem;color:var(--text-muted)" x-text="(e.entry_hash||'').substring(0,12) + '...'"></td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="tab-panel" :class="logTab==='console' && 'active'">
        <div class="log-console" id="logConsole">
          <template x-for="(l,i) in logEntries" :key="i">
            <div class="log-line">
              <span class="log-ts" x-text="l.ts ? new Date(l.ts*1000).toLocaleTimeString() : (l.timestamp||'').substring(11,19)"></span>
              <span class="log-level" :class="(l.level||'info').toLowerCase()" x-text="(l.level||'info').toUpperCase()"></span>
              <span class="log-event" x-text="l.event || JSON.stringify(l).substring(0,120)"></span>
            </div>
          </template>
          <div x-show="logEntries.length===0" style="color:var(--text-muted);padding:20px;">No log entries yet. Logs appear here during system operation.</div>
        </div>
      </div>
    </div>

    <!-- ==================== METRICS ==================== -->
    <div class="panel" :class="page==='metrics' && 'active'">
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">Prometheus Metrics (Raw)</div>
        <div class="json-viewer" x-text="JSON.stringify(rawMetrics, null, 2)"></div>
      </div>
    </div>

    <!-- ==================== SELF-IMPROVEMENT ==================== -->
    <div class="panel" :class="page==='self-improve' && 'active'">
      <div class="grid grid-2" style="margin-bottom:16px">
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Performance Summaries (24h)</div>
          <template x-if="selfImprove.performance.length > 0">
            <div class="table-wrap">
              <table>
                <thead><tr><th>Category</th><th>Metric</th><th>Count</th><th>Mean</th><th>P95</th></tr></thead>
                <tbody>
                  <template x-for="p in selfImprove.performance" :key="p.category+p.metric">
                    <tr>
                      <td><span class="badge badge-blue" x-text="p.category"></span></td>
                      <td x-text="p.metric"></td>
                      <td x-text="p.count"></td>
                      <td x-text="p.mean"></td>
                      <td x-text="p.p95"></td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </template>
          <div x-show="selfImprove.performance.length===0" style="color:var(--text-muted);font-size:0.78rem;">No performance data yet.</div>
        </div>
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Capability Gaps</div>
          <template x-if="selfImprove.gaps.length > 0">
            <div class="table-wrap">
              <table>
                <thead><tr><th>Type</th><th>Description</th><th>Confidence</th></tr></thead>
                <tbody>
                  <template x-for="g in selfImprove.gaps" :key="g.gap_id">
                    <tr>
                      <td><span class="badge badge-yellow" x-text="g.type"></span></td>
                      <td style="font-size:0.75rem" x-text="g.description"></td>
                      <td x-text="(g.confidence*100).toFixed(0) + '%'"></td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </template>
          <div x-show="selfImprove.gaps.length===0" style="color:var(--text-muted);font-size:0.78rem;">No capability gaps logged yet.</div>
        </div>
      </div>
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">RAG Document Quality</div>
        <div x-show="Object.keys(selfImprove.rag_quality).length > 0">
          <template x-for="(score, doc) in selfImprove.rag_quality" :key="doc">
            <div class="config-row">
              <span class="config-key" x-text="doc"></span>
              <span class="config-val" :style="'color:' + (score<0.3?'var(--red)':score<0.6?'var(--yellow)':'var(--green)')" x-text="(score*100).toFixed(1) + '%'"></span>
            </div>
          </template>
        </div>
        <div x-show="Object.keys(selfImprove.rag_quality).length===0" style="color:var(--text-muted);font-size:0.78rem;">No RAG quality data yet.</div>
      </div>
    </div>

    <!-- ==================== CONFIG ==================== -->
    <div class="panel" :class="page==='config' && 'active'">
      <template x-for="(section, name) in configData" :key="name">
        <div class="card config-section" x-show="typeof section === 'object'">
          <div class="config-section-title" x-text="name"></div>
          <template x-for="(val, key) in section" :key="key">
            <div class="config-row">
              <span class="config-key" x-text="key"></span>
              <span class="config-val" x-text="typeof val === 'object' ? JSON.stringify(val) : String(val)"></span>
            </div>
          </template>
        </div>
      </template>
    </div>

    <!-- ==================== VOICE & AUDIO ==================== -->
    <div class="panel" :class="page==='voice' && 'active'">

      <!-- Voice pipeline status -->
      <div class="grid grid-4" style="margin-bottom:16px">
        <div class="card">
          <div class="card-title">Voice Mode</div>
          <div class="card-value" :style="'color:' + (voiceStatus.voice_mode === 'full_duplex' ? 'var(--accent-light)' : 'var(--blue)')"
               x-text="voiceStatus.voice_mode === 'full_duplex' ? 'FULL-DUPLEX' : 'LEGACY'"></div>
          <div class="card-sub" :style="'color:' + (voiceStatus.running ? 'var(--green)' : 'var(--red)')"
               x-text="voiceStatus.running ? 'Running' : 'Stopped'"></div>
        </div>
        <div class="card">
          <div class="card-title">TTS Engine</div>
          <div class="card-value" :style="'color:' + (voiceStatus.tts_available ? 'var(--green)' : 'var(--yellow)')"
               x-text="voiceStatus.tts_available ? 'READY' : 'N/A'"></div>
        </div>
        <div class="card">
          <div class="card-title">STT Engine</div>
          <div class="card-value" :style="'color:' + (voiceStatus.stt_available ? 'var(--green)' : 'var(--yellow)')"
               x-text="voiceStatus.stt_available ? 'READY' : 'N/A'"></div>
        </div>
        <div class="card">
          <div class="card-title" x-text="voiceStatus.voice_mode === 'full_duplex' ? 'Conv. FSM' : 'Wake Word'"></div>
          <div class="card-value"
               x-show="voiceStatus.voice_mode === 'full_duplex'"
               :style="'color:var(--accent-light)'"
               x-text="voiceStatus.fsm_state || 'N/A'"></div>
          <div class="card-value"
               x-show="voiceStatus.voice_mode !== 'full_duplex'"
               :style="'color:' + (voiceStatus.wake_word_available ? 'var(--green)' : 'var(--yellow)')"
               x-text="voiceStatus.wake_word_available ? 'READY' : 'N/A'"></div>
        </div>
      </div>

      <!-- Module status (new voice engine only) -->
      <div class="card" style="margin-bottom:16px" x-show="voiceStatus.modules_loaded && voiceStatus.modules_loaded.length > 0">
        <div class="card-title" style="margin-bottom:8px">Voice Engine Modules</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">
          <template x-for="m in (voiceStatus.modules_loaded || [])" :key="m">
            <span class="badge badge-green" x-text="m"></span>
          </template>
        </div>
      </div>

      <!-- Device selection -->
      <div class="grid grid-2" style="margin-bottom:16px">
        <!-- Microphone selection -->
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Microphone (Input Device)</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            <select style="width:100%;background:var(--bg-input);border:1px solid var(--border);color:var(--text-primary);padding:10px 12px;border-radius:var(--radius-sm);font-size:0.82rem;outline:none;cursor:pointer;"
                    x-model="selectedInputDevice" @change="setInputDevice()">
              <option value="">System Default</option>
              <template x-for="d in audioDevices.input_devices" :key="d.index">
                <option :value="d.index" x-text="d.name + (d.is_default_input ? ' (default)' : '') + ' [' + d.hostapi + ']'"></option>
              </template>
            </select>
            <div style="display:flex;align-items:center;gap:8px;">
              <div style="flex:1;height:8px;background:var(--bg-primary);border-radius:4px;overflow:hidden;">
                <div id="micLevel" style="height:100%;width:0%;background:var(--green);border-radius:4px;transition:width 0.1s;"></div>
              </div>
              <span style="font-size:0.7rem;color:var(--text-muted);" x-text="micActive ? 'Live' : 'Inactive'"></span>
            </div>
            <div style="font-size:0.72rem;color:var(--text-muted);">
              Current: <span style="color:var(--text-primary)" x-text="voiceStatus.current_input_device || 'System Default'"></span>
            </div>
          </div>
        </div>

        <!-- Speaker selection -->
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Speaker (Output Device)</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            <select style="width:100%;background:var(--bg-input);border:1px solid var(--border);color:var(--text-primary);padding:10px 12px;border-radius:var(--radius-sm);font-size:0.82rem;outline:none;cursor:pointer;"
                    x-model="selectedOutputDevice" @change="setOutputDevice()">
              <option value="">System Default</option>
              <template x-for="d in audioDevices.output_devices" :key="d.index">
                <option :value="d.index" x-text="d.name + (d.is_default_output ? ' (default)' : '') + ' [' + d.hostapi + ']'"></option>
              </template>
            </select>
            <div style="display:flex;gap:8px;margin-top:4px;">
              <button @click="testTTS()"
                      style="background:var(--accent);color:#fff;border:none;padding:8px 16px;border-radius:var(--radius-sm);font-size:0.8rem;font-weight:600;cursor:pointer;transition:background 0.15s;"
                      onmouseover="this.style.background='#6d4ae0'" onmouseout="this.style.background='var(--accent)'">
                Test Speaker
              </button>
              <span style="font-size:0.72rem;color:var(--text-muted);align-self:center;" x-text="ttsTestStatus"></span>
            </div>
            <div style="font-size:0.72rem;color:var(--text-muted);">
              Current: <span style="color:var(--text-primary)" x-text="voiceStatus.current_output_device || 'System Default'"></span>
            </div>
          </div>
        </div>
      </div>

      <!-- TTS Provider & Voice selection -->
      <div class="grid grid-2" style="margin-bottom:16px">
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">TTS Provider</div>
          <select style="width:100%;background:var(--bg-input);border:1px solid var(--border);color:var(--text-primary);padding:10px 12px;border-radius:var(--radius-sm);font-size:0.82rem;outline:none;cursor:pointer;"
                  x-model="ttsProvider" @change="setVoiceProvider()">
            <template x-for="p in availableProviders" :key="p">
              <option :value="p" x-text="providerLabels[p]" :selected="p === ttsProvider"></option>
            </template>
          </select>
          <div style="font-size:0.72rem;color:var(--text-muted);margin-top:6px;">
            Active: <span style="color:var(--green)" x-text="providerLabels[ttsProvider] || ttsProvider"></span>
          </div>
        </div>
        <div class="card">
          <div class="card-title" style="margin-bottom:12px">Voice</div>
          <select style="width:100%;background:var(--bg-input);border:1px solid var(--border);color:var(--text-primary);padding:10px 12px;border-radius:var(--radius-sm);font-size:0.82rem;outline:none;cursor:pointer;"
                  x-model="selectedVoice" @change="setVoice()">
            <template x-for="v in ttsVoices" :key="v.id">
              <option :value="v.id" x-text="v.name + ' (' + v.gender + ', ' + v.locale + ')'" :selected="v.id === selectedVoice"></option>
            </template>
          </select>
          <div style="display:flex;gap:8px;margin-top:8px;align-items:center;">
            <button @click="previewVoice()"
                    style="background:var(--accent);color:#fff;border:none;padding:6px 14px;border-radius:var(--radius-sm);font-size:0.78rem;font-weight:600;cursor:pointer;transition:background 0.15s;"
                    onmouseover="this.style.background='#6d4ae0'" onmouseout="this.style.background='var(--accent)'">
              Preview Voice
            </button>
            <span style="font-size:0.72rem;color:var(--text-muted);" x-text="voicePreviewStatus"></span>
          </div>
        </div>
      </div>

      <!-- Device details table -->
      <div class="card">
        <div class="card-title" style="margin-bottom:12px">All Audio Devices</div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Name</th><th>Host API</th><th>In Ch</th><th>Out Ch</th><th>Rate</th><th>Type</th></tr></thead>
            <tbody>
              <template x-for="d in allDevices" :key="d.index">
                <tr>
                  <td style="font-variant-numeric:tabular-nums" x-text="d.index"></td>
                  <td style="color:var(--text-primary);font-weight:500" x-text="d.name"></td>
                  <td><span class="badge badge-blue" x-text="d.hostapi"></span></td>
                  <td x-text="d.max_input_channels"></td>
                  <td x-text="d.max_output_channels"></td>
                  <td x-text="d.default_samplerate + ' Hz'"></td>
                  <td>
                    <span x-show="d.max_input_channels > 0 && d.max_output_channels > 0" class="badge badge-purple">In/Out</span>
                    <span x-show="d.max_input_channels > 0 && d.max_output_channels === 0" class="badge badge-green">Input</span>
                    <span x-show="d.max_input_channels === 0 && d.max_output_channels > 0" class="badge badge-yellow">Output</span>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>

    </div>

  </div><!-- /main -->
</div><!-- /layout -->

<script>
function dashboard() {
  return {
    page: 'dashboard',
    status: { fsm_state: 'LOADING', uptime_s: 0, resources: {}, metrics: {}, emotional_state: {} },
    agents: [],
    voiceTranscript: [],
    voiceTranscriptId: 0,
    voiceEngineData: { fsm_state: null, voice_mode: 'legacy', running: false, state_duration_s: 0, emotion: null, turnSignal: null, latencyStages: {}, stats: {}, rhythm: null },
    _voiceEngineInterval: null,
    memTab: 'working',
    logTab: 'audit',
    auditEntries: [],
    logEntries: [],
    auditValid: null,
    rawMetrics: {},
    selfImprove: { performance: [], gaps: [], rag_quality: {} },
    configData: {},
    proceduralData: {},
    emotionChart: null,
    voiceStatus: { voice_mode: 'legacy', running: false, tts_available: false, stt_available: false, wake_word_available: false, current_input_device: null, current_output_device: null, fsm_state: null, modules_loaded: null },
    audioDevices: { input_devices: [], output_devices: [] },
    allDevices: [],
    selectedInputDevice: '',
    selectedOutputDevice: '',
    micActive: false,
    ttsTestStatus: '',
    ttsProvider: 'edge_tts',
    selectedVoice: 'en-US-AvaMultilingualNeural',
    ttsVoices: [],
    availableProviders: ['edge_tts'],
    providerLabels: { edge_tts: 'Edge TTS (Microsoft)', xtts_v2: 'XTTS v2 (Coqui)', kokoro: 'Kokoro' },
    voicePreviewStatus: '',
    _transcriptEvt: null,

    async init() {
      await this.pollStatus();
      await this.loadAgents();
      await this.loadLogs();
      setInterval(() => this.pollStatus(), 3000);
      setInterval(() => { if (this.page === 'logs') this.loadLogs(); }, 5000);
      this.$nextTick(() => this.initEmotionChart());
      this.connectVoiceTranscript();
    },

    async pollStatus() {
      try {
        const r = await fetch('/status');
        this.status = await r.json();
        this.updateEmotionChart();
      } catch(e) {}
    },

    async loadAgents() {
      try {
        const r = await fetch('/agents');
        const d = await r.json();
        this.agents = d.agents || [];
      } catch(e) {}
    },

    async loadLogs() {
      try {
        const r = await fetch('/security/audit?n=100');
        const d = await r.json();
        this.auditEntries = (d.entries || []).reverse();
      } catch(e) {}
      try {
        const r = await fetch('/logs/recent?n=200');
        const d = await r.json();
        this.logEntries = [...(d.logs || []), ...(d.audit || [])].sort((a,b) => (a.ts||0) - (b.ts||0)).slice(-200);
      } catch(e) {}
    },

    async verifyAudit() {
      try {
        const r = await fetch('/security/audit/verify', { method: 'POST' });
        const d = await r.json();
        this.auditValid = d.valid;
      } catch(e) { this.auditValid = false; }
    },

    async loadMetrics() {
      try {
        const r = await fetch('/metrics/summary');
        const d = await r.json();
        this.rawMetrics = d.metrics || {};
      } catch(e) {}
    },

    async loadSelfImprovement() {
      try {
        const r = await fetch('/self-improvement');
        this.selfImprove = await r.json();
      } catch(e) {}
    },

    async loadConfig() {
      try {
        const r = await fetch('/config');
        this.configData = await r.json();
      } catch(e) {}
    },

    async loadProcedural() {
      try {
        const r = await fetch('/memory/procedural');
        const d = await r.json();
        this.proceduralData = d.data || {};
      } catch(e) {}
    },

    async loadVoiceMode() {
      try {
        const [devResp, statusResp, engineResp] = await Promise.all([
          fetch('/audio/devices'),
          fetch('/audio/voice/status'),
          fetch('/voice-engine/status'),
        ]);
        this.audioDevices = await devResp.json();
        this.voiceStatus = await statusResp.json();
        const engine = await engineResp.json();
        this.voiceEngineData.fsm_state = engine.fsm_state || null;
        this.voiceEngineData.running = engine.running || false;
        this.voiceEngineData.state_duration_s = engine.state_duration_s || 0;
        this.voiceEngineData.voice_mode = this.voiceStatus.voice_mode || 'legacy';
        if (this.voiceStatus.current_input_device) this.selectedInputDevice = this.voiceStatus.current_input_device;
        if (this.voiceStatus.current_output_device) this.selectedOutputDevice = this.voiceStatus.current_output_device;
        this.micActive = this.voiceStatus.running;
      } catch(e) { console.error('loadVoiceMode', e); }
      await this.pollVoiceEngine();
      if (!this._voiceEngineInterval) {
        this._voiceEngineInterval = setInterval(() => { if (this.page === 'voice-mode') this.pollVoiceEngine(); }, 3000);
      }
    },

    async pollVoiceEngine() {
      const fetchers = [
        fetch('/voice-engine/status').then(r => r.json()).catch(() => null),
        fetch('/voice-engine/emotion').then(r => r.json()).catch(() => null),
        fetch('/voice-engine/turn-signal').then(r => r.json()).catch(() => null),
        fetch('/voice-engine/latency').then(r => r.json()).catch(() => null),
        fetch('/voice-engine/stats').then(r => r.json()).catch(() => null),
        fetch('/voice-engine/rhythm').then(r => r.json()).catch(() => null),
      ];
      const [status, emotion, turn, latency, stats, rhythm] = await Promise.all(fetchers);
      if (status) {
        this.voiceEngineData.fsm_state = status.fsm_state || this.voiceEngineData.fsm_state;
        this.voiceEngineData.running = status.running || false;
        this.voiceEngineData.state_duration_s = status.state_duration_s || 0;
      }
      if (emotion && emotion.available && emotion.emotion) {
        this.voiceEngineData.emotion = emotion.emotion;
      }
      if (turn && turn.available && turn.signal) {
        this.voiceEngineData.turnSignal = turn.signal;
      }
      if (latency && latency.available) {
        this.voiceEngineData.latencyStages = latency.stages || {};
      }
      if (stats && stats.available) {
        this.voiceEngineData.stats = stats.stats || {};
      }
      if (rhythm && rhythm.available) {
        this.voiceEngineData.rhythm = {
          user: rhythm.user_profile,
          emily: rhythm.emily_targets,
          entrainment: rhythm.entrainment_degree,
        };
      }
    },

    clearTranscript() {
      this.voiceTranscript = [];
      this.voiceTranscriptId = 0;
    },

    voiceFsmColor() {
      const m = { IDLE: '#34d399', LISTENING: '#60a5fa', PROCESSING: '#fbbf24', RESPONDING: '#a78bfa', TOOL_USE: '#22d3ee', REFLECTING: '#555570', ERROR: '#f87171', SHUTDOWN: '#f87171' };
      return m[this.voiceEngineData.fsm_state] || '#555570';
    },

    initEmotionChart() {
      const ctx = document.getElementById('emotionChart');
      if (!ctx) return;
      this.emotionChart = new Chart(ctx, {
        type: 'radar',
        data: {
          labels: ['Engagement', 'Confidence', 'Concern', 'Enthusiasm'],
          datasets: [{
            label: 'Emily',
            data: [0.5, 0.5, 0.5, 0.5],
            backgroundColor: 'rgba(124,92,252,0.15)',
            borderColor: '#7c5cfc',
            borderWidth: 2,
            pointBackgroundColor: '#7c5cfc',
            pointRadius: 4,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            r: {
              beginAtZero: true, max: 1, min: 0,
              ticks: { stepSize: 0.25, color: '#555570', backdropColor: 'transparent', font: { size: 9 } },
              grid: { color: '#1e1e30' },
              angleLines: { color: '#1e1e30' },
              pointLabels: { color: '#8888a0', font: { size: 11 } },
            }
          },
          plugins: { legend: { display: false } }
        }
      });
    },

    updateEmotionChart() {
      if (!this.emotionChart) return;
      const es = this.status.emotional_state || {};
      this.emotionChart.data.datasets[0].data = [
        es.engagement || 0.5, es.confidence || 0.5,
        es.concern || 0.5, es.enthusiasm || 0.5
      ];
      this.emotionChart.update('none');
    },

    async loadVoice() {
      try {
        const [devResp, statusResp] = await Promise.all([
          fetch('/audio/devices'),
          fetch('/audio/voice/status'),
        ]);
        this.audioDevices = await devResp.json();
        this.voiceStatus = await statusResp.json();
        const allSet = new Map();
        for (const d of [...(this.audioDevices.input_devices||[]), ...(this.audioDevices.output_devices||[])]) {
          allSet.set(d.index, d);
        }
        this.allDevices = [...allSet.values()].sort((a,b) => a.index - b.index);
        if (this.voiceStatus.current_input_device) this.selectedInputDevice = this.voiceStatus.current_input_device;
        if (this.voiceStatus.current_output_device) this.selectedOutputDevice = this.voiceStatus.current_output_device;
        this.micActive = this.voiceStatus.running;
      } catch(e) { console.error('loadVoice', e); }
      await this.loadVoiceSettings();
    },

    async setInputDevice() {
      try {
        const device = this.selectedInputDevice === '' ? null : this.selectedInputDevice;
        const r = await fetch('/audio/devices/input', {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ device })
        });
        const d = await r.json();
        this.voiceStatus.current_input_device = d.device;
      } catch(e) { console.error('setInputDevice', e); }
    },

    async setOutputDevice() {
      try {
        const device = this.selectedOutputDevice === '' ? null : this.selectedOutputDevice;
        const r = await fetch('/audio/devices/output', {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ device })
        });
        const d = await r.json();
        this.voiceStatus.current_output_device = d.device;
      } catch(e) { console.error('setOutputDevice', e); }
    },

    async testTTS() {
      this.ttsTestStatus = 'Speaking...';
      try {
        const r = await fetch('/audio/voice/test-tts', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ text: "Hello! I'm Emily, your AI assistant." })
        });
        if (r.ok) { this.ttsTestStatus = 'Done!'; }
        else {
          const d = await r.json();
          this.ttsTestStatus = d.detail || 'Failed';
        }
      } catch(e) { this.ttsTestStatus = 'Error: ' + e.message; }
      setTimeout(() => { this.ttsTestStatus = ''; }, 4000);
    },

    async loadVoiceSettings() {
      try {
        const [settingsResp, voicesResp] = await Promise.all([
          fetch('/audio/voice/settings'),
          fetch('/audio/voice/voices'),
        ]);
        const settings = await settingsResp.json();
        const voices = await voicesResp.json();
        this.ttsProvider = settings.provider;
        this.selectedVoice = voices.current_voice;
        this.availableProviders = settings.available_providers;
        this.ttsVoices = voices.voices[this.ttsProvider] || [];
      } catch(e) { console.error('loadVoiceSettings', e); }
    },

    async setVoiceProvider() {
      try {
        await fetch('/audio/voice/settings', {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ provider: this.ttsProvider })
        });
        const voicesResp = await fetch('/audio/voice/voices');
        const voices = await voicesResp.json();
        this.ttsVoices = voices.voices[this.ttsProvider] || [];
        if (this.ttsVoices.length > 0 && !this.ttsVoices.find(v => v.id === this.selectedVoice)) {
          this.selectedVoice = this.ttsVoices[0].id;
          await this.setVoice();
        }
      } catch(e) { console.error('setVoiceProvider', e); }
    },

    async setVoice() {
      try {
        await fetch('/audio/voice/settings', {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ voice: this.selectedVoice })
        });
      } catch(e) { console.error('setVoice', e); }
    },

    async previewVoice() {
      this.voicePreviewStatus = 'Speaking...';
      try {
        const r = await fetch('/audio/voice/test-tts', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ text: "Hi there, this is how I sound.", engine: this.ttsProvider })
        });
        this.voicePreviewStatus = r.ok ? 'Done!' : 'Failed';
      } catch(e) { this.voicePreviewStatus = 'Error'; }
      setTimeout(() => { this.voicePreviewStatus = ''; }, 3000);
    },

    connectVoiceTranscript() {
      try {
        const evt = new EventSource('/chat/voice-transcript');
        evt.onmessage = (e) => {
          try {
            const entry = JSON.parse(e.data);
            const now = new Date();
            const ts = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0') + ':' + now.getSeconds().toString().padStart(2,'0');
            this.voiceTranscript.push({
              id: this.voiceTranscriptId++,
              role: entry.role === 'emily' ? 'emily' : 'user',
              text: entry.text,
              time: ts,
            });
            if (this.voiceTranscript.length > 200) {
              this.voiceTranscript = this.voiceTranscript.slice(-150);
            }
            this.$nextTick(() => {
              const el = document.getElementById('voiceTranscriptBox');
              if (el) el.scrollTop = el.scrollHeight;
            });
          } catch(err) {}
        };
        evt.onerror = () => { setTimeout(() => this.connectVoiceTranscript(), 5000); evt.close(); };
        this._transcriptEvt = evt;
      } catch(e) {}
    },

    fsmColor() {
      const m = { IDLE: '#34d399', LISTENING: '#60a5fa', PROCESSING: '#fbbf24', RESPONDING: '#a78bfa', TOOL_USE: '#22d3ee', REFLECTING: '#555570', ERROR: '#f87171', SHUTDOWN: '#f87171' };
      return m[this.status.fsm_state] || '#555570';
    },

    vramPercent() {
      const r = this.status.resources || {};
      if (!r.vram_total_mb) return 0;
      return ((r.vram_used_mb / r.vram_total_mb) * 100).toFixed(1);
    },

    formatUptime(s) {
      if (!s) return '0s';
      s = Math.floor(s);
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const sec = s % 60;
      if (h > 0) return h + 'h ' + m + 'm';
      if (m > 0) return m + 'm ' + sec + 's';
      return sec + 's';
    },
  };
}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(content=_DASHBOARD_HTML)


@app.get("/voice-dashboard", response_class=HTMLResponse)
async def voice_dashboard() -> HTMLResponse:
    """Serve the dedicated voice mode dashboard from an external HTML file."""
    html_path = Path(__file__).parent / "voice_dashboard.html"
    content = await asyncio.to_thread(html_path.read_text, "utf-8")
    return HTMLResponse(content=content)
