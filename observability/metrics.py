"""
Prometheus metrics registry for Emily.

All subsystems import specific metric objects from here rather than creating
their own, ensuring consistent naming and label schemas.
"""

from __future__ import annotations

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

from observability.logger import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Latency histograms (seconds)
# ---------------------------------------------------------------------------

STT_LATENCY = Histogram(
    "emily_stt_latency_seconds",
    "End-to-end STT processing latency",
    buckets=(0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0, 2.0),
)

LLM_FIRST_TOKEN_LATENCY = Histogram(
    "emily_llm_first_token_latency_seconds",
    "Time to first token from LLM",
    labelnames=["model_tier"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

TTS_FIRST_AUDIO_LATENCY = Histogram(
    "emily_tts_first_audio_latency_seconds",
    "Time to first audio chunk from TTS",
    labelnames=["engine"],
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1.0),
)

RAG_RETRIEVAL_LATENCY = Histogram(
    "emily_rag_retrieval_latency_seconds",
    "RAG hybrid retrieval latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

AGENT_TASK_LATENCY = Histogram(
    "emily_agent_task_latency_seconds",
    "Agent task execution latency",
    labelnames=["agent_name"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0),
)

TOOL_EXECUTION_LATENCY = Histogram(
    "emily_tool_execution_latency_seconds",
    "Tool execution latency",
    labelnames=["tool_name"],
    buckets=(0.01, 0.1, 0.5, 1.0, 5.0, 30.0),
)

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

CONVERSATIONS_TOTAL = Counter(
    "emily_conversations_total",
    "Total conversation sessions started",
)

LLM_REQUESTS_TOTAL = Counter(
    "emily_llm_requests_total",
    "Total LLM inference requests",
    labelnames=["model_tier", "status"],
)

TOOL_CALLS_TOTAL = Counter(
    "emily_tool_calls_total",
    "Total tool invocations",
    labelnames=["tool_name", "status"],
)

MEMORY_WRITES_TOTAL = Counter(
    "emily_memory_writes_total",
    "Total memory write operations",
    labelnames=["tier"],
)

MEMORY_READS_TOTAL = Counter(
    "emily_memory_reads_total",
    "Total memory retrieval operations",
    labelnames=["tier"],
)

RAG_DOCUMENTS_INGESTED = Counter(
    "emily_rag_documents_ingested_total",
    "Total documents ingested into RAG",
    labelnames=["file_type"],
)

CRITIC_RETRIES_TOTAL = Counter(
    "emily_critic_retries_total",
    "Total CriticAgent retry attempts triggered",
)

WAKE_WORDS_DETECTED = Counter(
    "emily_wake_words_detected_total",
    "Total wake word detection events",
)

STT_ERRORS_TOTAL = Counter(
    "emily_stt_errors_total",
    "Total STT processing errors",
)

# ---------------------------------------------------------------------------
# Gauges (current state)
# ---------------------------------------------------------------------------

ACTIVE_AGENTS = Gauge(
    "emily_active_agents",
    "Number of currently active agents",
)

AGENT_QUEUE_DEPTH = Gauge(
    "emily_agent_queue_depth",
    "Current depth of the agent priority queue",
)

WORKING_MEMORY_TOKENS = Gauge(
    "emily_working_memory_tokens",
    "Current token count in working memory",
)

VRAM_USED_GB = Gauge(
    "emily_vram_used_gb",
    "Current VRAM usage in GB",
)

RAM_USED_GB = Gauge(
    "emily_ram_used_gb",
    "Current RAM usage in GB",
)

EMILY_EMOTIONAL_STATE = Gauge(
    "emily_emotional_state",
    "Emily's current emotional state dimension value",
    labelnames=["dimension"],
)


def start_metrics_server(port: int = 9090) -> None:
    """
    Start the Prometheus HTTP metrics server.

    Args:
        port: TCP port to serve metrics on. Defaults to 9090.
    """
    try:
        start_http_server(port)
        log.info("metrics_server_started", port=port)
    except OSError as exc:
        log.warning("metrics_server_failed", port=port, error=str(exc))
