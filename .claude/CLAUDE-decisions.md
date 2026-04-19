# Emily — Architectural Decisions (Session Log)

See also: `~/Emily1.0/DECISIONS.md` for full technology decision records.

## Key Decisions in Effect

### Unified Process Architecture (2026-04-05)
- API + Core merged into single process via `emily_server.py`
- Bootstrap starts first, then uvicorn runs in same asyncio loop
- Single `emily.service` systemd unit

### Emily 7 "AI IS the Computer" (2026-04-06, NOT YET IMPLEMENTED)
- 5-phase plan: prompt rewrite → bus partition → event streaming → config intelligence → system control
- Bus must switch from PUSH/PULL to PUB/SUB before adding event producers
- Configs stored in SQLite, NOT knowledge graph
- Package management and config editing deferred (too dangerous for v1)
- Phase 0 (prompt rewrite) is zero-risk, ships in 1-2 days

### Brain Dashboard Exists (Tauri + React)
- Current implementation: 6-tab BrainPage with NeuralOverview, EmotionalCortex, CognitiveProcesses, MemoryArchitecture, ModelFleet, PersonalityMatrix
- Uses polling (3-10s intervals), not real-time push
- BrainEventHub delivers to Qt/PySide6 signals, NOT to web frontend
- Gap: no WebSocket brain event channel, no interactive graph, no search, no chat integration

### ADR: Real-time Brain Dashboard via WebSocket Bridge (2026-04-06, VERDICT ruling 79%)

**Status:** Accepted

**Context:** The existing brain dashboard polls REST endpoints every 3-10s. BrainEventHub delivers events to Qt/PySide6 signals only. The Tauri/React frontend has no real-time event stream. Users cannot search, interact with, or query Emily's brain state from the web dashboard.

**Decision:** Bridge pattern -- dispatch thread + attach_recorder + new /ws/brain WebSocket endpoint. Extends existing Tauri/React frontend. ~800 LOC, zero new Python deps.

Architecture:
```
BrainEventHub.attach_recorder() -> queue.Queue (thread-safe)
  -> dispatch thread -> asyncio.call_soon_threadsafe
  -> per-client asyncio.Queue(maxsize=500, drop-oldest)
  -> 50ms batched WebSocket push to /ws/brain
```

Execution order (mandatory):
1. Phase 0: Bug fixes -- _recorders race, nvidia-smi blocking, SystemFSM hub wiring, WS token auth
2. Phase 1: Bridge layer (~300 LOC) -- brain_ws_bridge.py, /ws/brain endpoint
3. Phase 2: Frontend (~500 LOC) -- useBrainWS hook, enhanced brain store, EventStream, BrainChat components

Key design decisions:
- Qt GUI and web dashboard coexist via separate delivery paths (attach_signals vs attach_recorder)
- Both SystemFSM and ConversationFSM emit to hub, labeled distinctly
- Per-client Queue with drop-oldest backpressure prevents slow clients from affecting others
- Polling remains as WS fallback in Zustand store
- Token auth required on /ws/brain before websocket.accept()

**Rejected alternatives:**
- Separate service (B): too complex for single-developer project, 6-9 day estimate vs 15+ days
- SSE hybrid (C): unidirectional, cannot support inline brain chat without second channel
- Replacing Qt GUI: unnecessary, attach_recorder coexists by design

**Pre-requisite bugs identified:**
1. _recorders list mutated without lock (core/brain_hub.py:71) -- race condition
2. nvidia-smi subprocess.run blocks asyncio loop (api/app.py:430) -- up to 3s blocking
3. SystemFSM has zero hub emit calls (core/fsm.py) -- invisible to dashboard
4. /ws endpoint has zero auth (api/app.py:934) -- BaseHTTPMiddleware skips WebSocket scope

**Risks:**
- Voice latency degradation: mitigated by dispatch thread isolating delivery from emit path
- Browser event storm: mitigated by 50ms batching (20fps max)
- Memory leak from abandoned WS: mitigated by bounded Queue + heartbeat sweep

**What would change this:** Emily 7 bus partition ships first (build on PUB/SUB), voice latency >10ms p99 (move to separate process), Tauri abandoned (standalone web app)

---

### ADR: Feedback-Driven LLM Routing + Automatic Knowledge Extraction (2026-04-06, VERDICT ruling 81%)

**Status:** Accepted

**Mission:** Design feedback-driven LLM routing and automatic knowledge extraction for Emily.

**Context:** Emily's voice pipeline (primary interaction mode) uses a hardcoded regex complexity gate in `emily_llm.py` that bypasses `ModelRouter` entirely. Emotional state is detected but never feeds into routing. `KnowledgeStore` has a full entity/people/facts/relationships SQLite schema (tested, working) but zero callers from the conversation flow. `_extract_user_facts()` writes to flat procedural JSON, ignoring the structured store. `supersede_fact()` exists only in tests. `CapabilityGapLogger` logs "model_limitation" gaps but nothing closes the loop.

