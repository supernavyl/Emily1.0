# EMILY SYSTEM REPORT — Full Codebase Audit

**Date:** 2026-02-23
**Auditor:** Automated deep scan — every file, every function
**Scope:** 311 Python files, ~64,000 LOC, 55 test files, 1,039 test functions

---

## EXECUTIVE SUMMARY

Emily is a **well-architected, ambitious system** with excellent documentation conventions (type hints, docstrings, structured logging everywhere). The cognitive architecture — agents, memory tiers, LLM fleet, voice pipeline — is thoughtfully designed with proper separation of concerns.

However, the audit reveals **3 exploitable security vulnerabilities**, **5 critical code quality issues**, **massive test coverage gaps (~38% file coverage vs the 100% rule)**, and **~20 blocking I/O violations** in async contexts. The AEC module cannot meet real-time latency requirements. The API layer has authentication bypasses.

### Severity Dashboard

| Severity | Count | Status |
|----------|-------|--------|
| **CRITICAL** | 9 | Must fix before any deployment |
| **HIGH** | 16 | Fix within 1-2 sprints |
| **MEDIUM** | 24 | Plan into roadmap |
| **LOW** | 18+ | Fix opportunistically |

### Key Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Total Python files | 311 | — | — |
| Total LOC | ~64,000 | — | — |
| Test files | 55 | — | — |
| Test functions | 1,039 | — | — |
| File coverage | ~38% | 100% | **FAIL** |
| Files with type hints | ~98% | 100% | PASS |
| Files with docstrings | ~95% | 100% | PASS |
| TODO/FIXME/HACK comments | 0 | 0 | PASS |
| Inline prompt violations | 5 files | 0 | **FAIL** |
| Blocking I/O in async | ~20 instances | 0 | **FAIL** |

---

## CRITICAL FINDINGS (9)

### SECURITY — Exploitable Now

**C-1. Timing-unsafe Bearer token comparison**
- **File:** `api/app.py:180`
- **Issue:** Uses Python `!=` for auth token comparison — vulnerable to timing side-channel attacks. Attacker can infer the secret byte-by-byte.
- **Fix:** Replace with `hmac.compare_digest(auth[7:].strip(), secret)`
- **Time:** 10 minutes

**C-2. WebSocket endpoint has NO authentication**
- **File:** `api/app.py:746`
- **Issue:** `/ws` WebSocket bypasses `BearerAuthMiddleware` entirely. Any client can connect, read system status, audit logs, and interact.
- **Fix:** Add token validation in WebSocket handshake before `accept()`
- **Time:** 30 minutes

**C-3. Unsafe pickle deserialization in BM25 index**
- **File:** `memory/semantic/bm25.py:40-41`
- **Issue:** `pickle.load()` on index file — arbitrary code execution vector if file is tampered with.
- **Fix:** Add HMAC validation before deserialization, or switch to safetensors/JSON
- **Time:** 1-2 hours

### CODE QUALITY — Blocking Bugs

**C-4. Inline system prompt in API layer**
- **File:** `api/app.py:636-640`
- **Issue:** `_EMILY_SYSTEM_PROMPT` is hardcoded — bypasses entire PromptBuilder pipeline. Rule 3 violation.
- **Fix:** Move to `llm/prompt_builder.py`, call `PromptBuilder.build_api_system_prompt()`
- **Time:** 20 minutes

**C-5. Inline system prompt in LLM orchestrator**
- **File:** `llm/orchestrator.py:210-214`
- **Issue:** Hardcoded `"You are Emily. Respond briefly..."` in speculative decoding path.
- **Fix:** Use `PromptBuilder.build_voice_system_prompt()`
- **Time:** 15 minutes

**C-6. Inline prompt strings in vision module**
- **File:** `perception/vision/vision_llm.py:55-58, 72-73, 87-89, 108-110`
- **Issue:** 4 hardcoded prompts in `describe_scene()`, `extract_text()`, `analyze_screen()`, `infer_emotion()`.
- **Fix:** Add vision prompt methods to PromptBuilder
- **Time:** 30 minutes

