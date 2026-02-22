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
import json
import signal
import time
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from agents.registry import AgentRegistry
from config import EmilySettings, get_settings
from core.bus import AgentBus, Message, PerceptionBus, Priority
from core.fsm import SystemFSM, SystemState
from core.scheduler import Scheduler
from llm.fleet import LLMFleet
from memory.manager import MemoryManager
from observability.logger import configure_logging, get_logger
from observability.metrics import start_metrics_server
from observability.tracing import configure_tracing
from perception.audio.pipeline import AudioPipeline
from perception.vision.pipeline import VisionPipeline
from security.manager import SecurityManager
from self_improvement.engine import SelfImprovementEngine
from voice.output_stream import AudioOutputStream
from voice.tts import TTSManager

log = get_logger(__name__)

_VOICE_ENGINE_AVAILABLE = True
try:
    from conversation.voice_engine import VoiceEngine
except ImportError:
    _VOICE_ENGINE_AVAILABLE = False


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
        self.vision_pipeline: VisionPipeline | None = None
        self.audio_pipeline: AudioPipeline | None = None
        self.tts_manager: TTSManager | None = None
        self.audio_output: AudioOutputStream | None = None
        self.voice_engine_instance: object | None = None
        self.security: SecurityManager = SecurityManager(settings.security)
        self.self_improvement: SelfImprovementEngine = SelfImprovementEngine()
        self.fleet: LLMFleet = LLMFleet(settings.llm, brain_hub=brain_hub)
        self.memory: MemoryManager = MemoryManager(settings, brain_hub=brain_hub)
        self.registry: AgentRegistry | None = None
        self._background_tasks: list[asyncio.Task[None]] = []
        self._shutdown_event = asyncio.Event()

        if brain_hub is not None:
            self.perception_bus.set_brain_hub(brain_hub)
            self.agent_bus.set_brain_hub(brain_hub)

    @classmethod
    def create(
        cls, config_path: str = "config.yaml", brain_hub: Any | None = None,
    ) -> "Bootstrap":
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

        if self.brain_hub is not None:
            async def _on_fsm_change(old: Any, new: Any) -> None:
                await self.brain_hub.emit("fsm", "state_change", {
                    "old": old.name, "new": new.name,
                })
            self.fsm.on_transition(_on_fsm_change)

        # 2. Ensure data directories exist
        for dir_name in [s.data_dir, s.logs_dir, s.knowledge_dir, s.prompts_dir]:
            Path(dir_name).mkdir(parents=True, exist_ok=True)
        Path("prompts/archive").mkdir(parents=True, exist_ok=True)
        Path("plugins/generated").mkdir(parents=True, exist_ok=True)

        # 3. Metrics server
        start_metrics_server(port=s.observability.metrics_port)

        # 4. Security (before any data access)
        await self.security.start()

        # 5. Core buses
        await self.perception_bus.start_publisher()
        await self.perception_bus.start_subscriber()
        await self.agent_bus.start()

        # 6. Scheduler
        await self.scheduler.start()

        # 7. LLM fleet
        await self.fleet.startup()

        # 8. Memory system
        await self.memory.startup()
        await self._wire_retriever()

        # 9. Agent registry
        self.registry = AgentRegistry(self.agent_bus, self.fleet, self.memory)
        await self.registry.start_all()
        self.add_background_task(self.agent_bus.run())

        # 10. Vision pipeline (non-critical — degrade gracefully)
        try:
            self.vision_pipeline = VisionPipeline(
                config=s.vision,
                bus=self.perception_bus,
                vision_model=s.llm.models.vision,
                ollama_url=s.llm.ollama_base_url,
            )
            await self.vision_pipeline.start()
        except Exception as exc:
            log.warning("vision_pipeline_start_failed", error=str(exc))
            self.vision_pipeline = None

        # 8–10. Voice mode selection
        self._voice_mode_enabled = (
            _VOICE_ENGINE_AVAILABLE
            and hasattr(s, "voice_engine")
            and s.voice_engine.enabled
        )

        # TTS is always loaded (used by both new engine and legacy bridge)
        self.tts_manager = TTSManager(s.tts)
        self.audio_output = AudioOutputStream()
        self.add_background_task(self._load_tts())

        if self._voice_mode_enabled:
            log.info("voice_mode_new_engine",
                     msg="Using new full-duplex voice engine — legacy AudioPipeline skipped")
            self.voice_engine_instance = VoiceEngine(
                s,
                self.perception_bus,
                agent_bus=self.agent_bus,
                fleet=self.fleet,
                memory=self.memory,
                brain_hub=self.brain_hub,
            )
            self.add_background_task(self._start_voice_engine())
        else:
            log.info("voice_mode_legacy",
                     msg="Using legacy half-duplex pipeline + bridge")
            self.audio_pipeline = AudioPipeline(settings=s, bus=self.perception_bus)
            self.add_background_task(self._start_audio_pipeline())
            self.add_background_task(self._perception_tts_bridge())

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

        # Stop voice engine
        if self.voice_engine_instance is not None:
            try:
                await self.voice_engine_instance.stop()  # type: ignore[union-attr]
            except Exception as exc:
                log.error("voice_engine_stop_error", error=str(exc))

        # Stop audio pipeline
        if self.audio_pipeline:
            self.audio_pipeline.stop()

        # Stop vision pipeline
        if self.vision_pipeline:
            await self.vision_pipeline.stop()

        # Stop agent registry
        if self.registry is not None:
            await self.registry.stop_all()

        # Stop memory
        await self.memory.shutdown()

        # Stop security services
        await self.security.stop()

        # Stop buses
        await self.scheduler.stop()
        self.agent_bus.stop()
        self.perception_bus.stop()

        log.info("emily_shutdown_complete")

    def _handle_signal(self) -> None:
        """Signal handler: trigger graceful shutdown."""
        log.info("shutdown_signal_received")
        self._shutdown_event.set()

    def add_background_task(self, coro: asyncio.coroutines) -> asyncio.Task[None]:  # type: ignore[type-arg]
        """
        Register and start a long-running background coroutine.

        Args:
            coro: A coroutine to run indefinitely.

        Returns:
            The created asyncio Task.
        """
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self._background_tasks.append(task)
        return task

    async def _wire_retriever(self) -> None:
        """Create HybridRetriever with Qdrant + BM25 + reranker and attach to memory."""
        try:
            from memory.semantic.bm25 import BM25Index
            from memory.semantic.reranker import CrossEncoderReranker
            from memory.semantic.retriever import HybridRetriever
            from memory.semantic.vector_store import QdrantVectorStore

            s = self.settings
            vector_store = QdrantVectorStore(config=s.memory.semantic)
            await vector_store.ensure_collection()

            bm25 = BM25Index(index_path=s.memory.semantic.bm25_index_path)

            reranker = CrossEncoderReranker()
            await reranker.load()

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
            log.info("retriever_wired")
        except Exception as exc:
            log.warning("retriever_unavailable_degraded_mode", error=str(exc))

    async def _start_audio_pipeline(self) -> None:
        """Background task: load audio models and start the capture pipeline."""
        try:
            assert self.audio_pipeline is not None
            log.info("audio_pipeline_loading")
            await self.audio_pipeline.load()
            await self.audio_pipeline.start()
        except Exception as exc:
            log.error("audio_pipeline_start_failed", error=str(exc))

    async def _load_tts(self) -> None:
        """Background task: load TTS engine models."""
        try:
            assert self.tts_manager is not None
            await self.tts_manager.load()
            log.info("tts_engines_loaded")
        except Exception as exc:
            log.error("tts_load_failed", error=str(exc))

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
            )
        except ImportError:
            pass

        try:
            from api.routes.voice_engine import configure_voice_engine_routes
            configure_voice_engine_routes(engine=self.voice_engine_instance)
        except ImportError:
            pass

    async def _start_voice_engine(self) -> None:
        """Background task: start the full-duplex voice engine."""
        try:
            assert self.voice_engine_instance is not None
            log.info("voice_engine_starting")
            await self.voice_engine_instance.start()  # type: ignore[union-attr]
        except Exception as exc:
            log.error("voice_engine_start_failed", error=str(exc)[:200])
            try:
                await self.voice_engine_instance.stop()  # type: ignore[union-attr]
            except Exception:
                pass
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

        await asyncio.sleep(5)

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
                    log.info("wake_word_detected_in_bridge",
                             keyword=event.payload.get("keyword"))
                    await self.fsm.force_transition(SystemState.LISTENING)

            except Exception as exc:
                log.error("perception_bridge_error", error=str(exc))
                try:
                    await self.fsm.force_transition(SystemState.IDLE)
                except Exception:
                    pass

    async def _stream_llm_and_speak(self, user_text: str) -> str:
        """
        Stream LLM tokens, chunk into sentences, synthesize each sentence
        immediately for low perceived latency.

        Falls back to batch mode (full response then speak) on error.

        Args:
            user_text: Transcribed user speech.

        Returns:
            Full response text.
        """
        try:
            return await self._streaming_pipeline(user_text)
        except Exception as exc:
            log.warning("streaming_pipeline_unavailable_batch_fallback", error=str(exc))
            return await self._batch_pipeline(user_text)

    async def _streaming_pipeline(self, user_text: str) -> str:
        """
        Stream LLM output sentence by sentence into TTS.

        Each sentence is synthesized and played as soon as it is complete,
        without waiting for the full LLM response.
        """
        from llm.client import ChatMessage as CM, OllamaClient
        from llm.streaming import StreamProcessor

        client = OllamaClient(base_url=self.settings.llm.ollama_base_url)
        processor = StreamProcessor(tts_chunk_min_chars=40)
        full_response = ""

        try:
            messages = [
                CM(role="system", content=(
                    "You are Emily, a warm and helpful AI assistant. "
                    "Keep responses concise and conversational — you're "
                    "speaking out loud, not writing an essay. "
                    "1-3 sentences is ideal. Do not use markdown or emojis."
                )),
                CM(role="user", content=user_text),
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
        except Exception as exc:
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
            from llm.client import ChatMessage, OllamaClient

            client = OllamaClient(base_url=self.settings.llm.ollama_base_url)
            try:
                result = await client.chat(
                    model=self.settings.llm.models.fast,
                    messages=[
                        ChatMessage(
                            role="system",
                            content=(
                                "You are Emily, a warm and helpful AI assistant. "
                                "Keep responses concise and conversational — you're "
                                "speaking out loud, not writing an essay. "
                                "1-3 sentences is ideal."
                            ),
                        ),
                        ChatMessage(role="user", content=user_text),
                    ],
                )
                return result.content
            finally:
                await client.close()
        except Exception as exc:
            log.error("llm_voice_response_failed", error=str(exc))
            return ""

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