**Decision: Phased hybrid — prerequisites first, then signal wiring, adaptive learning gated on evidence.**

#### Phase 0: Voice Routing Unification (Week 1) -- PREREQUISITE, BLOCKING

Unify the voice path through `ModelRouter`. This is the single highest-leverage change. Without it, no routing improvement affects the primary interaction mode.

Changes to `voice_engine/providers/llm/emily_llm.py`:
- Remove `_COMPLEX_VOICE_RE` and `_is_complex_voice_query()` (lines 49-63)
- Replace the hardcoded tier selection (line 268) with `self._fleet.route(user_text, voice_mode=True, urgency=urgency)`
- Derive urgency from `self._emotional_state` (concern dimension maps to urgency)
- Use `RoutingDecision.tier` instead of the local binary gate

Net effect: ~20 lines changed, 0 new files, 0 new deps. Voice now benefits from all router improvements automatically.

VRAM impact: zero. Latency impact: zero (ModelRouter fast path is <1ms regex, same as current gate).

#### Phase 1: Signal Wiring (Week 2) -- wire existing infrastructure

**1a. Emotional state to urgency** (~5 lines)
- In `agents/conversation.py` `_generate_response()`, derive urgency from `EmotionalStateManager`:
  `urgency = min(1.0, emotions.state.concern * 1.5)` (concern > 0.5 = high urgency)
- Pass urgency to `self._fleet.route()` and `self._fleet.chat_stream()`

**1b. Routing outcome recording** (~15 lines)
- After every `add_assistant_turn()` in both `conversation.py` and `emily_llm.py`, call `self._self_improvement.record_llm_outcome()` (conversation.py already does this at line 432-439; emily_llm.py does NOT -- add it)
- This feeds PerformanceTracker, which already computes per-tier statistics

**1c. Replace `_extract_user_facts` with `ExtractionPipeline`** (~50 lines)
- In `ConversationAgent`, replace `_extract_user_facts()` (lines 587-635) with a call to `ExtractionPipeline.process()`
- ExtractionPipeline already handles: LLM entity extraction, Deduplicator (Jaro-Winkler at 0.85), fact storage to KnowledgeStore
- Rate limit: every 5th text turn (keep existing cadence) + once at session end for voice
- Fire-and-forget via `asyncio.create_task()` (keep existing pattern)
- Use NANO tier for extraction (8B, same model already loaded, no VRAM impact)

**1d. Wire `supersede_fact()` into extraction** (~20 lines)
- In `ExtractionPipeline._store_attributes_as_facts()`, before `add_fact()`:
  query existing facts for same entity_id + fact_type
  if found and different, call `supersede_fact(old_id, new_fact)`
- This activates the contradiction handling that already exists in schema and code

Net Phase 1: ~90 lines changed across 3 files, 0 new files, 0 new deps.

#### Phase 2: Adaptive Routing (Week 3-4) -- GATED on evidence from Phase 1

**Gate condition:** Only proceed if after 2+ weeks of Phase 1 data:
- Performance log shows >100 routing outcomes recorded
- At least 3 tier:task_type buckets have >30 observations each
- Critic score variance across tiers is >0.1 (meaning tier selection actually matters)

If gate is met:
- Implement FORGE's `RoutingFeedbackTracker` with EMA per tier:task_type (~130 LOC)
- `critic_score` as primary signal (text path)
- Post-hoc quality evaluation for voice (sample 10% of voice responses, evaluate async with NANO tier)
- `should_escalate()` returns bool when EMA < 0.5 with min 10 samples
- Wire into ModelRouter as an advisory signal (router can override based on VRAM/latency constraints)

If gate is NOT met: defer indefinitely. The heuristic router is good enough for a single user.

#### Conflict Resolution Record

1. **"Ship phased" (NEXUS) vs "prerequisites first" (PHANTOM)**
   - **Ruling:** PHANTOM wins on the prerequisite. Voice routing unification is blocking. But PHANTOM's scope of prerequisites is too wide -- we don't need to fix ALL dead code before shipping value.
   - Evidence: emily_llm.py line 268 confirms voice bypasses ModelRouter. Any routing improvement without unification is text-only, which is the secondary interaction mode.
   - **Confidence:** 92%

2. **"EMA per tier:task_type" (FORGE) vs "sentiment too noisy" (PHANTOM)**
   - **Ruling:** Both partially right. FORGE's design is sound for text (critic_score is a clean signal). PHANTOM is right that frustration alone is insufficient for voice (critic is skipped in voice mode). Resolution: critic_score for text, sampled post-hoc eval for voice, frustration as penalty multiplier only.
   - Evidence: conversation.py line 386-388 confirms voice skips critic.
   - **Confidence:** 78%

3. **"Knowledge extraction week 3" (NEXUS) vs "supersede_fact dead, will pollute" (PHANTOM)**
   - **Ruling:** NEXUS is right that extraction should ship early because the infrastructure already exists (ExtractionPipeline, Deduplicator, KnowledgeStore all built and tested). PHANTOM is right that supersede_fact must be wired first. Resolution: ship both together in Phase 1, not separated by weeks.
   - Evidence: extraction/pipeline.py + extraction/deduplicator.py are complete, tested code. supersede_fact exists at knowledge_store.py:484.
   - **Confidence:** 85%

