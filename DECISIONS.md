# Emily — Technology Decisions

Every technology choice is recorded here with rationale and rejected alternatives.
Updated after each phase that introduces a new dependency.

---

## LLM Backend: Ollama + llama-cpp-python (per-tier)

**Chosen:** Ollama (primary) + llama-cpp-python (latency-critical tiers)  
**Rationale:** Ollama remains the primary backend for its model management, hot-swapping, and multi-model fleet capabilities. llama-cpp-python is added as a secondary in-process backend for latency-critical tiers (nano, voice_fast) where eliminating HTTP/JSON serialization overhead reduces first-token latency from ~80-100ms to ~20-30ms. Each tier's backend is configurable via `tier_backend` in config.yaml. Nano and voice_fast default to llamacpp (when llamacpp is enabled and the GGUF is present); all other tiers default to Ollama. If the GGUF is missing or llamacpp is disabled, nano and voice_fast fall back to Ollama.  
**Rejected:**
- `llama.cpp` directly — lower-level, more integration work, no multi-model management
- `vLLM` — production-grade but heavier, designed for server deployments with multiple users
- `LM Studio` — GUI-first, no programmatic API
- Ollama-only — viable but leaves ~60-70ms of avoidable HTTP overhead on the table for the voice pipeline's always-resident 3B model

---

## Nano Model: Qwen3-4B

**Chosen:** Qwen3-4B  
**Rationale:** Fits in ~3 GB VRAM (always resident), generational upgrade over Qwen2.5-3B — trained on 36T tokens (vs 18T), 119 language support, hybrid thinking/non-thinking mode, and Alibaba reports performance rivaling Qwen2.5-72B-Instruct. 32K native context. ~78-79% MMLU. Fast inference on RTX 4090. Used for routing, classification, complexity scoring, and voice fast-path.  
**Rejected:**
- Qwen2.5-3B — previous choice, superseded by Qwen3 generation
- Phi-3-mini 3.8B — outclassed by both Qwen2.5-3B and Qwen3-4B
- Qwen3-1.7B — too weak for reliable routing
- Llama 3.2 3B — competitive but no hybrid thinking mode

---

## Fast Model: Qwen3-14B Q4_K_M

