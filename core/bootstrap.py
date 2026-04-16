"""
Emily system bootstrap and dependency injection.

`Bootstrap` is the root composition root. It initializes all subsystems
in dependency order, holds references to shared singletons, and manages
graceful startup/shutdown of every component.

Usage:
    async with Bootstrap.create() as emily:
        await emily.run()
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from types import TracebackType

from agents.registry import AgentRegistry
from config import EmilySettings, get_settings
from core.bus import AgentBus, PerceptionBus
from core.fsm import SystemFSM, SystemState
from core.scheduler import Scheduler
from llm.fleet import LLMFleet
from memory.manager import MemoryManager
from observability.event_recorder import EventRecorder
from observability.logger import configure_logging, get_logger
from observability.metrics import start_metrics_server
from observability.tracing import configure_tracing
from perception.audio.pipeline import AudioPipeline
from perception.system.telemetry import SystemTelemetry
from perception.vision.pipeline import VisionPipeline

_perception_system_available = True
try:
    from perception.system.config_parser import parse_all as parse_all_configs
    from perception.system.config_store import ConfigStore, set_config_store
    from perception.system.config_watcher import ConfigWatcher
    from perception.system.hyprland import HyprlandEventProducer
    from perception.system.journald import JournaldEventProducer
except ImportError:
    _perception_system_available = False
    parse_all_configs = None  # type: ignore[assignment]
    ConfigStore = None  # type: ignore[assignment,misc]
    set_config_store = None  # type: ignore[assignment]
    ConfigWatcher = None  # type: ignore[assignment,misc]
    HyprlandEventProducer = None  # type: ignore[assignment,misc]
    JournaldEventProducer = None  # type: ignore[assignment,misc]

_perception_forecaster_available = True
try:
    from perception.forecaster.manager import ForecasterManager
    from perception.forecaster.telemetry_recorder import TelemetryRecorder
except ImportError:
    _perception_forecaster_available = False
    ForecasterManager = None  # type: ignore[assignment,misc]
    TelemetryRecorder = None  # type: ignore[assignment,misc]
from persona.profile import PersonaProfile
from proactive.engine import Alert, ProactiveEngine, ProactiveScheduler
from security.manager import SecurityManager
from self_improvement.engine import SelfImprovementEngine
from users.owner_identity import OwnerIdentityManager
from voice.output_stream import AudioOutputStream
from voice.singing import SingingManager
from voice.tts import TTSManager

_automation_available = True
try:
    from integrations.automation import AutomationEngine
except ImportError:
    _automation_available = False

log = get_logger(__name__)


@dataclass
class HealthReport:
    """Result of pre-startup backend health checks."""

    ollama_ok: bool = False
    qdrant_ok: bool = False
    cuda_available: bool = False
    vram_free_mb: int = 0
    warnings: list[str] = field(default_factory=list)


# Patterns that indicate the user wants Emily to sing / generate music.
_SING_RE = re.compile(
    r"\b(?:"
    r"sing(?:\s+(?:me\s+)?(?:a\s+)?(?:song|tune|melody|lullaby|ballad|jingle))?"
    r"|serenade\s+me"
    r"|(?:can|could|please|would)\s+you\s+sing"
    r"|start\s+singing"
    r"|perform\s+(?:a\s+)?(?:song|tune)"
    r")\b",
    re.IGNORECASE,
)


def _is_singing_request(text: str) -> bool:
    return bool(_SING_RE.search(text))


_voice_engine_available = True
try:
    from voice_engine.config import VoiceEngineConfig as VE13Config
    from voice_engine.conversation import VoiceConversation
    from voice_engine.providers.llm.emily_llm import EmilyLLMProvider
    from voice_engine.providers.tts.emily_tts import EmilyTTSProvider
except ImportError:
    _voice_engine_available = False


class Bootstrap:
    """
    Root composition object. Owns and manages all Emily subsystem lifetimes.

    All subsystems are initialized lazily in `startup()` and torn down in
    reverse order in `shutdown()`. External code accesses subsystems via
    the public attributes on this object.
    """

    def __init__(self, settings: EmilySettings, brain_hub: Any | None = None) -> None:
        self.settings = settings
        self.brain_hub = brain_hub
        self.fsm = SystemFSM()
        self.scheduler = Scheduler()
        self.perception_bus = PerceptionBus()
        self.agent_bus = AgentBus(port=settings.agents.message_bus_port)
        self.telemetry: SystemTelemetry | None = None
        self.hyprland_producer: HyprlandEventProducer | None = None
        self.journald_producer: JournaldEventProducer | None = None
        self.config_watcher: ConfigWatcher | None = None
        self.config_store: ConfigStore | None = (
            ConfigStore() if _perception_system_available else None
        )
        self.vision_pipeline: VisionPipeline | None = None
        self.audio_pipeline: AudioPipeline | None = None
        self.tts_manager: TTSManager | None = None
        self.singing_manager: SingingManager | None = None
        self.audio_output: AudioOutputStream | None = None
        self.voice_engine_instance: object | None = None
        self.security: SecurityManager = SecurityManager(settings.security)
        self.self_improvement: SelfImprovementEngine = SelfImprovementEngine()
        self.fleet: LLMFleet = LLMFleet(
            settings.llm, brain_hub=brain_hub, llm_guard=self.security.llm_guard
        )
        self.memory: MemoryManager = MemoryManager(settings, brain_hub=brain_hub)
        self.identity_manager: OwnerIdentityManager = OwnerIdentityManager(
            data_path=settings.owner.identity_file
        )
        self.persona_profile: PersonaProfile = PersonaProfile()
        self.persona_profile.load()
        self.registry: AgentRegistry | None = None
        self.telemetry_recorder: TelemetryRecorder | None = None
        self.forecaster: ForecasterManager | None = None
        self.proactive_engine: ProactiveEngine | None = None
        self.proactive_scheduler: ProactiveScheduler | None = None
        self.automation_engine: object | None = None
        self.event_recorder: EventRecorder = EventRecorder(
            replay_dir=settings.replay.dir,
            compress_after_hours=settings.replay.compress_after_hours,
            enabled=settings.replay.enabled,
        )
        self._background_tasks: list[asyncio.Task[None]] = []
        self._shutdown_event = asyncio.Event()
        self._tts_ready = asyncio.Event()
        self._degraded_backends: set[str] = set()
        self._health_report: HealthReport | None = None

        if brain_hub is not None:
            self.perception_bus.set_brain_hub(brain_hub)
            self.agent_bus.set_brain_hub(brain_hub)

        # Wire event recorder into bus (full payload capture)
        self.agent_bus.set_event_recorder(self.event_recorder)

    @classmethod
    def create(
        cls,
        config_path: str = "config.yaml",
        brain_hub: Any | None = None,
    ) -> Bootstrap:
        """
        Factory: load settings and return an unstarted Bootstrap instance.

        Args:
            config_path: Path to config.yaml.
            brain_hub: Optional BrainEventHub for Brain Dashboard integration.

        Returns:
            A Bootstrap instance ready for `async with` or manual startup.
        """
        settings = get_settings()
        return cls(settings, brain_hub=brain_hub)

    async def startup(self) -> None:
        """
        Initialize all subsystems in dependency order.

        Raises:
            RuntimeError: If a critical subsystem fails to start.
        """
        s = self.settings

        # 1. Observability (must be first)
        configure_logging(log_level=s.log_level, log_format=s.observability.log_format)
        configure_tracing(
            service_name="emily",
            service_version=s.version,
            otlp_endpoint=s.observability.otlp_endpoint,
            enabled=s.observability.tracing_enabled,
        )

        log.info("emily_starting", version=s.version, name=s.name)

        hub = self.brain_hub
        if hub is not None:

            async def _on_fsm_change(old: Any, new: Any) -> None:
                await hub.emit(
                    "fsm",
                    "state_change",
                    {
                        "old": old.name,
                        "new": new.name,
                    },
                )

            self.fsm.on_transition(_on_fsm_change)

        # 2. Ensure data directories exist
        for dir_name in [s.data_dir, s.logs_dir, s.knowledge_dir, s.prompts_dir]:
            Path(dir_name).mkdir(parents=True, exist_ok=True)
        Path("prompts/archive").mkdir(parents=True, exist_ok=True)
        Path("plugins/generated").mkdir(parents=True, exist_ok=True)

        # 2a. Event recorder (replay debugger) — attach to hub and start session
        if hub is not None:
            self.event_recorder.attach(hub)
        self.event_recorder.start_session()

        # 3. Metrics server
        start_metrics_server(port=s.observability.metrics_port)

        # 4. Security (before any data access)
        await self.security.start()

        # 5. Core buses
        await self.perception_bus.start_publisher()
        await self.perception_bus.start_subscriber()
        await self.agent_bus.start()

        # 5a. System telemetry (publishes snapshots to PerceptionBus)
        self.telemetry = SystemTelemetry()
        self.telemetry.set_bus(self.perception_bus)
        self.add_background_task(self.telemetry.run())

        # 5a-ii. Telemetry recorder (persists telemetry to SQLite for forecaster)
        if _perception_forecaster_available:
            try:
                self.telemetry_recorder = TelemetryRecorder(
                    db_path=s.forecaster.telemetry_db,
                    retention_days=s.forecaster.telemetry_retention_days,
                )
                await self.telemetry_recorder.connect()
                await self.telemetry_recorder.start(self.perception_bus)
                log.info("telemetry_recorder_started")
            except (OSError, ConnectionError) as exc:
                log.warning("telemetry_recorder_start_failed", error=str(exc))
                self.telemetry_recorder = None
            except Exception as exc:  # noqa: BLE001 — startup resilience: unknown DB/config errors degrade gracefully
                log.warning("telemetry_recorder_start_failed_unexpected", error=str(exc))
                self.telemetry_recorder = None

        # 5b. Perception event producers (Hyprland, journald, config files)
        if _perception_system_available:
            self.hyprland_producer = HyprlandEventProducer(self.perception_bus)
            await self.hyprland_producer.start()

            self.journald_producer = JournaldEventProducer(self.perception_bus)
            await self.journald_producer.start()

            # 5c. Config intelligence — parse host configs into SQLite
            self.config_store.open()
            set_config_store(self.config_store)
            try:
                count = await asyncio.to_thread(parse_all_configs, self.config_store)
                log.info("config_intelligence_ready", entries=count)
            except (OSError, ValueError) as exc:
                log.warning("config_intelligence_parse_failed", error=str(exc))
            except Exception as exc:  # noqa: BLE001 — startup resilience: config parse is best-effort
                log.warning("config_intelligence_parse_failed_unexpected", error=str(exc))

            # Config watcher — triggers re-parse on file changes
            self.config_watcher = ConfigWatcher(
                self.perception_bus,
                on_change=lambda _path: parse_all_configs(self.config_store),
            )
            await self.config_watcher.start()

        # 6. Scheduler
        await self.scheduler.start()

        # 7. LLM fleet
        await self.fleet.startup()

        # 7a. Backend health checks (after fleet so Ollama client is ready)
        self._health_report = await self._verify_backends()

        # 8. Memory system
        await self.memory.startup()
        self.memory.set_fleet(self.fleet)
        await self._wire_retriever()

        # 8a. Document ingestion pipeline (non-critical)
        self.ingestor = None
        self.rag_watcher = None
        try:
            from rag.ingestor import DocumentIngestor
            from rag.watcher import RAGFileWatcher

            self.ingestor = DocumentIngestor(
                config=s.rag,
                vector_store=getattr(self.memory, "_retriever", None)
                and getattr(self.memory._retriever, "_vector_store", None),
            )
            self.rag_watcher = RAGFileWatcher(
                config=s.rag,
                on_file_change=self.ingestor.ingest_file,
            )
            await self.rag_watcher.start()
            log.info("rag_ingestion_pipeline_started", watch_dirs=s.rag.watch_dirs)
        except ImportError as exc:
            log.warning("rag_ingestion_pipeline_not_installed", error=str(exc))
        except (OSError, ConnectionError) as exc:
            log.warning("rag_ingestion_pipeline_failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — startup resilience: RAG is optional subsystem
            log.warning("rag_ingestion_pipeline_failed_unexpected", error=str(exc))

        # Load owner identity (non-critical)
        try:
            await self.identity_manager.load()
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            log.warning("identity_manager_load_failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — startup resilience: identity is optional
            log.warning("identity_manager_load_failed_unexpected", error=str(exc))

        # 9. Agent registry
        self.registry = AgentRegistry(
            self.agent_bus,
            self.fleet,
            self.memory,
            settings=self.settings,
            self_improvement=self.self_improvement,
        )
        await self.registry.start_all()
        self.add_background_task(self.agent_bus.run())

        # 9a. Self-improvement idle cycle (every 30 min)
        self.add_background_task(self._idle_improvement_loop())
        # 9b. First reflection 15 min after startup (gives time to accumulate episodes)
        self.add_background_task(self._schedule_initial_reflection())
        # 9c. Memory consolidation loop (summarize unsummarized episodes)
        self.add_background_task(self._memory_consolidation_loop())

        # 9d. System profiler — gives Emily persistent, always-current PC knowledge
        self._voice_active_event = asyncio.Event()  # cleared during active voice turns
        self.system_profiler: object | None = None
        try:
            from plugins.builtin.system_profiler import initialize as _init_profiler

            self.system_profiler = await _init_profiler(
                voice_active_flag=self._voice_active_event,
            )
            log.info("system_profiler_ready")
        except ImportError as exc:
            log.warning("system_profiler_not_available", error=str(exc))
        except (OSError, RuntimeError) as exc:
            log.warning("system_profiler_start_failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — startup resilience: profiler is optional subsystem
            log.warning("system_profiler_start_failed_unexpected", error=str(exc))

        # 9e. Proactive engine (non-critical)
        try:
            from memory.knowledge_store import KnowledgeStore

            knowledge_store = KnowledgeStore()
            await knowledge_store.connect()
            self.proactive_engine = ProactiveEngine(store=knowledge_store)
            self.proactive_scheduler = ProactiveScheduler(
                self.proactive_engine, check_interval_minutes=30
            )
            self.proactive_scheduler.on_alert(self._on_proactive_alert)
            await self.proactive_scheduler.start()
            log.info("proactive_engine_started")
        except ImportError as exc:
            log.warning("proactive_engine_import_failed", error=str(exc))
        except (OSError, ConnectionError) as exc:
            log.warning("proactive_engine_start_failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — startup resilience: proactive is optional subsystem
            log.warning("proactive_engine_start_failed_unexpected", error=str(exc))

        # 9f. Forecaster (non-critical — system state prediction)
        if not _perception_forecaster_available:
            log.warning("forecaster_not_available", reason="perception.forecaster not installed")
        else:
            try:
                from pathlib import Path as _Path

                model_dir = _Path(s.forecaster.model_dir)
                self.forecaster = ForecasterManager(
                    bus=self.perception_bus,
                    model_dir=model_dir,
                    seq_length=s.forecaster.seq_length,
                    hidden_size=s.forecaster.hidden_size,
                    train_interval=s.forecaster.train_interval_snapshots,
                    anomaly_threshold=s.forecaster.anomaly_threshold_sigma,
                    min_history=s.forecaster.min_history,
                    enabled=s.forecaster.enabled,
                    recorder=self.telemetry_recorder,
                )
                await self.forecaster.start()
                log.info("forecaster_started")

                # Update proactive engine with forecaster reference
                if self.proactive_engine is not None:
                    self.proactive_engine.set_forecaster(self.forecaster)
            except ImportError as exc:
                log.warning("forecaster_import_failed", error=str(exc))
            except (OSError, RuntimeError) as exc:
                log.warning("forecaster_start_failed", error=str(exc))
            except Exception as exc:  # noqa: BLE001 — startup resilience: forecaster is optional subsystem
                log.warning("forecaster_start_failed_unexpected", error=str(exc))

        # 10. Vision pipeline (non-critical — degrade gracefully)
        try:
            self.vision_pipeline = VisionPipeline(
                config=s.vision,
                bus=self.perception_bus,
                vision_model=s.llm.models.vision,
                ollama_url=s.llm.ollama_base_url,
            )
            await self.vision_pipeline.start()
        except ImportError as exc:
            log.warning("vision_pipeline_not_available", error=str(exc))
            self.vision_pipeline = None
        except (OSError, RuntimeError) as exc:
            log.warning("vision_pipeline_start_failed", error=str(exc))
            self.vision_pipeline = None
        except Exception as exc:  # noqa: BLE001 — startup resilience: vision pipeline is optional
            log.warning("vision_pipeline_start_failed_unexpected", error=str(exc))
            self.vision_pipeline = None

        # 10b. VRAM coordinator for vision model swapping
        try:
            from llm.vram_coordinator import VRAMCoordinator, set_vram_coordinator

            if s.vision.vram_swap_enabled and hasattr(self.fleet, "_llamacpp"):
                vram_coord = VRAMCoordinator(
                    llamacpp_client=self.fleet._llamacpp,
                    ollama_url=s.llm.ollama_base_url,
                    enabled=s.vision.vram_swap_enabled,
                )
                set_vram_coordinator(vram_coord)
                log.info("vram_coordinator_initialized")
        except ImportError as exc:
            log.warning("vram_coordinator_not_available", error=str(exc))
        except (RuntimeError, OSError) as exc:
            log.warning("vram_coordinator_init_failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — startup resilience: VRAM coordinator is optional
            log.warning("vram_coordinator_init_failed_unexpected", error=str(exc))

        # 10c. Visual context buffer configuration
        try:
            from perception.vision.context import get_visual_context

            get_visual_context().configure(
                max_entries=s.vision.visual_context_max_entries,
                ttl_s=s.vision.visual_context_ttl_s,
            )
        except (ImportError, AttributeError) as exc:
            log.warning("visual_context_config_failed", error=str(exc))

        # 8-10. Voice mode selection
        self._voice_mode_enabled = (
            _voice_engine_available and hasattr(s, "voice_engine") and s.voice_engine.enabled
        )

        # TTS is always loaded (used by API routes and legacy bridge)
        self.tts_manager = TTSManager(s.tts)
        self.audio_output = AudioOutputStream(output_device=s.audio.output_device)
        self.add_background_task(self._load_tts())

        # Singing engine (non-critical — degrades gracefully if no engines installed)
        if s.singing.enabled:
            self.singing_manager = SingingManager(s.singing)
            self.add_background_task(self._load_singing())

        if self._voice_mode_enabled:
            log.info("voice_mode_v13", msg="Using VoiceEngine 1.3 integrated with Emily brain")
            from llm.prompt_builder import PromptBuilder

            ve_config = VE13Config(  # type: ignore[possibly-undefined]
                stt_provider=s.voice_engine.stt_provider,
                stt_model=s.stt.model,
                vad_threshold=s.voice_engine.vad_threshold,
                min_speech_ms=s.voice_engine.min_speech_ms,
                min_silence_ms=s.voice_engine.min_silence_ms,
            )

            # Breath injector (non-critical — degrades to no-breath TTS)
            breath_injector = None
            try:
                if s.voice_engine.breath_injector.enabled:
                    from voice_engine.processing.breath_injector import BreathInjector

                    breath_injector = BreathInjector(s.voice_engine.breath_injector)
                    log.info(
                        "breath_injector_ready", density=s.voice_engine.breath_injector.density
                    )
            except (ImportError, OSError) as exc:
                log.warning("breath_injector_not_available", error=str(exc)[:200])
            except Exception as exc:  # noqa: BLE001
                log.warning("breath_injector_failed", error=str(exc)[:200])
            self._breath_injector = breath_injector

            # Voice tool orchestrator (non-critical — degrades to no-tools-in-voice)
            voice_tool_orchestrator = None
            try:
                from plugins.registry import PluginRegistry
                from voice_engine.processing.voice_tools import VoiceToolOrchestrator

                voice_registry = PluginRegistry()
                _browser_cfg = {
                    "headless": s.tools.browser.headless,
                    "idle_timeout_s": s.tools.browser.idle_timeout_s,
                    "max_pages": s.tools.browser.max_pages_before_restart,
                }
                voice_registry.load_builtins(
                    tool_kwargs={
                        "web_search": {"searxng_url": s.tools.web_search_url},
                        "home_assistant": {
                            "ha_url": s.tools.home_assistant.url,
                            "token": s.tools.home_assistant.token,
                        },
                        "browser_search": {"browser_config": _browser_cfg},
                        "browser_fetch": {"browser_config": _browser_cfg},
                    }
                )
                voice_tool_orchestrator = VoiceToolOrchestrator(
                    fleet=self.fleet,
                    prompt_builder=PromptBuilder(),
                    registry=voice_registry,
                )
                log.info("voice_tool_orchestrator_ready", n_tools=len(voice_registry))
            except ImportError as exc:
                log.warning("voice_tool_orchestrator_not_available", error=str(exc)[:200])
            except Exception as exc:  # noqa: BLE001 — startup resilience: voice tools are optional
                log.warning("voice_tool_orchestrator_failed", error=str(exc)[:200])

            # Adapter: routes voice LLM calls through Emily's fleet + memory
            emily_llm = EmilyLLMProvider(  # type: ignore[possibly-undefined]
                fleet=self.fleet,
                memory=self.memory,
                prompt_builder=PromptBuilder(),
                persona=self.persona_profile,
                identity_manager=self.identity_manager,
                tool_orchestrator=voice_tool_orchestrator,
                self_improvement=self.self_improvement,
            )
            self._emily_llm_provider = emily_llm
            # Adapter: reuses Emily's already-loaded Kokoro TTS instance
            emily_tts = EmilyTTSProvider(tts_manager=self.tts_manager)  # type: ignore[possibly-undefined]

            self.voice_engine_instance = VoiceConversation(  # type: ignore[possibly-undefined]
                ve_config,
                llm=emily_llm,
                tts=emily_tts,
            )
            self.add_background_task(self._start_voice_engine())
        else:
            log.info("voice_mode_legacy", msg="Using legacy half-duplex pipeline + bridge")
            self.audio_pipeline = AudioPipeline(settings=s, bus=self.perception_bus)
            self.add_background_task(self._start_audio_pipeline())
            self.add_background_task(self._perception_tts_bridge())

        # 11b. Automation engine (integrations layer)
        if _automation_available:
            try:
                from plugins.registry import PluginRegistry

                plugin_reg = PluginRegistry()
                plugin_reg.load_builtins(
                    tool_kwargs={
                        "discord": {
                            "bot_token": getattr(
                                getattr(s, "integrations", None), "discord", {}
                            ).get("bot_token", "")
                            if hasattr(s, "integrations")
                            else "",
                            "default_channel_id": getattr(
                                getattr(s, "integrations", None), "discord", {}
                            ).get("default_channel_id", "")
                            if hasattr(s, "integrations")
                            else "",
                        },
                    }
                )
                self.automation_engine = AutomationEngine(  # type: ignore[possibly-undefined]
                    plugin_registry=plugin_reg,
                    fleet=self.fleet,
                )
                self.add_background_task(self.automation_engine.start())  # type: ignore[union-attr]
                log.info("automation_engine_initialized")
            except ImportError as exc:
                log.warning("automation_engine_import_failed", error=str(exc)[:200])
            except Exception as exc:  # noqa: BLE001 — startup resilience: automation is optional
                log.warning("automation_engine_init_failed", error=str(exc)[:200])

        # Wire voice engine refs into API routes
        self._wire_api_voice_state()

        # 11. Register signal handlers for graceful shutdown
        #     (fails gracefully when the loop runs on a non-main thread,
        #      e.g. inside a QThread for the GUI; Qt handles quit instead)
        loop = asyncio.get_running_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_signal)
        except (ValueError, RuntimeError):
            log.info("signal_handlers_skipped_non_main_thread")

        log.info("emily_ready")

    async def shutdown(self) -> None:
        """
        Gracefully shut down all subsystems in reverse initialization order.
        """
        log.info("emily_shutting_down")
        await self.fsm.force_transition(SystemState.SHUTDOWN)

        # Cancel background tasks
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Voice engine (VoiceConversation) stops when its task is cancelled above

        # Close browser if it was used
        try:
            from plugins.builtin.browser import BrowserManager

            await BrowserManager.close()
        except ImportError:
            pass  # Browser plugin not installed
        except Exception:  # noqa: BLE001 — shutdown cleanup: best-effort, never block shutdown
            log.debug("browser_close_failed", exc_info=True)

        # Stop automation engine
        if self.automation_engine is not None:
            await self.automation_engine.stop()  # type: ignore[union-attr]

        # Stop audio pipeline
        if self.audio_pipeline:
            self.audio_pipeline.stop()

        # Stop vision pipeline
        if self.vision_pipeline:
            await self.vision_pipeline.stop()

        # Stop agent registry
        if self.registry is not None:
            await self.registry.stop_all()

        # Persist voice/chat session as an episode before closing memory
        with contextlib.suppress(Exception):
            await self.memory.end_session()

        # Stop memory
        await self.memory.shutdown()

        # Stop security services
        await self.security.stop()

        # Stop event recorder (flush + compress old sessions)
        self.event_recorder.end_session()
        self.event_recorder.compress_old_sessions()

        # Stop perception event producers
        if self.hyprland_producer is not None:
            self.hyprland_producer.stop()
        if self.journald_producer is not None:
            self.journald_producer.stop()
        if self.config_watcher is not None:
            self.config_watcher.stop()

        # Stop config intelligence
        if self.config_store is not None:
            self.config_store.close()

        # Stop forecaster (before bus shutdown)
        if self.forecaster is not None:
            await self.forecaster.stop()

        # Stop telemetry recorder (before bus shutdown)
        if self.telemetry_recorder is not None:
            await self.telemetry_recorder.close()

        # Stop system telemetry
        if self.telemetry is not None:
            self.telemetry.stop()

        # Stop buses
        await self.scheduler.stop()
        self.agent_bus.stop()
        self.perception_bus.stop()

        log.info("emily_shutdown_complete")

    def _handle_signal(self) -> None:
        """Signal handler: trigger graceful shutdown."""
        log.info("shutdown_signal_received")
        self._shutdown_event.set()

    def add_background_task(
        self,
        coro: Coroutine[Any, Any, None],
    ) -> asyncio.Task[None]:
        """
        Register and start a long-running background coroutine.

        Args:
            coro: A coroutine to run indefinitely.

        Returns:
            The created asyncio Task.
        """
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        return task

    async def _verify_backends(self) -> HealthReport:
        """
        Run health checks against all configured backends before agent registration.

        Checks Ollama, Qdrant (if semantic memory is enabled), CUDA availability,
        and free VRAM. Individual check failures are non-fatal — they are logged
        and added to ``self._degraded_backends``. A ``RuntimeError`` is raised
        only when no LLM backend at all is reachable.

        Returns:
            A ``HealthReport`` populated with per-backend results.
        """
        import subprocess

        import httpx

        report = HealthReport()
        s = self.settings

        # --- Ollama ping ---
        ollama_url = s.llm.ollama_base_url + "/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(ollama_url)
                resp.raise_for_status()
            report.ollama_ok = True
            log.info("health_check_ollama_ok", url=s.llm.ollama_base_url)
        except (httpx.HTTPError, OSError, ConnectionError, TimeoutError) as exc:
            msg = f"Ollama unreachable at {s.llm.ollama_base_url}: {exc}"
            log.warning("health_check_ollama_failed", error=str(exc))
            report.warnings.append(msg)
            self._degraded_backends.add("ollama")

        # --- Qdrant ping (only when semantic memory is configured) ---
        semantic_enabled = getattr(s.memory.semantic, "enabled", True)
        if semantic_enabled:
            qdrant_url = s.memory.semantic.qdrant_url + "/collections"
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(qdrant_url)
                    resp.raise_for_status()
                report.qdrant_ok = True
                log.info("health_check_qdrant_ok", url=s.memory.semantic.qdrant_url)
            except (httpx.HTTPError, OSError, ConnectionError, TimeoutError) as exc:
                msg = f"Qdrant unreachable at {s.memory.semantic.qdrant_url}: {exc}"
                log.warning("health_check_qdrant_failed", error=str(exc))
                report.warnings.append(msg)
                self._degraded_backends.add("qdrant")
        else:
            log.info("health_check_qdrant_skipped", reason="semantic_memory_disabled")

        # --- CUDA availability ---
        try:
            import torch  # lazy import — torch is an optional dependency

            report.cuda_available = torch.cuda.is_available()
            if report.cuda_available:
                log.info("health_check_cuda_ok")
            else:
                log.warning("health_check_cuda_unavailable")
                report.warnings.append("CUDA is not available — GPU acceleration disabled")
        except ImportError:
            log.info("health_check_cuda_skipped", reason="torch_not_installed")

        # --- Free VRAM via nvidia-smi ---
        async def _query_vram() -> int:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    first_line = result.stdout.strip().splitlines()[0]
                    return int(first_line.strip())
            except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                pass
            return 0

        report.vram_free_mb = await _query_vram()
        if report.vram_free_mb > 0:
            log.info("health_check_vram", free_mb=report.vram_free_mb)
        else:
            log.info("health_check_vram_unavailable", reason="nvidia-smi_not_available_or_no_gpu")

        # --- Critical failure guard: no LLM backend at all ---
        # If Ollama is down AND TabbyAPI is also unreachable, Emily cannot chat.
        tabbyapi_ok = False
        tabbyapi_url = s.llm.tabbyapi_base_url + "/v1/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(tabbyapi_url)
                resp.raise_for_status()
            tabbyapi_ok = True
            log.info("health_check_tabbyapi_ok", url=s.llm.tabbyapi_base_url)
        except (httpx.HTTPError, OSError, ConnectionError, TimeoutError) as exc:
            log.info("health_check_tabbyapi_unreachable", error=str(exc))

        if not report.ollama_ok and not tabbyapi_ok:
            raise RuntimeError("No LLM backend available — cannot start Emily")

        if report.warnings:
            log.warning(
                "health_check_degraded_backends",
                degraded=list(self._degraded_backends),
                warnings=report.warnings,
            )
        else:
            log.info("health_check_all_ok")

        return report

    async def _wire_retriever(self) -> None:
        """Create HybridRetriever and attach to memory.

        When Qdrant is healthy: full hybrid mode (BM25 + dense + reranker).
        When Qdrant is degraded: BM25-only keyword search still works.
        """
        try:
            from memory.semantic.bm25 import BM25Index
            from memory.semantic.reranker import CrossEncoderReranker
            from memory.semantic.retriever import HybridRetriever
            from memory.semantic.vector_store import QdrantVectorStore

            s = self.settings

            # Vector store: only create if Qdrant passed health check
            vector_store = None
            if "qdrant" not in self._degraded_backends:
                try:
                    vector_store = QdrantVectorStore(config=s.memory.semantic)
                    await vector_store.ensure_collection()
                except (OSError, ConnectionError, TimeoutError) as exc:
                    log.warning("qdrant_connect_failed_bm25_only", error=str(exc))
                    self._degraded_backends.add("qdrant")
                except Exception as exc:  # noqa: BLE001 — Qdrant client may raise varied errors
                    log.warning("qdrant_connect_failed_bm25_only_unexpected", error=str(exc))
                    self._degraded_backends.add("qdrant")

            # BM25: always available (returns [] when index is empty)
            bm25 = BM25Index(index_path=s.memory.semantic.bm25_index_path)
            bm25.load()

            # Reranker: only useful with dense results, skip in BM25-only mode
            reranker = None
            if vector_store is not None:
                try:
                    reranker = CrossEncoderReranker()
                    await reranker.load()
                except (OSError, RuntimeError, ImportError) as exc:
                    log.warning("reranker_load_failed", error=str(exc))

            async def _embed(text: str) -> list[float]:
                result = await self.fleet.embed(text)
                return result.embedding

            retriever = HybridRetriever(
                config=s.rag,
                vector_store=vector_store,
                bm25=bm25,
                embedder=_embed,
                reranker=reranker,
            )
            self.memory.set_retriever(retriever)
            mode = "hybrid" if vector_store else "bm25_only"
            log.info("retriever_wired", mode=mode)
        except ImportError as exc:
            log.warning("retriever_import_failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — startup resilience: retriever is optional
            log.warning("retriever_unavailable_degraded_mode", error=str(exc))

    async def _start_audio_pipeline(self) -> None:
        """Background task: load audio models and start the capture pipeline."""
        try:
            assert self.audio_pipeline is not None
            log.info("audio_pipeline_loading")
            await self.audio_pipeline.load()
            await self.audio_pipeline.start()
        except (OSError, RuntimeError) as exc:
            log.error("audio_pipeline_start_failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 — startup resilience: audio pipeline is non-critical
            log.error("audio_pipeline_start_failed_unexpected", error=str(exc))

    async def _load_tts(self) -> None:
        """Background task: load TTS engine models."""
        try:
            assert self.tts_manager is not None
            await self.tts_manager.load()
            log.info("tts_engines_loaded")
            self._tts_ready.set()
            if self.audio_output is not None:
                ai = getattr(self, "identity_manager", None)
                name = ai.ai_name if ai else "Emily"
                greeting = f"Hey, {name} here. What's on your mind?"
                log.info("startup_greeting_speaking")
                chunks = self.tts_manager.speak(text=greeting)
                await self.audio_output.play_stream(chunks)
                log.info("startup_greeting_complete")
        except (OSError, RuntimeError, ImportError) as exc:
            log.error("tts_load_failed", error=str(exc))
            self._tts_ready.set()  # unblock waiters even on failure
        except Exception as exc:  # noqa: BLE001 — startup resilience: TTS load must unblock waiters
            log.error("tts_load_failed_unexpected", error=str(exc))
            self._tts_ready.set()  # unblock waiters even on failure

    async def _load_singing(self) -> None:
        """Background task: load singing engine models."""
        try:
            assert self.singing_manager is not None
            await self.singing_manager.load()
            log.info("singing_engines_loaded")
        except (OSError, RuntimeError, ImportError) as exc:
            log.warning("singing_load_failed", error=str(exc)[:200])

    def _wire_api_voice_state(self) -> None:
        """Inject voice engine and audio state into API route modules."""
        try:
            from api.routes import audio as audio_routes

            audio_routes.set_audio_state(
                input_device=self.settings.audio.input_device,
                output_device=self.settings.audio.output_device,
                audio_pipeline=self.audio_pipeline,
                tts_manager=self.tts_manager,
                voice_engine=self.voice_engine_instance,
                emily_llm=getattr(self, "_emily_llm_provider", None),
                breath_injector=getattr(self, "_breath_injector", None),
            )
        except ImportError:
            pass

        try:
            from api.routes.voice_engine import configure_voice_engine_routes

            configure_voice_engine_routes(engine=self.voice_engine_instance)
        except ImportError:
            pass

        try:
            from api.routes.settings import set_identity_manager

            set_identity_manager(self.identity_manager)
        except ImportError:
            pass

        try:
            from api.routes.integrations import configure as configure_integrations

            configure_integrations(
                automation_engine=self.automation_engine,
                fleet=self.fleet,
            )
        except ImportError:
            pass

        try:
            from api.routes.singing import configure as configure_singing

            if self.singing_manager is not None:
                configure_singing(self.singing_manager)
        except ImportError:
            pass

    async def _start_voice_engine(self) -> None:
        """Background task: run the VoiceEngine 1.3 conversation loop."""
        try:
            assert self.voice_engine_instance is not None
            log.info("voice_engine_v13_starting")

            # Wait for TTS to finish loading before onboarding tries to speak
            try:
                await asyncio.wait_for(self._tts_ready.wait(), timeout=30.0)
            except TimeoutError:
                log.warning("tts_load_timeout_continuing_without_greeting")

            # First-run onboarding disabled — concurrent TTS calls cause
            # heap corruption (double free) in Kokoro's C extension.
            # TODO: re-enable with sequential TTS once the root cause is fixed.
            if not self.identity_manager.has_owner:
                log.info("first_run_onboarding_skipped_no_owner")

            await self.voice_engine_instance.run()  # type: ignore[union-attr]
        except (OSError, RuntimeError) as exc:
            log.error("voice_engine_start_failed", error=str(exc)[:200])
            self.voice_engine_instance = None
            log.info("falling_back_to_legacy_bridge")
            await self._perception_tts_bridge()
            return
        except Exception as exc:  # noqa: BLE001 — startup resilience: voice engine fallback to legacy
            log.error("voice_engine_start_failed_unexpected", error=str(exc)[:200])
            self.voice_engine_instance = None
            log.info("falling_back_to_legacy_bridge")
            await self._perception_tts_bridge()

    async def _perception_tts_bridge(self) -> None:
        """
        Bridge: listen for audio.transcript on PerceptionBus, run LLM, speak back.

        Uses streaming LLM -> sentence chunking -> per-sentence TTS for low latency.
        Falls back to batch mode if streaming client is unavailable.
        """
        log.info("perception_tts_bridge_started")

        await asyncio.sleep(0.5)

        async for event in self.perception_bus.iter_events():
            try:
                if event.type == "audio.transcript":
                    text = event.payload.get("text", "").strip()
                    if not text:
                        continue

                    log.info("voice_input_received", text=text[:80])
                    self._write_transcript("user", text)
                    await self.fsm.force_transition(SystemState.PROCESSING)

                    response = await self._stream_llm_and_speak(text)
                    if response:
                        self._write_transcript("emily", response)

                    await self.fsm.force_transition(SystemState.IDLE)

                elif event.type == "audio.wake_word_detected":
                    log.info("wake_word_detected_in_bridge", keyword=event.payload.get("keyword"))
                    await self.fsm.force_transition(SystemState.LISTENING)

            except Exception as exc:  # noqa: BLE001 — event loop resilience: must not crash on any event
                log.error("perception_bridge_error", error=str(exc))
                with contextlib.suppress(Exception):
                    await self.fsm.force_transition(SystemState.IDLE)

    async def _stream_llm_and_speak(self, user_text: str) -> str:
        """
        Stream LLM tokens, chunk into sentences, synthesize each sentence
        immediately for low perceived latency.

        Falls back to batch mode (full response then speak) on error.
        Intercepts singing requests before they reach the LLM.

        Args:
            user_text: Transcribed user speech.

        Returns:
            Full response text.
        """
        if self.singing_manager is not None and _is_singing_request(user_text):
            return await self._sing_response(user_text)
        try:
            return await self._streaming_pipeline(user_text)
        except Exception as exc:  # noqa: BLE001 — resilience: streaming failure falls back to batch
            log.warning("streaming_pipeline_unavailable_batch_fallback", error=str(exc))
            return await self._batch_pipeline(user_text)

    async def _sing_response(self, user_text: str) -> str:
        """Handle a singing request from the voice bridge.

        Streams audio from SingingManager directly to the audio output device.

        Args:
            user_text: The original user utterance (used as the song prompt).

        Returns:
            Acknowledgment string written to the transcript.
        """
        assert self.singing_manager is not None

        # Tell the user something before generation starts (can take a few seconds).
        if self.tts_manager and self.audio_output:
            intro = "Sure, let me sing something for you!"
            chunks = self.tts_manager.speak(text=intro)
            await self.audio_output.play_stream(chunks)

        await self.fsm.force_transition(SystemState.RESPONDING)
        log.info("singing_request_detected", prompt=user_text[:80])

        try:
            if self.audio_output:
                await self.audio_output.play_stream(self.singing_manager.sing(user_text, mode=None))
        except RuntimeError as exc:
            log.error("singing_failed", error=str(exc)[:200])
            if self.tts_manager and self.audio_output:
                msg = "Sorry, no singing engine is available right now."
                chunks = self.tts_manager.speak(text=msg)
                await self.audio_output.play_stream(chunks)
            return "Sorry, no singing engine is available right now."

        return f"[sang: {user_text[:60]}]"

    async def _streaming_pipeline(self, user_text: str) -> str:
        """
        Stream LLM output sentence by sentence into TTS.

        Each sentence is synthesized and played as soon as it is complete,
        without waiting for the full LLM response.
        """
        from llm.client import ChatMessage
        from llm.streaming import StreamProcessor
        from llm.tabbyapi_client import TabbyAPIClient

        client = TabbyAPIClient(
            base_url=self.settings.llm.tabbyapi_base_url,
            api_key=self.settings.llm.tabbyapi_api_key,
        )
        processor = StreamProcessor(tts_chunk_min_chars=40)
        full_response = ""

        try:
            from llm.prompt_builder import PromptBuilder

            _micro = None
            if self.system_profiler is not None:
                try:
                    _micro = self.system_profiler.get_micro_excerpt()
                except (AttributeError, RuntimeError):
                    pass
            _voice_prompt = PromptBuilder().build_voice_system_prompt(
                system_profile_excerpt=_micro,
            )
            messages = [
                ChatMessage(role="system", content=_voice_prompt),
                ChatMessage(role="user", content=user_text),
            ]

            async def _token_iter():
                async for chunk in client.chat_stream(
                    model=self.settings.llm.models.fast,
                    messages=messages,
                ):
                    if chunk.content:
                        yield chunk.content

            await self.fsm.force_transition(SystemState.RESPONDING)

            async for sentence in processor.iter_sentences(_token_iter()):
                full_response += sentence + " "
                log.info("streaming_sentence", text=sentence[:60])

                if self.tts_manager and self.audio_output:
                    chunks = self.tts_manager.speak(text=sentence)
                    await self.audio_output.play_stream(chunks)

        finally:
            await client.close()

        return full_response.strip()

    async def _batch_pipeline(self, user_text: str) -> str:
        """Batch fallback: get full LLM response, then speak it."""
        response = await self._get_llm_response(user_text)
        if not response:
            return ""

        log.info("voice_response_ready", response=response[:80])
        await self.fsm.force_transition(SystemState.RESPONDING)

        if self.tts_manager and self.audio_output:
            chunks = self.tts_manager.speak(text=response)
            await self.audio_output.play_stream(chunks)

        return response

    _TRANSCRIPT_PATH = Path("logs/voice_transcript.jsonl")

    def _write_transcript(self, role: str, text: str) -> None:
        """Append a voice transcript entry to the shared JSONL log."""
        try:
            self._TRANSCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
            entry = {"role": role, "text": text, "ts": time.time(), "source": "voice"}
            with self._TRANSCRIPT_PATH.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as exc:
            log.error("transcript_write_failed", error=str(exc))

    async def _get_llm_response(self, user_text: str) -> str:
        """
        Quick LLM call for voice conversation.

        Uses Ollama directly for the fast model to keep the bridge simple.

        Args:
            user_text: Transcribed user speech.

        Returns:
            LLM response text.
        """
        try:
            from llm.client import ChatMessage
            from llm.tabbyapi_client import TabbyAPIClient

            client = TabbyAPIClient(
                base_url=self.settings.llm.tabbyapi_base_url,
                api_key=self.settings.llm.tabbyapi_api_key,
            )
            try:
                from llm.prompt_builder import PromptBuilder

                _micro = None
                if self.system_profiler is not None:
                    try:
                        _micro = self.system_profiler.get_micro_excerpt()
                    except (AttributeError, RuntimeError):
                        pass
                _voice_prompt = PromptBuilder().build_voice_system_prompt(
                    system_profile_excerpt=_micro,
                )
                result = await client.chat(
                    model=self.settings.llm.models.fast,
                    messages=[
                        ChatMessage(role="system", content=_voice_prompt),
                        ChatMessage(role="user", content=user_text),
                    ],
                )
                return result.content
            finally:
                await client.close()
        except (ConnectionError, TimeoutError, OSError) as exc:
            log.error("llm_voice_response_failed", error=str(exc))
            return ""
        except Exception as exc:  # noqa: BLE001 — resilience: LLM failure must not crash voice loop
            log.error("llm_voice_response_failed_unexpected", error=str(exc))
            return ""

    async def _idle_improvement_loop(self) -> None:
        """Background task: run the self-improvement idle cycle every 30 minutes."""
        while True:
            await asyncio.sleep(30 * 60)
            try:
                await self.self_improvement.run_idle_cycle()
            except Exception as exc:  # noqa: BLE001 — background loop: must not crash on any error
                log.warning("idle_cycle_error", error=str(exc))

    async def _on_proactive_alert(self, alert: Alert) -> None:
        """Handle a proactive alert from the scheduler."""
        if self.brain_hub is not None:
            await self.brain_hub.emit("proactive", "alert", alert.to_dict())
        log.info(
            "proactive_alert",
            alert_type=alert.alert_type,
            severity=alert.severity,
            title=alert.title,
        )

    async def _memory_consolidation_loop(self) -> None:
        """Background task: summarize unsummarized episodes periodically."""
        interval = self.settings.memory.consolidation.idle_trigger_minutes * 60
        limit = self.settings.memory.consolidation.max_episodes_per_run
        while True:
            await asyncio.sleep(interval)
            try:
                count = await self.memory.summarize_unsummarized(limit=limit)
                if count:
                    log.info("memory_consolidation_ran", summarized=count)
            except Exception as exc:  # noqa: BLE001 — background loop: must not crash on any error
                log.warning("memory_consolidation_error", error=str(exc))

    async def _schedule_initial_reflection(self) -> None:
        """Trigger the first reflection cycle 15 minutes after startup."""
        await asyncio.sleep(15 * 60)
        try:
            await self.agent_bus.send_to(
                recipient="ReflectionAgent",
                msg_type="reflection.trigger",
                payload={},
                sender="bootstrap",
            )
            log.info("initial_reflection_triggered")
        except (ConnectionError, OSError, RuntimeError) as exc:
            log.warning("initial_reflection_schedule_failed", error=str(exc))

    async def run_until_shutdown(self) -> None:
        """
        Block until a shutdown signal is received.

        Shutdown is handled by the context manager (__aexit__).
        """
        await self._shutdown_event.wait()

    async def __aenter__(self) -> Self:
        await self.startup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.shutdown()