4. **"Hook into MemoryManager.add_assistant_turn()" (FORGE) vs "8B will hallucinate entities" (PHANTOM)**
   - **Ruling:** FORGE's hook point is correct (covers both paths). PHANTOM's hallucination concern is valid but overstated for this context. Single-user system, entities can be manually corrected, Deduplicator provides fuzzy merge. Resolution: use existing ExtractionPipeline with NANO tier, rate-limited, fire-and-forget. Monitor entity quality for 2 weeks before deciding if 27B is needed.
   - Evidence: Deduplicator has Jaro-Winkler at 0.85 threshold. Single user means entity universe is small (~50-200 entities).
   - **Confidence:** 75%

#### Files Modified

| File | Change | Phase |
|------|--------|-------|
| `voice_engine/providers/llm/emily_llm.py` | Remove regex gate, use ModelRouter | 0 |
| `agents/conversation.py` | Wire urgency, replace _extract_user_facts | 1 |
| `extraction/pipeline.py` | Add contradiction detection before add_fact | 1 |
| `voice_engine/providers/llm/emily_llm.py` | Add outcome recording to memory write | 1 |
| `llm/routing_feedback.py` (NEW) | EMA tracker, should_escalate() | 2 (gated) |

#### Estimated Impact

- ~110 lines changed in Phase 0+1 (0 new files, 0 new deps)
- ~130 lines new in Phase 2 (1 new file, 0 new deps, gated)
- Voice latency impact: 0ms (ModelRouter fast path = regex, same as current)
- VRAM impact: 0 (extraction uses already-loaded 8B model)
- Storage: ~5KB/day for routing outcomes, ~1KB/day for extracted entities

#### Risks and Mitigations

1. **Voice latency regression from ModelRouter** -- ModelRouter.route() fast path is pure compiled regex, <1ms. Risk is near-zero. Mitigation: benchmark before/after, hard-revert if p95 > 5ms.
2. **Entity quality from 8B extraction** -- 8B may produce inconsistent canonical names for the same person. Mitigation: Deduplicator fuzzy merge, rate-limited extraction (not every turn), manual correction pathway exists via API/TUI.
3. **VRAM contention during concurrent voice + extraction** -- Both use 8B (already loaded). Ollama/llama-cpp queues requests. Mitigation: fire-and-forget extraction, no latency coupling to voice path.

#### Acceptance Criteria

1. Voice routing produces `RoutingDecision` from `ModelRouter` (not hardcoded tier) -- unit test
2. `urgency` parameter in route() calls reflects emotional state -- unit test
3. `data/performance_log.jsonl` contains routing outcomes from BOTH voice and text paths after 10 interactions -- integration test
4. Entities from conversation appear in `data/knowledge.db` (not just `data/procedural.json`) -- integration test
5. Contradictory facts trigger `supersede_fact()` -- unit test

#### What Would Change This Ruling

- ModelRouter.route() turns out slower than expected for voice (>5ms) -- revisit unification
- 8B extraction produces >50% garbage entities in first 2 weeks -- gate extraction behind 27B or defer
- VRAM spikes above 22GB during concurrent voice + extraction -- move extraction to session-end-only
- Emily 7 bus partition ships first -- Phase 2 routing feedback may use PUB/SUB events instead of direct wiring

#### Rejected Alternatives

- **Option A (NEXUS/FORGE full 4-week plan):** Too much new code before proving the foundation works. AdaptiveRouter before data exists is premature optimization. Score: 273/550 weighted.
- **Option C (Minimal wiring, no unification):** Cheapest but doesn't improve voice (the primary path). Wiring frustration to urgency without voice going through ModelRouter is a no-op. Score: 368/550 weighted but misleading -- voice improvement score should be 1/10.
- **PHANTOM's full prerequisite pass:** Correct instinct, but scope too wide. Fixing CapabilityGapLogger's feedback loop and all dead code before shipping value is not warranted for a single-user system.

**Overall Confidence: 81%**
Justification: High confidence on Phase 0 (clear code path, small change). Moderate confidence on Phase 1 (wiring existing code, but extraction quality is uncertain). Low confidence on Phase 2 (speculative, gated on data that may never materialize). The 81% reflects that Phases 0+1 are solid but Phase 2 is a coin flip.

**Dissent acknowledged:** PHANTOM's concern about 8B entity extraction quality is the weakest link. If the 8B consistently produces "John", "John Smith", and "my friend John" as separate entities, the Deduplicator's 0.85 threshold may not catch all cases. This is a known risk accepted for a single-user system where manual correction is feasible.

---

### ADR: Vision/Camera Integration Architecture (2026-04-07, NEXUS design)

**Status:** Proposed