**C-7. AEC module cannot meet real-time latency**
- **File:** `perception/audio/aec.py:180-198`
- **Issue:** Per-sample Python for-loop (O(N×M), N=480, M=4800) takes 50-500ms per 10ms chunk. Budget is ≤5ms.
- **Fix:** Rewrite with vectorized numpy/scipy LMS or use C extension
- **Time:** 4-6 hours

**C-8. Bootstrap does blocking file I/O in async**
- **File:** `core/bootstrap.py:491-499`
- **Issue:** `_write_transcript()` performs synchronous file writes in async `_perception_tts_bridge`.
- **Fix:** Wrap in `asyncio.to_thread()`
- **Time:** 10 minutes

**C-9. Episodic memory does blocking file I/O in async**
- **File:** `memory/episodic.py:234-237`
- **Issue:** `save_transcript()` is async but calls sync `Path.write_text()`.
- **Fix:** Wrap in `asyncio.to_thread()`
- **Time:** 10 minutes

---

## HIGH FINDINGS (16)

### Security

| # | File | Issue | Fix Time |
|---|------|-------|----------|
| H-1 | `api/app.py:266-271` | CORS wildcard `["*"]` with `allow_credentials=True` | 15 min |
| H-2 | `api/app.py:220` | Rate limiter `_counts` dict grows unbounded per IP — memory leak DoS | 1 hr |
| H-3 | `plugins/sandbox.py:70,85-86` | Bubblewrap tmpfs + bind conflict — sandbox may not work correctly | 1 hr |
| H-4 | `plugins/sandbox.py:134-167` | Python sandbox builtins restriction bypassable via `__class__.__subclasses__()` | 2 hrs |
| H-5 | `plugins/builtin/process_manager.py:49` | Process kill action bypasses approval gate | 30 min |
| H-6 | `perception/audio/speaker_engine.py:132` | `np.load(allow_pickle=True)` — code execution via crafted voice profiles | 30 min |

### Blocking I/O Violations

| # | File | Issue | Fix Time |
|---|------|-------|----------|
| H-7 | `security/audit_log.py:110,154,179` | Sync file I/O in async methods (read_text, open/write) | 30 min |
| H-8 | `plugins/builtin/file_ops.py:47,71-80` | Sync Path operations in async execute() | 30 min |
| H-9 | `security/dead_man_switch.py:62-63` | Sync file writes in heartbeat() called from async | 15 min |
| H-10 | `llm/prompt_builder.py:107-115,654-656` | Sync file I/O in constructor and archive_prompt() | 30 min |

### Missing Tests (Critical Systems)

| # | System | Files Untested | Fix Time |
|---|--------|---------------|----------|
| H-11 | `core/bootstrap.py` (552 lines) | Composition root — 0 tests | 4 hrs |
| H-12 | `agents/conversation.py` (300 lines) | Primary dialogue agent — 0 tests | 3 hrs |
| H-13 | `agents/tool_builder.py` (275 lines) | Code generation agent — 0 tests | 2 hrs |
| H-14 | `core/scheduler.py` (185 lines) | Priority scheduler — 0 tests | 2 hrs |
| H-15 | `core/brain_hub.py` (145 lines) | Event router — 0 tests | 1.5 hrs |

### Code Quality

| # | File | Issue | Fix Time |
|---|------|-------|----------|
| H-16 | `conversation/fsm.py` (1004 lines) | Largest file in codebase — needs extraction | 3 hrs |

---

## MEDIUM FINDINGS (24)

### Blocking I/O (8 instances)