**Chosen:** Qwen3-14B quantized to Q4_K_M  
**Rationale:** Trained on 36T tokens, 128K native context (vs Phi-4's 16K), hybrid thinking mode for moderate-complexity tasks, 119 languages, ~78.9% MMLU. ~10 GB VRAM at Q4_K_M co-resides with nano + embedding + STT. Generational improvement over the Qwen2.5 series. Outperforms or matches Phi-4 14B on most benchmarks while offering substantially longer context and thinking mode flexibility.  
**Rejected:**
- Phi-4 14B Q4_K_M — previous choice, strong at math (95.1% GSM8K) but only 16K context, no thinking mode
- Gemma 3 9B — smaller parameter count, less capable at same VRAM
- Mistral 7B — weaker at 7B class
- LLaMA 3.1 8B — solid but outclassed by 14B models

---

## Smart + Reasoning Model: QwQ-32B Q4_K_M

**Chosen:** QwQ-32B quantized to Q4_K_M  
**Rationale:** Dedicated reasoning model with structured chain-of-thought traces. 79.5% AIME'24, 73.1% LiveBench, 66.4% BFCL. Outperforms LLaMA 3.3 70B on math and logical reasoning at half the VRAM. Q4_K_M fits in ~20 GB — within the RTX 4090's 24 GB. Loaded on demand, evicts the fast model. Faster inference than DeepSeek-R1 at comparable quality (~20-24 tok/s on RTX 4090 Q4).  
**Rejected:**
- QwQ-32B Q8_0 — 35 GB, exceeds single RTX 4090 VRAM
- LLaMA 3.3 70B Q4 — larger VRAM requirement (~40 GB), requires GPU offloading which adds latency
- DeepSeek-R1 70B — excellent but same VRAM problem as LLaMA 70B
- DeepSeek-R1-Distill-32B — competitive (93.2% MATH) but slower inference

**Alternative (inactive):** Qwen3-32B Q4_K_M — hybrid thinking/non-thinking mode, performs at 72B-class levels, 128K context, 119 languages. Available as a drop-in replacement by setting `smart: "qwen3:32b"` in config.yaml. Same ~20 GB VRAM. Kept inactive because QwQ's dedicated reasoning chains are better suited for Emily's ReAct++ loop, but Qwen3-32B is the stronger general-purpose option.

---

## Vision Model: MiniCPM-V 2.6

**Chosen:** MiniCPM-V 2.6  
**Rationale:** Strong multimodal performance, 8B parameters, fits in 8 GB VRAM, excellent for screenshot understanding and OCR. Ollama-compatible. Outperforms LLaVA-7B on most vision benchmarks.  
**Rejected:**
- LLaVA 1.6 (34B) — too large for co-residency with other models
- Moondream 2 — lighter but weaker on complex scene understanding
- InternVL2 — strong but less Ollama-compatible

---

## Embedding Model: BGE-M3

**Chosen:** BGE-M3 (FlagEmbedding)  
**Rationale:** Best-of-class hybrid embedding — supports dense, sparse (SPLADE), and multi-vector (ColBERT-style) retrieval from a single model. 8k context window handles long documents. Multilingual. Available via Ollama and sentence-transformers.  
**Rejected:**
- nomic-embed-text — fast but single-mode dense only
- mxbai-embed-large — strong dense retrieval, no sparse support
- text-embedding-3-large — cloud API, violates zero-egress policy

---

## Reranker: BGE-reranker-v2-m3

**Chosen:** BAAI/bge-reranker-v2-m3 (CrossEncoder)  
**Rationale:** Pairs with BGE-M3 embeddings for optimal retrieval accuracy — trained on the same data distribution. Significantly outperforms ms-marco-MiniLM on BEIR benchmarks. Compatible with sentence-transformers CrossEncoder interface. Replaces ms-marco-MiniLM-L-6-v2.  
**Rejected:**
- cross-encoder/ms-marco-MiniLM-L-6-v2 — previous choice, weaker retrieval accuracy
- cross-encoder/ms-marco-MiniLM-L-12-v2 — incremental upgrade over L-6, still outclassed by BGE
- jina-reranker-v2 — strong but less synergy with BGE-M3 embeddings
- Cohere rerank — cloud API, violates zero-egress policy

---

## STT: Faster-Whisper large-v3-turbo (CUDA)

**Chosen:** Faster-Whisper large-v3-turbo  
**Rationale:** ~3x faster than large-v3 with only ~1% WER regression, giving ~50ms end-to-end latency on RTX 4090 — well under the 300ms budget. CTranslate2 optimization with CUDA float16 inference. Word-level timestamps enable accurate VAD alignment. Upgraded from large-v3 for the substantial latency improvement at negligible quality cost.  
**Rejected:**
- Whisper large-v3 — previous choice, 3x slower for marginal WER gain
- Whisper.cpp — C++ with Python bindings, harder to integrate, similar quality
- Vosk — much lower WER accuracy, no word timestamps
- NVIDIA Parakeet — highest accuracy but requires NeMo toolkit (~2 GB extra dep)

---

## TTS: CSM (quality) + Kokoro (speed) + XTTS v2 (cloning)

**Chosen:** Sesame CSM-1B + Kokoro + XTTS v2 (config-driven priority)  
**Rationale:**
- CSM (Sesame Conversational Speech Model): 1B-parameter model producing the most natural conversational speech. Runs via HuggingFace `transformers` (fp16, ~4-6 GB VRAM). Best quality option when latency budget allows.
- Kokoro: Sub-50ms latency as speed-first engine. Ideal as primary for real-time voice mode where first-audio latency matters most.
- XTTS v2: Retained for voice cloning use cases and expressive prosody via style vectors. 200ms latency acceptable as fallback.
- Edge TTS: Always-available last resort (cloud, no GPU needed).  
**Rejected:**
- StyleTTS2 — excellent prosody but no voice cloning, complex inference setup
- Piper — fastest (<20ms) but noticeably robotic at high speeds
- Matcha-TTS — strong quality but less mature ecosystem
- ElevenLabs — cloud API, violates zero-egress policy

---

## Wake Word: openWakeWord

**Chosen:** openWakeWord  
**Rationale:** Free, local, Python-native, ONNX inference (CPU/GPU), supports custom wake word training on user's voice samples. Active development. Low false positive rate.  
**Rejected:**
- Picovoice Porcupine — proprietary, requires license key
- Snowboy — abandoned, Python 2 era
- Custom CNN — viable but weeks of training work

---

## VAD: Silero VAD

**Chosen:** Silero VAD v5  
**Rationale:** ~1 MB ONNX model, extremely fast (<1ms per chunk), excellent accuracy, works offline. Provides exact speech segment boundaries. Used with adaptive noise-floor threshold.  
**Rejected:**
- WebRTC VAD — older, less accurate, no Python wheels for all platforms
- pyannote.audio — heavy, designed for speaker diarization, overkill for VAD

---

## Vector Database: Qdrant

**Chosen:** Qdrant  
**Rationale:** Rust-based, extremely fast filtered vector search, supports sparse + dense + multi-vector simultaneously (matches BGE-M3's capabilities). Docker image is 50 MB. Async Python client. Snapshots for backup. Best performance/features ratio among open-source vector DBs.  
**Rejected:**
- Weaviate — heavier JVM startup, more complex configuration
- Milvus — excellent scalability but designed for clusters, overkill for single-machine
- LanceDB — embedded (no separate server), good for development but less production-hardened
- ChromaDB — simple but limited filtering and sparse support

---

## Graph Database: networkx (embedded)

**Chosen:** networkx (in-process Python)  
**Rationale:** Zero infrastructure overhead, full graph algorithm library, serializable to JSON/GraphML, sufficient for entity relationship graphs at individual-user scale (millions of nodes). Upgradeable to Neo4j if scale demands it.  
**Rejected:**
- Neo4j — powerful but requires JVM, Docker service, and Cypher query language. Added as an upgrade path.
- ArangoDB — multi-model but heavier than networkx for local use
- TinkerPop/Gremlin — overkill for the scale

---

## Message Bus: ZeroMQ

**Chosen:** ZeroMQ (pyzmq with asyncio)  
**Rationale:** Battle-tested, language-agnostic, sub-millisecond local IPC, PUSH/PULL and PUB/SUB patterns fit perception and agent use cases perfectly. asyncio support via pyzmq.  
**Rejected:**
- asyncio.Queue — simpler but single-process only, no cross-process agent isolation
- Redis Pub/Sub — requires separate Redis server, overkill for local IPC
- NATS — excellent but heavier operational footprint

---

## Tool Sandboxing: bubblewrap

**Chosen:** bubblewrap (bwrap)  
**Rationale:** Arch Linux has it in core repos, lightweight user-namespace container, filesystem namespacing, no network in sandboxed tools, used by Flatpak. Zero overhead compared to Docker for subprocess execution.  
**Rejected:**
- Docker — too heavy for per-tool-call containers
- firejail — similar but more complex policy language
- seccomp only — weaker isolation (no filesystem namespacing)
- subprocess with restricted PATH — not sufficient for security model

---

## Observability: structlog + Prometheus + OpenTelemetry

**Chosen:** structlog (logging) + prometheus-client (metrics) + OpenTelemetry (tracing)  
**Rationale:** The de-facto Python stack for production observability. structlog enables structured JSON logs with context variables. Prometheus is the standard for local metrics. OTEL traces integrate with Jaeger (Docker service).  
**Rejected:**
- loguru — less structured, no async context vars
- Datadog/New Relic — cloud SaaS, violates zero-egress policy
- statsd — older metrics protocol, Prometheus preferred

---

## Config: Pydantic Settings v2

**Chosen:** Pydantic Settings v2 + YAML  
**Rationale:** Type-safe config with automatic env var override support, nested model validation, helpful error messages. YAML chosen for config.yaml because it's human-readable with comments.  
**Rejected:**
- Dynaconf — more features but heavier, complex layering
- configparser — no type safety, no nesting
- environment variables only — unmanageable at this configuration depth

---

## Web Framework: FastAPI + HTMX

**Chosen:** FastAPI (API) + HTMX + vanilla JS (web UI)  
**Rationale:** FastAPI gives async-native WebSocket and REST support with automatic OpenAPI docs. HTMX enables reactive UI updates without a full SPA framework.  
**Rejected:**
- Flask — synchronous by default, WebSocket support requires additional library
- Django — too heavyweight for this use case
- React/Next.js — heavy build toolchain for a local-only UI

---

## Encryption: age

**Chosen:** age (via `pyage` or `age` CLI)  
**Rationale:** Modern, simple, audited encryption tool. Replaces GPG for new projects. X25519 key exchange, ChaCha20-Poly1305 AEAD.  
**Rejected:**
- GPG — complex key management, legacy algorithms by default
- OpenSSL directly — low-level, easy to misuse
- Fernet (cryptography lib) — symmetric only, no public-key support

---

## Package Manager: uv + hatchling

**Chosen:** uv (package management) + hatchling (build backend)  
**Rationale:** uv is 10-100x faster than pip for dependency resolution and installation. hatchling is a modern, standards-compliant build backend. Both are in active development.  
**Rejected:**
- pip + setuptools — slower, older
- Poetry — slower than uv, less flexible
- conda — heavier, designed for scientific computing environments

---

## Cloud LLM Provider SDK: anthropic (Phase 5)

**Chosen:** `anthropic>=0.40.0` — first-party Python SDK for the Anthropic API  
**Rationale:** Native support for streaming (`client.messages.stream()`), extended thinking (`thinking.budget_tokens`), content block deltas (`thinking_delta` / `text_delta`), and usage tracking. Async client (`AsyncAnthropic`) integrates cleanly with the `AsyncRunner` bridge. Added to the `desktop` optional dependency group.  
**Rejected:**
- httpx directly — would require manually handling SSE, content block parsing, and thinking extraction
- litellm — adds a large transitive dependency tree; Emily needs per-provider control for thinking extraction
- openai SDK with Anthropic-compatible endpoints — not available for all Anthropic-specific features (extended thinking)