**Context:** Emily has a complete vision capture pipeline (screen + webcam), a VLM wrapper (VisionAnalyzer), on-demand vision tools, and a PerceptionBus with PUB/SUB. However, nothing subscribes to vision events. No visual context reaches the LLM prompts. VisionPipeline publishes to PerceptionBus but zero consumers exist. The description bridge pattern (VLM generates text, inject into text-only LLM conversation) is the only viable approach given VRAM constraints.

**Decision: VisualContextManager as bridge component + VRAM-aware ambient analysis + prompt injection via system prompt.**

See full architecture in `/home/supernovyl/Emily1.0/docs/VISION_ARCHITECTURE.md`

#### Core Design

1. **VisualContextManager** (`perception/vision/context_manager.py`) — standalone module that subscribes to PerceptionBus `vision.*` events, maintains cached visual state as text, and exposes `get_context_block()` for prompt injection.

2. **VRAM-aware gating** — queries Ollama `/api/ps` to determine loaded models. Ambient VLM analysis only runs when VRAM headroom exists (threshold: remaining >= 6GB). On-demand tools always run (user accepts latency).

3. **Prompt injection** — visual context added as system prompt section between system_profile and user_profile. Omitted entirely when vision is disabled or context is stale. Compact format: 50-150 tokens for text chat, 30-50 tokens for voice.

4. **Four-tier vision hierarchy:** ambient metadata (CPU-only presence/idle) -> change-triggered VLM (PerceptionBus events) -> on-demand detailed (vision tools) -> proactive alerts (app switch, user return, error detection).

#### Key Bug Fixes Required

1. `pipeline.py:131` — `self._presence.update(frame=None)` passes None instead of webcam frame; face detection never works
2. `api/routes/vision.py:68` — hardcodes `"minicpm-v:latest"` instead of using config vision model
3. `vision_tools.py:48` — `_get_vision_model()` fallback is `"minicpm-v:latest"`, should be config-driven

#### Files Modified

| File | Change |
|------|--------|
| `perception/vision/context_manager.py` (NEW) | VisualContextManager + VisualContext dataclass |
| `perception/vision/pipeline.py` | Fix frame=None bug, pass img_b64 decoded frame to presence |
| `llm/prompt_builder.py` | Add visual_context param + `_format_visual_context_injection()` |
| `agents/conversation.py` | Wire VisualContextManager, pass visual context to prompts |
| `voice_engine/providers/llm/emily_llm.py` | Wire VisualContextManager, pass visual context to prompts |
| `core/bootstrap.py` | Create VisualContextManager, wire to bus, pass to agents |
| `api/routes/vision.py` | Fix hardcoded model name |
| `plugins/builtin/vision_tools.py` | Fix fallback model name |
| `config.py` | Add ambient_interval_s, vlm_vram_threshold_gb, context_stale_threshold_s |
| `config.yaml` | Add new vision config fields |

#### Estimated Impact

- ~350 LOC new (context_manager.py), ~100 LOC modified across existing files
- VRAM impact: 0 additional (uses existing Ollama VLM, gated by headroom)
- Voice latency impact: 0 (visual context is pre-computed text, not on-path)
- Token cost: 50-150 tokens per system prompt when vision is active

#### Risks

1. VRAM thrashing if Ollama model swap is triggered during voice conversation — mitigated by VRAM gating
2. VLM cold load latency (10-30s) when user explicitly asks "what's on my screen" during heavy model use — mitigated by cache serving + user-facing latency warning
3. Stale visual context may confuse LLM ("you said VS Code is open but I switched to Firefox") — mitigated by staleness indicator in prompt + short TTL (30s)

#### What Would Change This

- SmolVLM2 2.2B proves good enough for ambient: add as second model config, always-on (fits in ~2GB alongside any text model)
- Ollama adds model pinning API: use it instead of querying /api/ps
- Emily moves to TabbyAPI for all tiers: VRAM gating needs different implementation
- RTX 5090 upgrade: dual-model approach becomes trivial, lift all gating

**Confidence: 82%**

---

### ADR-001: Emily Frontend Framework — React to SolidJS (2026-04-08, VERDICT ruling 71%)

**Status:** Accepted

**Context:** Emily's desktop frontend is a Tauri 2 + React 19 + Zustand + Tailwind app with 14,305 LOC across 90 files. It consumes 128 FastAPI endpoints (40 wired) and 2 WebSockets (chat SSE + brain events at 50+/sec). The brain event stream renders 500+ nodes without virtualization. The developer wants to rebuild in a more performant framework.

**Decision:** Build a new SolidJS frontend in `~/Emily1.0/web-solid/`, reusing the existing Tauri Rust shell and framework-free TypeScript layers (API client, types, SSE handler, env/lib). The React app is preserved. A day-5 kill switch gates the effort: if chat + brain dashboard are not functional by day 5, the rewrite is abandoned and React is optimized instead.

**Prerequisites (before any SolidJS code):**
1. Generate typed API client from FastAPI OpenAPI spec via `openapi-typescript` (2-4h)
2. Port 8 framework-free files verbatim (api/client.ts, types.ts, sse.ts, lib/env.ts, cost.ts, time.ts, mode-themes.ts)