| File | Issue | Fix Time |
|------|-------|----------|
| `voice/voice_clone.py:54` | Sync `Path.iterdir()` in async `prepare()` | 10 min |
| `voice/filler_engine.py:102-118` | Sync `wave.open()` in async `load()` | 10 min |
| `voice/breath_injector.py:95-104` | Sync file I/O in async `load()` | 10 min |
| `conversation/backchannel.py:104-113` | Sync file I/O in async `load_prerecorded()` | 10 min |
| `perception/audio/vad.py:128-132` | PyTorch inference in sync `process()` from async pipeline | 1 hr |
| `perception/audio/noise_suppress.py` | Expensive sync processing blocking event loop | 1 hr |
| `agents/tool_builder.py:237` | Sync `Path.unlink()` in async handler | 5 min |
| `api/app.py:766` | Sync `subprocess.run()` in async WebSocket handler | 15 min |

### Code Quality (10 issues)

| File | Issue | Fix Time |
|------|-------|----------|
| `agents/conversation.py:114-246` | `_generate_response` is 114 lines — split into sub-methods | 1 hr |
| `agents/research.py:81-84` | Recreates `ToolRegistry` on every `_web_search` call | 30 min |
| `agents/monitor.py:107-108` | Silent `except Exception: pass` in `_get_vram_gb` | 5 min |
| `llm/orchestrator.py:268-286` + `llm/speculative.py:114-133` | Duplicated Levenshtein algorithm | 20 min |
| `llm/fleet.py:279-281` | `vision_chat` mutates caller's message list | 5 min |
| `llm/fleet.py:94,322` | Accesses private `_loaded_tiers` on LlamaCppClient | 15 min |
| `memory/procedural.py:104-107` | TOCTOU race in debounce flush — needs `asyncio.Lock` | 15 min |
| `memory/query_engine.py:36` | Module-level `PromptBuilder()` triggers I/O at import | 15 min |
| `memory/working.py:31` | Module-level `tiktoken.get_encoding()` at import time | 15 min |
| `llm/client.py` + `llm/llamacpp_client.py` | O(n²) string concatenation in streaming | 15 min |

### Security (3 issues)

| File | Issue | Fix Time |
|------|-------|----------|
| `agents/tool_builder.py:34-37` | Naive substring matching for dangerous patterns — bypassable | 2 hrs |
| `memory/knowledge_store.py:595` | SQL f-string table name interpolation (safe now, fragile) | 30 min |
| `security/vault/vault.py:361-364` | Column name interpolation in UPDATE SQL | 30 min |

### Config/Infrastructure (3 issues)

| Issue | Detail | Fix Time |
|-------|--------|----------|
| Port mismatch | `config.yaml` says 8000, `start-emily.sh` uses 8080 | 10 min |
| Docker ports on 0.0.0.0 | All services exposed on all interfaces despite LAN-only posture | 20 min |
| Hardcoded secrets | Grafana password + SearXNG secret in version-controlled files | 30 min |

---

## LOW FINDINGS (18+)

| Category | Count | Details |
|----------|-------|---------|
| Unused imports | 12 | `asyncio` in router.py, `asdict` in episodic.py, `Deque` in 6 files, `io`, `json`, `struct`, `Awaitable`, `AsyncIterator` |
| Missing type specificity | 5 | `Any` type hints in agent constructors, `frame: object` in vision |
| Undeclared instance attrs | 3 | `_scheduled_task`, `_monitor_task` set outside `__init__` |
| Inefficient data structures | 2 | `list.pop(0)` instead of `deque.popleft()` in wake_word, streaming_stt |
| Relative paths | 1 | `Path("data/...")` instead of configured `data_dir` |
| Lazy imports in loops | 3 | `import importlib`, `import re`, `import json` inside methods |
| Bare except+pass | 4 | Silent error swallowing in fallback paths |
| Greedy regex | 1 | `structured_output.py` JSON extraction regex |

---

## TEST COVERAGE ANALYSIS

### Untested Subsystems (by priority)

