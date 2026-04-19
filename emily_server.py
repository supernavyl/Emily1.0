"""
Emily unified server — single process for Bootstrap + API.

Runs the full cognitive system (agents, memory, ZMQ buses, voice engine,
LLM fleet, scheduler) alongside the FastAPI HTTP server in one asyncio
event loop. This replaces the separate emily-api + emily-core services.

Usage:
    uv run python emily_server.py
    # or via systemd: emily.service
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

import uvicorn
from dotenv import load_dotenv

load_dotenv()

# EMILY_VOICE_TTS env flag overrides config.tts_provider. Used for rollback
# (e.g. EMILY_VOICE_TTS=kokoro reverts voice from Orpheus to Kokoro).
# Must run BEFORE any VoiceEngineConfig / get_settings() call so pydantic-settings
# picks it up. Kept as lower-case `tts_provider` because pydantic-settings reads
# the field name case-insensitively.
import os as _os

_tts_override = _os.environ.get("EMILY_VOICE_TTS", "").strip().lower()
if _tts_override in ("orpheus", "kokoro"):
    _os.environ["tts_provider"] = _tts_override

from observability.logger import get_logger

log = get_logger(__name__)

if _tts_override in ("orpheus", "kokoro"):
    log.info("EMILY_VOICE_TTS override active: %s", _tts_override)


async def run_unified() -> None:
    """Start Bootstrap and uvicorn in the same event loop."""
    from api.app import app, set_bootstrap
    from core.bootstrap import Bootstrap

    # 1. Create and start Bootstrap (all subsystems)
    bootstrap = Bootstrap.create()

    try:
        await bootstrap.startup()
    except Exception as exc:
        log.error("bootstrap_startup_failed", error=str(exc))
        sys.exit(1)

    # 2. Wire Bootstrap into the API layer — this must happen BEFORE uvicorn
    #    starts the ASGI lifespan, so the lifespan detects unified mode.
    set_bootstrap(bootstrap)

    # 2b. Wire brain WebSocket bridge — must happen after bootstrap has a hub
    from api.app import set_brain_bridge
    from api.brain_ws import BrainWSBridge
    from core.brain_hub import get_brain_hub

    hub = get_brain_hub()
    if hub is not None:
        brain_bridge = BrainWSBridge(loop=asyncio.get_running_loop())
        hub.attach_recorder(brain_bridge.on_event)
        set_brain_bridge(brain_bridge)
        log.info("brain_ws_bridge_installed")
    else:
        log.warning("brain_ws_bridge_skipped_no_hub")

    # 3. Wire Bootstrap's subsystems into API route dependency overrides.
    #    In standalone mode, the lifespan does this. In unified mode, we do it here
    #    so the lifespan short-circuits.
    _wire_api_routes(app, bootstrap)

    log.info("emily_unified_bootstrap_complete")

    # 4. Start uvicorn — reuse this event loop (no new loop creation)
    from config import get_settings

    settings = get_settings()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=settings.api.port,
        log_level="warning",  # uvicorn access logs are noisy; Emily has its own
        loop="none",  # reuse the running loop
    )
    server = uvicorn.Server(config)

    # 5. Handle shutdown signals
    shutdown_triggered = False

    def _signal_handler() -> None:
        nonlocal shutdown_triggered
        if shutdown_triggered:
            return
        shutdown_triggered = True
        log.info("emily_shutdown_signal_received")
        bootstrap._shutdown_event.set()
        server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # 6. Run both concurrently — when either finishes, shut down the other
    try:
        await asyncio.gather(
            server.serve(),
            bootstrap.run_until_shutdown(),
        )
    except Exception as exc:
        log.error("emily_unified_runtime_error", error=str(exc))
    finally:
        # Ensure clean shutdown even if gather raises
        if not bootstrap._shutdown_event.is_set():
            bootstrap._shutdown_event.set()
        try:
            await bootstrap.shutdown()
        except Exception as exc:
            log.warning("emily_shutdown_error", error=str(exc))
        log.info("emily_unified_stopped")


def _wire_api_routes(app: Any, bootstrap: Any) -> None:
    """Wire Bootstrap-owned subsystems into API route dependency overrides."""
    from api.routes import audio as audio_routes
    from api.routes import graph as graph_routes
    from api.routes import people as people_routes
    from api.routes import query as query_routes
    from api.routes import settings as settings_routes
    from api.routes import singing as singing_routes
    from api.routes import vault as vault_routes
    from api.routes import vision as vision_routes

    settings = bootstrap.settings

    # Knowledge store — used by people and graph routes
    if bootstrap.proactive_engine is not None:
        store = bootstrap.proactive_engine._store
        app.dependency_overrides[people_routes._get_store] = lambda: store
        app.dependency_overrides[graph_routes._get_store] = lambda: store
        app.dependency_overrides[graph_routes._get_proactive] = lambda: bootstrap.proactive_engine

    # Vault — from SecurityManager
    if hasattr(bootstrap.security, "_vault"):
        vault = bootstrap.security._vault
        app.dependency_overrides[vault_routes._get_vault] = lambda: vault

    # TTS — wire audio routes
    if bootstrap.tts_manager is not None:
        audio_routes.set_audio_state(
            input_device=settings.audio.input_device,
            output_device=settings.audio.output_device,
            tts_manager=bootstrap.tts_manager,
        )

    # Singing engine
    if bootstrap.singing_manager is not None:
        singing_routes.configure(bootstrap.singing_manager)

    # Owner identity
    settings_routes.init_identity_manager(bootstrap.identity_manager)

    # Vision
    if bootstrap.vision_pipeline is not None:
        asyncio.create_task(
            vision_routes.init_vision(settings.vision, settings.llm.ollama_base_url)
        )

    # Query engine — needs knowledge store + LLM client for classification
    if bootstrap.proactive_engine is not None:
        store = bootstrap.proactive_engine._store
        vault = getattr(bootstrap.security, "_vault", None)

        from llm.tabbyapi_client import TabbyAPIClient
        from memory.query_engine import MemoryQueryEngine

        llm_client = TabbyAPIClient(
            base_url=settings.llm.tabbyapi_base_url,
            api_key=settings.llm.tabbyapi_api_key,
        )
        query_engine = MemoryQueryEngine(
            llm_client=llm_client,
            knowledge_store=store,
            vault=vault,
            nano_model=settings.llm.models.fast,
        )
        app.dependency_overrides[query_routes._get_query_engine] = lambda: query_engine


if __name__ == "__main__":
    try:
        asyncio.run(run_unified())
    except KeyboardInterrupt:
        print("\nEmily stopped.")