**Build order:**
1. Chat page (core value) — 2-3 days
2. Brain Dashboard + EventStream with `<For>` + virtualization — 2 days
3. Settings — 1-2 days
4. Voice, Logs, Vision, Terminal — 3-4 days

**Key technical decisions:**
- Zustand stores → SolidJS `createStore()` + `produce()` (built-in, no library needed)
- react-markdown → unified/remark/rehype directly + 50-line Solid renderer
- react-syntax-highlighter → Shiki (framework-agnostic, better output)
- lucide-react → lucide-solid (same API, official package)
- Enable `eslint-plugin-solid` from day 1 (catches destructuring-kills-reactivity bugs)
- Brain event pushEvents: ring buffer with `produce()` append, NOT array spread

**Estimated timeline:** 13-15 days to parity, 18-21 with buffer (62% confidence on estimate)

**Acceptance criteria:**
1. All 6 pages functional in SolidJS app
2. WebSocket brain events stream with `<For>` (no full-list re-render on push)
3. SSE chat streaming works with abort/stop
4. At least 40 of 128 API endpoints wired (matching current React coverage)
5. Tauri build produces working AppImage
6. EventStream handles 100 events/sec without frame drops
7. React app preserved in git history

**Day-5 kill switch:** If chat + brain dashboard not functional by day 5 → abandon, return to React + @tanstack/react-virtual on EventStream + React.memo on EventRow + ring buffer in pushEvents.

**Rejected alternatives:**
- **(A) Optimize React** — Lower risk, but developer rejected this path. Real-time event stream's architectural mismatch with React's VDOM means ongoing friction. Retained as fallback if kill switch triggers.
- **(C) Incremental hybrid (both apps in Tauri)** — Theoretically superior but dual codebases for solo developer creates maintenance burden. Rejected.

**Consequences:**
- 2-3 week investment before feature parity
- 8 files / 1,410 LOC transfer with zero modification
- Must learn SolidJS destructuring-reactivity model (new failure mode)
- EventStream gets virtualization + signal-driven rendering from day 1
- Ecosystem gaps (markdown, syntax highlighting) require thin custom wrappers
- 88 unwired endpoints remain regardless — that's the real feature gap

**Decision matrix scores (weighted):**
- (A) Keep React + optimize: 223/590
- (B) Big-bang SolidJS rewrite: 212/590
- (C) Incremental hybrid: 225/590
- Ruling overrides matrix: signals are the natural model for real-time dashboards, and developer motivation is a real constraint

**What would change this ruling:**
- Developer has zero SolidJS experience (learning curve doubles timeline)
- Emily needs plugin architecture or third-party component libraries (React ecosystem wins)
- Day-5 gate fails (self-terminating)

**Agents consulted:** NEXUS (82%), FORGE (70%), ORACLE (78%), PHANTOM (74%), VERDICT (71%)

**Dissent:** 3 of 4 agents recommended against rewrite. Overridden because: (1) user's preference is a constraint, (2) signals fit real-time dashboards architecturally, (3) 14K LOC switching cost is bounded for solo dev.

**Confidence: 71%**

---

### ADR: Hardware Utilization — Ollama-only, Single GPU, Benchmark-First (2026-04-16, VERDICT ruling 79%)

**Status:** Accepted

**Context:** Emily runs on AMD Ryzen 7 7800X3D (8C/16T, 96MB 3D V-Cache), 48GB DDR5, RTX 4090 24GB + RTX 3060 LHR 12GB (non-functional — Xid 79, PCIe header corruption). CLAUDE.md incorrectly stated i9-14900K/64GB. All local LLM tiers run through Ollama despite config.py defaults pointing to llamacpp/tabbyapi (both non-functional). The 9B nano model + STT + embedding consume ~14.8GB, leaving insufficient headroom for 14B co-residency. Model swaps to 27B+ tiers take 15-30s via Ollama.

**Decision:** Ollama-only architecture on single 4090. STT remains on CUDA (fastest path). Voice pipeline uses 9B exclusively with 30m keep_alive to prevent swap storms. Heavy models (27B/32B/30B) accessible for text chat only (swap tolerated). CPU STT migration deferred pending benchmarks.

Key changes implemented:
1. CLAUDE.md corrected — hardware specs, backend reality, STT provider
2. `config.py` TierBackend defaults fixed — all local tiers default to `"ollama"`
3. `voice_engine/providers/factory.py` — now passes `device`/`compute_type` from config (unblocks future CPU STT migration)
4. `voice_engine/config.py` — added `stt_device`/`stt_compute_type` fields
5. `llm/fleet.py` — `startup()` now calls `keep_alive("30m")` on the voice model

**Consequences:**
- Voice pipeline is 9B-only (no 14B co-residency without CPU STT migration)
- 27B/32B/30B require 15-30s swap (text chat only, acceptable)
- RTX 3060 is dead weight until physically reseated + BIOS configured
- CPU STT migration is the upgrade path to unlock 9B+14B co-residency (requires OMP_NUM_THREADS isolation)