| Priority | Subsystem | Source Files | LOC | Risk |
|----------|-----------|-------------|-----|------|
| **P0** | `perception/audio/` | 13 files | ~3,400 | Core voice pipeline — complete blind spot |
| **P0** | `llm/` (10 of 13 files) | 10 files | ~2,600 | Cognitive core — fleet, router, ReAct, critic untested |
| **P0** | `memory/` (11 of 14 files) | 11 files | ~3,200 | Memory tiers — sensory, working, episodic, procedural untested |
| **P1** | `rag/` | 8 files | ~900 | Knowledge pipeline untested |
| **P1** | `plugins/builtin/` | 13 tools | ~1,800 | All built-in tools untested |
| **P1** | `security/` (5 of 7 files) | 5 files | ~800 | Security modules untested |
| **P2** | `self_improvement/` | 5 files | ~850 | Self-improvement engine untested |
| **P2** | `api/routes/` | 9 files | ~1,600 | API routes untested |
| **P2** | `emily_chat/` (18 files) | 18 files | ~3,000 | Desktop app partially untested |
| **P3** | `perception/vision/` | 5 files | ~650 | Vision pipeline untested |
| **P3** | `ingestion/` | 5 files | ~400 | Ingestion parsers untested |
| **P3** | `observability/` | 4 files | ~300 | Logging/metrics untested |

**Total untested:** ~120 source files, ~19,500 LOC

---

## PERFORMANCE vs LATENCY BUDGETS

| Component | Budget | Status | Issue |
|-----------|--------|--------|-------|
| Wake word | <50ms | **PASS** | Thread-pooled ONNX inference |
| VAD | <1ms/chunk | **RISK** | PyTorch inference in sync process() |
| AEC | ≤5ms/chunk | **FAIL** | Python for-loop takes 50-500ms |
| STT (Faster-Whisper) | <300ms | **PASS** | CUDA float16, thread-pooled |
| LLM first token (nano) | <100ms | **PASS** | llama-cpp-python in-process |
| LLM first token (fast) | <1s | **PASS** | Ollama with keep-alive |
| TTS first audio | <200ms | **PASS** | Per-sentence streaming |
| End-to-end voice | <2s | **RISK** | AEC bottleneck breaks pipeline |

---

## DEPENDENCY AUDIT

| Issue | Detail | Action |
|-------|--------|--------|
| `aiomqtt>=2.0.0` | Not imported anywhere — dead dependency | Remove |
| `uv.lock` not committed | Fresh clones = non-reproducible builds | Commit lockfile |
| No upper version bounds | `>=` only — potential breaking changes | Acceptable with lockfile |
| `spacy` in optional group | But PII scrubbing enabled by default | Document or move to base |
| `emily = "emily.main:cli"` | Script entry point may be broken (module path issue) | Verify and fix |

---

## INFRASTRUCTURE AUDIT

### Docker Compose

| Issue | Severity | Fix Time |
|-------|----------|----------|
| All ports bound to `0.0.0.0` | Medium | 20 min |
| Hardcoded Grafana password | Medium | 15 min |
| Hardcoded SearXNG secret | Medium | 15 min |
| `searxng:latest` tag not pinned | Low | 5 min |
| Jaeger has no persistent volume | Low | 10 min |
| No container resource limits | Low | 15 min |
| No `cap_drop` / `read_only` | Low | 20 min |

### Startup Script

| Issue | Severity | Fix Time |
|-------|----------|----------|
| Port 8080 vs config's 8000 | Medium | 10 min |
| `pkill -f` for process stop | Medium | 30 min |
| No PID file management | Medium | 30 min |

---

## IMPROVEMENT PLAN WITH TIME ESTIMATES

### Phase 1: Security Hardening (1 day)

| Task | Time | Priority |
|------|------|----------|
| Fix timing-unsafe token comparison (C-1) | 10 min | P0 |
| Add WebSocket authentication (C-2) | 30 min | P0 |
| Add HMAC validation to BM25 pickle (C-3) | 1.5 hrs | P0 |
| Fix CORS configuration (H-1) | 15 min | P0 |
| Add rate limiter IP cleanup (H-2) | 1 hr | P0 |
| Fix sandbox tmpfs/bind conflict (H-3) | 1 hr | P1 |
| Fix sandbox builtins bypass (H-4) | 2 hrs | P1 |
| Fix `np.load(allow_pickle=True)` (H-6) | 30 min | P1 |
| Bind Docker ports to 127.0.0.1 (M) | 20 min | P1 |
| Move secrets to .env file (M) | 30 min | P1 |
| **Phase 1 total** | **~8 hours** | |