**Rejected alternatives:**
- **(B) CPU STT migration now** — OMP_NUM_THREADS=1 in systemd unit makes CPU STT 3-4s (unusable). Requires subprocess isolation work. Deferred to post-benchmark. Score: 316/550.
- **(C) Dual-GPU** — 3060 Xid 79, 98.3% VRAM utilization proposed, no perception circuit breaker. Score: 243/550.
- **llama-cpp-python re-enablement** — No GGUF files exist (only Orpheus 3B TTS). Dual VRAM manager OOM risk. Multi-day download + integration work.

**Agents consulted:** NEXUS (82%), FORGE (82%), PHANTOM (88%), VERDICT (79%)

**Key risk:** 27B swap headroom is 1.7GB — OOM if desktop VRAM spikes. Mitigation: VRAM coordinator pre-unloads before swap. Router tuned to keep 27B invocations rare.

**What would change this:** Benchmark shows peak VRAM >23GB (forces CPU STT). CPU STT <400ms at OMP=4 (makes Plan B attractive). 3060 revived (offload embedding + vision). 9B proves inadequate for quality (forces 14B co-residency).

**Confidence: 79%**

---

### ADR: Emily Brain — Standalone Neural Visualization App (2026-04-16, VERDICT ruling 81%)

**Status:** Accepted

**Mission:** Design Emily Brain as a standalone app separate from web-solid, with real-time neural visualization connecting to Emily API at localhost:8001.

#### Decision Matrix

| Criterion | Weight | A: Canvas 2D + d3-force (NEXUS/FORGE) | B: SVG + static layout (VERDICT synthesis) | C: SVG tab in web-solid (PHANTOM) |
|-----------|--------|----------------------------------------|---------------------------------------------|-----------------------------------|
| Time-to-ship | 9 | 5 (force tuning, hit-testing, compositing) | 8 (declarative SVG, trivial layout) | 9 (no new project setup) |
| Maintainability | 8 | 4 (imperative canvas, manual events) | 8 (declarative SVG, SolidJS reactive) | 7 (coupled to main app lifecycle) |
| Visual quality | 8 | 7 (smooth but manual work) | 7 (CSS transitions, SVG filters) | 6 (constrained by BrainPage layout) |
| Performance | 4 | 9 (overkill) | 8 (more than adequate) | 8 (same) |
| Complexity | 7 | 4 (Canvas+DOM compositing, d3 config) | 8 (simple, declarative) | 7 (routing concerns) |
| Risk | 6 | 5 (force layout tuning = time sink) | 7 (well-understood tech) | 3 (violates user requirement) |
| Reversibility | 5 | 6 (can swap renderer) | 7 (can add Canvas overlay later) | 4 (extracting = rewrite) |
| **Weighted total** | | **257** | **357** | **304** |

**Winner: Option B — SVG + static layout, standalone SolidJS app.**

#### Conflict Resolution

1. **Canvas 2D vs SVG**: NEXUS/FORGE recommended Canvas 2D + requestAnimationFrame. PHANTOM countered that Canvas 2D is wrong for 7-15 interactive labeled nodes.
   - **Ruling: SVG.** PHANTOM is correct. Evidence: (a) All existing web-solid charts are SVG-based (Sparkline, RadarChart, BarChart, ProgressRing, DonutChart) -- zero Canvas components exist in the codebase; (b) 7-15 nodes is firmly in SVG territory -- Canvas 2D's performance advantage is irrelevant below ~200 nodes; (c) Canvas 2D requires manual hit-testing, manual text layout, and Canvas+DOM compositing for labels/tooltips -- all of which SVG provides for free; (d) SolidJS fine-grained reactivity maps perfectly to SVG elements (each `<g>` is a reactive component). Canvas 2D is the right tool for particle systems and large-scale rendering. This is neither.
   - **Confidence: 88%**

2. **d3-force vs static layout**: NEXUS/FORGE recommended d3-force (~35-40KB) for graph layout physics. PHANTOM countered that hardcoded topology doesn't need a physics simulation.
   - **Ruling: Static layout. Drop d3-force.** Emily's subsystem topology is compile-time fixed. There are 12 nodes whose identities and relationships are architecturally determined (VAD, STT, FSM, Router, LLM Fleet, Memory, TTS, Speaker, Agents, Tools, Knowledge, Perception). d3-force solves a discovery problem that doesn't exist here. FORGE acknowledged force layout tuning as "hard" -- this is correct, and it's wasted difficulty. A curated circuit-diagram layout in ~30 lines of coordinate definitions gives a better visual result with deterministic positioning and zero dependencies. The "organic movement" aesthetic benefit of force-directed layout does not justify the 35KB dependency + unpredictable tuning time for 12 nodes.
   - **Confidence: 85%**