### Phase 2: Blocking I/O Fixes (0.5 day)

| Task | Time | Priority |
|------|------|----------|
| Wrap bootstrap transcript write (C-8) | 10 min | P0 |
| Wrap episodic save_transcript (C-9) | 10 min | P0 |
| Wrap audit_log methods (H-7) | 30 min | P0 |
| Wrap file_ops execute (H-8) | 30 min | P0 |
| Wrap dead_man_switch heartbeat (H-9) | 15 min | P1 |
| Wrap prompt_builder I/O (H-10) | 30 min | P1 |
| Wrap 6 medium-priority instances | 1 hr | P1 |
| Fix WebSocket sync subprocess call | 15 min | P1 |
| **Phase 2 total** | **~4 hours** | |

### Phase 3: Prompt Consolidation (0.5 day)

| Task | Time | Priority |
|------|------|----------|
| Move API system prompt to PromptBuilder (C-4) | 20 min | P0 |
| Move orchestrator inline prompt (C-5) | 15 min | P0 |
| Move 4 vision prompts to PromptBuilder (C-6) | 30 min | P0 |
| Move inline prompt fragments from planner, research | 20 min | P1 |
| Move emily_chat skill system prompts | 30 min | P2 |
| Move onboarding scripts | 20 min | P2 |
| Move FSM silence prompts | 15 min | P2 |
| **Phase 3 total** | **~3 hours** | |

### Phase 4: Performance Fixes (1 day)

| Task | Time | Priority |
|------|------|----------|
| Rewrite AEC with vectorized numpy/scipy (C-7) | 5 hrs | P0 |
| Fix O(n²) string concatenation in LLM clients | 15 min | P1 |
| Replace `list.pop(0)` with `deque.popleft()` | 15 min | P2 |
| Consolidate duplicated Levenshtein | 20 min | P2 |
| Fix `vision_chat` list mutation | 5 min | P2 |
| Cache ToolRegistry in ResearchAgent | 30 min | P2 |
| Lazy-load tiktoken in working.py | 15 min | P2 |
| **Phase 4 total** | **~7 hours** | |

### Phase 5: Critical Test Coverage (3-5 days)

| System | Files to Test | Time |
|--------|--------------|------|
| `core/bootstrap.py` | 1 file, ~15 tests | 4 hrs |
| `agents/conversation.py` | 1 file, ~12 tests | 3 hrs |
| `agents/tool_builder.py` | 1 file, ~10 tests | 2 hrs |
| `core/scheduler.py` | 1 file, ~8 tests | 2 hrs |
| `core/brain_hub.py` | 1 file, ~6 tests | 1.5 hrs |
| `llm/fleet.py` + `llm/router.py` | 2 files, ~15 tests | 4 hrs |
| `llm/react_loop.py` + `llm/critic_loop.py` | 2 files, ~12 tests | 3 hrs |
| `memory/working.py` + `memory/sensory_buffer.py` | 2 files, ~10 tests | 2 hrs |
| `memory/episodic.py` + `memory/procedural.py` | 2 files, ~12 tests | 3 hrs |
| `rag/ingestor.py` + `rag/chunker.py` | 2 files, ~10 tests | 2.5 hrs |
| `security/` (5 untested files) | 5 files, ~15 tests | 4 hrs |
| `plugins/builtin/` (13 tools) | 13 files, ~30 tests | 6 hrs |
| **Phase 5 total** | **~37 hours** | |

### Phase 6: Code Quality Refactors (2 days)