3. **Standalone vs web-solid tab**: User explicitly requested standalone. PHANTOM suggested embedding in web-solid BrainPage as a new tab.
   - **Ruling: Standalone.** This is a user constraint, not a technical decision. PHANTOM's architectural argument (avoid CORS overhead, share WS connection, skip project scaffolding) is technically sound but overridden by explicit user intent. The standalone approach also has genuine advantages: independent iteration cycle, can serve as a monitoring tool while web-solid is being developed, no coupling to Tauri build process.
   - **Confidence: 95%** (user intent is unambiguous)

4. **Static topology vs dynamic execution paths**: PHANTOM argued that Emily's architecture has multiple execution paths (voice pipeline, text chat, ReAct loop, memory consolidation) that a single static graph misrepresents.
   - **Ruling: Fixed nodes, dynamic edges.** PHANTOM's concern is legitimate but the proposed solution (don't build a graph) is wrong. The nodes ARE fixed -- Emily's subsystems don't spawn and die at runtime. What changes is which EDGES are active. The event stream provides this signal directly: `{cat: "llm", kind: "token"}` means Router->LLM Fleet edge is active. `{cat: "perception", kind: "vad_speech"}` means Perception->VAD is active. A static 15-line lookup table maps event categories to edge activations. Edges light up for ~2s on event, with exponential decay. This correctly represents "which execution path is active right now" without dynamic node creation.
   - **Confidence: 76%** (the event-to-edge mapping may be incomplete for some flows; requires iteration with real data)