| Task | Time | Priority |
|------|------|----------|
| Extract response handler from `conversation/fsm.py` | 3 hrs | P1 |
| Split `_generate_response` in conversation agent | 1 hr | P2 |
| Add `asyncio.Lock` to procedural.py flush | 15 min | P2 |
| Expose `loaded_tiers` property on LlamaCppClient | 15 min | P2 |
| Fix lazy imports (move to module level) | 15 min | P3 |
| Remove unused imports | 15 min | P3 |
| Declare `_scheduled_task`/`_monitor_task` in `__init__` | 10 min | P3 |
| Replace `Any` with concrete types in agent constructors | 30 min | P3 |
| Add missing return type hints in API routes | 30 min | P3 |
| Add missing docstrings in API routes | 30 min | P3 |
| **Phase 6 total** | **~7 hours** | |

### Phase 7: Infrastructure & Config (0.5 day)

| Task | Time | Priority |
|------|------|----------|
| Fix API port mismatch (config vs script) | 10 min | P1 |
| Add PID file management to start-emily.sh | 30 min | P2 |
| Add `KnowledgeStoreConfig` and `VaultConfig` to config.yaml | 20 min | P2 |
| Pin SearXNG Docker image version | 5 min | P3 |
| Add Jaeger persistent volume | 10 min | P3 |
| Add container resource limits | 15 min | P3 |
| Remove `aiomqtt` from pyproject.toml | 5 min | P3 |
| Commit `uv.lock` | 5 min | P3 |
| Verify script entry point in pyproject.toml | 15 min | P3 |
| **Phase 7 total** | **~2 hours** | |

---

## TOTAL EFFORT SUMMARY

| Phase | Focus | Time | Priority |
|-------|-------|------|----------|
| Phase 1 | Security hardening | ~8 hrs | **Do first** |
| Phase 2 | Blocking I/O fixes | ~4 hrs | **Do first** |
| Phase 3 | Prompt consolidation | ~3 hrs | **Do first** |
| Phase 4 | Performance fixes | ~7 hrs | Week 1 |
| Phase 5 | Test coverage | ~37 hrs | Week 1-2 |
| Phase 6 | Code quality refactors | ~7 hrs | Week 2 |
| Phase 7 | Infrastructure & config | ~2 hrs | Week 2 |
| **TOTAL** | | **~68 hours** | **~2 weeks** |

---

## WHAT'S WORKING WELL

- **Architecture**: Clean separation across 10+ subsystems with well-defined boundaries
- **Documentation**: 95%+ files have docstrings, nearly universal type hints, zero TODO/FIXME
- **Agent system**: All 9 agents register correctly, proper BaseAgent inheritance, clean message bus
- **Memory design**: 5-tier pentagonal architecture is sophisticated and well-thought-out
- **LLM fleet**: Multi-tier model routing with complexity scoring is production-grade design
- **Structured logging**: `structlog` + Prometheus metrics throughout — excellent observability
- **Graceful degradation**: Optional dependencies handled with try/except + availability flags
- **Voice pipeline design**: Full duplex with turn-taking, backchannel, rhythm sync — ambitious and unique
- **Security design**: Age encryption, PII scrubbing, audit log, consent gate, dead man's switch
- **Config system**: Pydantic Settings v2 with YAML + env vars — modern and type-safe

---

## TOP 10 RECOMMENDATIONS (in priority order)

1. **Fix the 3 exploitable security vulnerabilities** (C-1, C-2, C-3) — 2 hours
2. **Fix all blocking I/O violations** — 4 hours for immediate win
3. **Move all inline prompts to PromptBuilder** — 3 hours, rule compliance
4. **Rewrite AEC module** with vectorized operations — 5 hours, unblocks real-time voice
5. **Write tests for core/bootstrap.py and agents/conversation.py** — 7 hours, highest risk code
6. **Fix CORS, rate limiter, and sandbox issues** — 4 hours, security hygiene
7. **Add test coverage for llm/ and memory/ subsystems** — 12 hours, cognitive core
8. **Refactor conversation/fsm.py** (1004 lines) into smaller modules — 3 hours
9. **Bind Docker ports to 127.0.0.1 and externalize secrets** — 1 hour, deployment safety
10. **Commit uv.lock and fix port mismatch** — 15 minutes, reproducibility