5. **Code reuse strategy**: NEXUS said copy types. FORGE estimated 880 LOC reusable.
   - **Ruling: Copy types and the WS primitive. Do not share packages.** The `createBrainWS.ts` primitive (102 LOC) is well-written with exponential backoff, rAF-batched flushing, and proper cleanup. Copy it. The `BrainEvent`, `SystemStatus`, `Agent`, `ModelInfo` interfaces from `stores/brain.ts` are needed. Copy them. The env.ts pattern is reusable but simplified (no Tauri detection -- hardcode `http://127.0.0.1:8001`). Do NOT create a shared package -- the two apps have different lifecycles and different concerns. Type drift is a real risk (PHANTOM's point) but shared packages for a solo dev are overhead that exceeds the drift cost.
   - **Confidence: 82%**

#### Architecture Specification

**Stack:** SolidJS + Vite 7 + Tailwind 4 at `~/Emily1.0/emily-brain/`, port 1422

**Connection:**
- WebSocket: `ws://127.0.0.1:8001/ws/brain` (primary, real-time events)
- REST polling: `http://127.0.0.1:8001/status` at 30s intervals (structural data only)
- Auth: Bearer token via query param on WS, Authorization header on REST

**Neural Graph (centerpiece):**
- 12 fixed nodes: VAD, STT, FSM, Router, LLM Fleet, Memory, TTS, Speaker, Agents, Tools, Knowledge, Perception
- SVG `<g>` groups with SolidJS reactive props per node
- Curated circuit-diagram layout (hand-authored coordinates, not force-directed)
- Node states: idle (dim, 30% opacity), active (bright + CSS pulse animation), error (red glow)
- Edges: SVG `<path>` with animated `stroke-dasharray` for "data flowing" effect
- Edge activation: event fires -> lookup table maps {cat,kind} to source->target pair -> edge lights up for ~2s with exponential opacity decay

**Event-to-node mapping (static lookup):**
```
perception -> Perception, VAD
fsm        -> FSM
llm        -> Router, LLM Fleet
memory     -> Memory
agent      -> Agents
react      -> Router, LLM Fleet, Tools
tool       -> Tools
proactive  -> Agents
log        -> (no node activation)
```

**Backend change required:**
- Add `"http://127.0.0.1:1422"` and `"http://localhost:1422"` to `cors_origins` in `config.py`
- Nothing else. Existing WS bridge (50ms batching, 500 queue, 50 clients, HMAC auth, category filtering, backfill) and REST endpoints are sufficient.

**Phased delivery:**

Phase 1 (MVP, 3-4 days):
1. NeuralMap -- SVG graph with live event pulses and edge animations
2. StatusBar -- FSM state, uptime, CPU/RAM/VRAM gauges
3. EventDock -- Simplified event stream with category filtering
4. WS connection indicator + reconnect status

Phase 2 (+1 week):
5. EmotionalField -- emotion dimension bars with history sparklines
6. FleetMonitor -- model tier cards with health indicators
7. MemoryLayers -- 5-tier memory visualization

Phase 3 (+1-2 weeks):
8. CognitiveLoop -- ReAct iteration visualization
9. Event detail panel (click to expand)
10. Layout persistence (localStorage)

#### Acceptance Criteria (Phase 1 "done")

1. `npm run dev` starts on :1422 without errors
2. WebSocket connects to :8001/ws/brain and receives events (verified by event counter)
3. Neural graph renders 12 nodes in designed positions with labels
4. Events cause visible node pulses (opacity/scale animation)
5. Active edges animate (stroke-dasharray flow) when corresponding events fire
6. FSM state displayed in real-time (derived from WS fsm:transition events)
7. CPU/RAM/VRAM gauges update via REST polling at 30s intervals
8. Event feed shows last 200 events with category filtering (at minimum: toggle per category)
9. Dark theme, monospace readouts, data-lab aesthetic consistent with web-solid
10. Zero external graph dependencies (no d3, no Three.js, no Canvas 2D)
11. Types defined locally (BrainEvent, SystemStatus, Agent, ModelInfo)

#### Files Modified

| File | Change |
|------|--------|
| `config.py` | Add :1422 origins to cors_origins default list |
| `emily-brain/` (NEW directory) | Entire standalone app |

#### Top 3 Risks

1. **SVG animation performance under burst traffic** (probability: 20%) -- During heavy LLM streaming, dozens of events/sec could trigger many simultaneous SVG transitions. Mitigation: debounce node pulses (max one pulse per 200ms per node), use CSS transitions not JS animation loops. Worst case: visual jank during burst, easily fixable post-ship.

2. **Event-to-topology mapping is incomplete** (probability: 35%) -- The static {cat,kind} -> edge mapping might miss important flows or create misleading connections. Mitigation: ship with unmapped-event counter visible in dev mode. The mapping is a single object literal -- changing it is a 2-minute edit. Iterate based on real observation.

3. **Design quality falls short of "Anthropic-level"** (probability: 40%) -- The neural graph needs careful visual design (node shapes, edge curves, spacing, color palette, glow effects). Mitigation: invest design time upfront on the SVG node template BEFORE coding the reactive layer. Reference: Anthropic dashboard, Linear, Vercel monitoring. SVG gives full access to CSS filters, gradients, and blend modes for polish.

#### Rejected Alternatives

- **(A) Canvas 2D + d3-force standalone** (NEXUS/FORGE) -- Canvas 2D is overengineered for 7-15 interactive labeled nodes. d3-force adds 35KB+ for a physics simulation that solves no real problem. Manual hit-testing, text layout, and Canvas+DOM compositing add complexity without benefit. Score: 257/550 weighted.
- **(C) SVG tab in web-solid** (PHANTOM) -- Technically sound but violates explicit user requirement for standalone app. Additionally couples iteration to main app build cycle and makes future extraction a rewrite. Score: 304/550 weighted.

#### What Would Change This Ruling

1. Node count exceeds ~50 (dynamic agent spawning, plugin visualization) -- Canvas 2D or WebGL becomes justified
2. Emily's event schema gains explicit relationship data (`{from_subsystem, to_subsystem}`) -- d3-force and data-driven topology become worth reconsidering
3. User reverses standalone requirement -- PHANTOM's tab approach becomes the obvious choice
4. SVG transitions cause measurable frame drops at 60fps under normal event load -- add Canvas overlay for particle effects

#### Dissent Acknowledged

- NEXUS and FORGE both recommended Canvas 2D. At higher node counts (50+) or with heavy particle effects, they would be correct. For 12 fixed nodes, SVG is the right abstraction.
- PHANTOM's topology concern is legitimate. A static graph IS a simplification. The dynamic-edges mitigation is pragmatic but imperfect -- some execution paths may not map cleanly to the preset edges.
- d3-force would give "organic" movement. This is a real aesthetic trade-off sacrificed for predictability and zero dependencies.

**Agents consulted:** NEXUS (82%), FORGE (82%), PHANTOM (78%), VERDICT (81%)

**Confidence: 81%**
Justification: Strong evidence from codebase (SVG charts exist, Canvas charts don't, node count is firmly in SVG territory, event schema verified, WS bridge verified). Main uncertainties: design quality is subjective (40% risk), event-to-edge mapping completeness requires real-world testing (35% risk). Both are iteratively fixable post-ship.

## ADR 2026-04-19 — Dual-GPU Voice: Qwen3-30B-A3B-abliterated + Orpheus TTS

**Decision:** Voice LLM = Qwen3-30B-A3B-abliterated (MoE Q4_K_M) via Ollama on 4090. Voice TTS = Orpheus-3B-0.1-ft via llama-cpp-python + SNAC on 3060 (CUDA:1). Whisper pinned to CUDA:1 int8. Kokoro remains as fallback.

**Why:** 3060 recovered from Xid 79 (confirmed 2026-04-19). Partitioning LLM off TTS+STT removes SM contention. 30B-A3B MoE gives 30B quality at ~3B active-params cost. Orpheus provides emotional prosody via tags. Initial attempt with Qwen3-TTS (1.7B) blocked by transformers pin conflict.

**Trade-off:** 14B fast tier no longer co-resides on 4090 — swaps in/out on text-chat demand (~2s cold start accepted).

**3060 budget:** embedding 8B (~5GB) + Orpheus Q4 (~3.5GB) + Whisper int8 (~2GB) = ~10.5GB / 12GB.

**Rollback:** EMILY_VOICE_TTS=kokoro + revert config.yaml voice_fast to qwen3.5-abliterated:9b.

**Artifacts:** Spec v2, plan, commits fce67e8 / ebdf1e5 / fcc989d / a10df15.
