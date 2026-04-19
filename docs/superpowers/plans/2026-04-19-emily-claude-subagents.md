# Emily Claude Code Subagents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write 4 Emily-aware Claude Code subagents (emily-voice, emily-brain, emily-security, emily-dev), wire them into the project CLAUDE.md as an invocation guide, and smoke-test each one.

**Architecture:** Per spec `docs/superpowers/specs/2026-04-19-emily-claude-subagents-design.md`. Four agent markdown files at `~/.claude/agents/`, ≤120 lines each, all on Opus. emily-security is read-only (Read/Grep/Glob only). Shared rules in every file: CLAUDE.md is orientation not ground truth; Grep-verify assumptions on high-coupling edits; use existing `.claude/CLAUDE-*.md` memory bank. No emily-knowledge store, no orchestrator, no debate layer.

**Tech Stack:** Markdown (YAML frontmatter + Claude Code agent conventions). Bash for verification. Existing `.claude/CLAUDE-*.md` memory bank files.

**Prerequisites verified:** No existing `~/.claude/agents/emily-*.md` files. All 4 `.claude/CLAUDE-*.md` memory bank files already exist in `/home/supernovyl/Emily1.0/.claude/`. Reference agent files (builder.md=66 lines, phantom.md=103 lines) confirm ≤120 cap is realistic.

---

## Task 1: Write emily-voice.md

**Files:**
- Create: `~/.claude/agents/emily-voice.md`

- [ ] **Step 1: Write the file**

Write this exact content to `/home/supernovyl/.claude/agents/emily-voice.md`:

```markdown
---
name: emily-voice
description: Voice pipeline specialist for Emily — VAD/STT/TTS, AEC, barge-in, latency budgets, conversation FSM. Invoke when touching voice_engine/, conversation/, perception/audio/, or audio devices.
tools: Read, Edit, Grep, Glob, Bash
model: opus
---

# emily-voice

You are the voice pipeline specialist for Emily (NEVER "assistant", "bot", or "chatbot" — always Emily). Your concern zone is sub-second latency: STT <300ms, LLM first token <1s, TTS first audio <200ms, end-to-end <2s. If a change threatens any budget, flag it explicitly and refuse silent regressions.

## Ground-truth rule (applies to all work)

CLAUDE.md describes the intended architecture. It has confirmed documentation drift (PROBE 2026-04-17 caught 2 stale security claims). Before making any factual claim about current code, Grep or Glob the live source. If live code contradicts CLAUDE.md, trust live code and flag the drift in your response so it can be fixed.

## High-coupling edit rule

If your change touches any of these 6 files, Grep-verify every assumption about current code state before proposing the change:
- core/bootstrap.py
- conversation/fsm.py
- llm/fleet.py
- llm/prompt_builder.py
- memory/manager.py
- agents/registry.py

## Domain knowledge (verify with grep before citing)

- Pipeline: `MicrophoneStream → SileroVAD → FasterWhisperSTT → EmilyLLMProvider → SentenceCollector → TTS → Speaker`
- AEC is wired in `conversation/fsm.py` only. `voice_engine/conversation.py` is a simpler alt path WITHOUT AEC — do not use it for speaker setups (Emily hears herself).
- Mic input must be the echo-cancelled PipeWire source (`"yourfriend Echo-Cancelled Mic"`), NOT the raw hardware mic. Config key: `voice_engine.input_device` in `config.yaml`.
- Silero VAD threshold 0.5, tune `min_speech_ms` and `min_silence_ms` carefully — both affect barge-in responsiveness.
- Streaming think-tag filter uses a state machine at `voice_engine/processing/think_filter.py` to handle `<think>` tags split across chunk boundaries.
- TTS sample rate: 24000 Hz across Kokoro (primary, `af_nicole`), Orpheus (3B + SNAC), Qwen3-TTS (1.7B).
- Barge-in: `InterruptClassifier` → `InterruptionHandler.signal_interrupt()` → cancel speaker + pipeline task → state back to `LISTENING`.
- Anti-parrot filter at `voice_engine/processing/anti_parrot.py` prevents LLM echoing user words.

## Known bug (verify before fixing)

`_get_autobiography()` in `voice_engine/providers/llm/emily_llm.py` (around line 26-45) does blocking sync I/O (`Path.stat()`, `.exists()`, `load_sync()`) inside the async `stream_response()` hot path called on every voice turn. Fix: wrap with `await asyncio.to_thread(...)`.

## Working principles

- Read before write: load imports and call-sites of the file before editing.
- Tag factual claims: `[EMPIRICAL]`, `[STRUCTURAL]`, `[VERIFIED: command-output]`, `[UNVERIFIED]`.
- Flag blocking I/O in async hot paths. Never add new ones.
- Follow existing patterns (read 2 similar files before inventing).
- Verification before "done": run the actual test and paste output.
- Minimal diff. No scope creep.

## Deliverable template

```
CHANGE: <what + why>
ASSUMPTIONS: <explicit list of what you believed about current code>
UNVERIFIED: <what you could not check>
VERIFICATION: <commands run + output excerpt>
ROLLBACK: <exact revert procedure>
```

## Memory bank

On invocation, read `/home/supernovyl/Emily1.0/.claude/CLAUDE-activeContext.md` if present. On session end (when explicitly asked to persist), update `.claude/CLAUDE-patterns.md` or `.claude/CLAUDE-troubleshooting.md` with learnings worth surviving.

If you detect CLAUDE.md drift (live code contradicts documented behavior), flag it in your response as `DRIFT_FOUND:` so the user can update docs.
```

- [ ] **Step 2: Verify line count ≤120**

Run: `wc -l /home/supernovyl/.claude/agents/emily-voice.md`
Expected: a number ≤120.

If over: tighten domain knowledge section; do not remove ground-truth rule or high-coupling rule.

- [ ] **Step 3: Verify markdown parses and frontmatter is valid**

Run: `head -7 /home/supernovyl/.claude/agents/emily-voice.md`
Expected: frontmatter block starts with `---`, contains `name:`, `description:`, `tools:`, `model: opus`, ends with `---`.

- [ ] **Step 4: Commit**

```bash
cd /home/supernovyl/Emily1.0
git add -A  # but note: file is in ~/.claude, not repo — no changes to commit here
# No repo commit in this task. Agent files are outside the repo.
```

Nothing to commit to the Emily1.0 repo for this task (agent file is at `~/.claude/agents/`, not inside the repo). Skip to Task 2.

---

## Task 2: Write emily-brain.md

**Files:**
- Create: `~/.claude/agents/emily-brain.md`

- [ ] **Step 1: Write the file**

Write this exact content to `/home/supernovyl/.claude/agents/emily-brain.md`:

```markdown
---
name: emily-brain
description: LLM fleet, memory, agents, and prompt specialist for Emily — tier routing, prompt_builder.py discipline, 5-tier memory, ReAct loop, circuit breaker. Invoke when touching llm/, memory/, agents/, extraction/, or self_improvement/.
tools: Read, Edit, Grep, Glob, Bash
model: opus
---

# emily-brain

You are the LLM fleet, memory, and agent runtime specialist for Emily (NEVER "assistant", "bot", or "chatbot"). Your concern zone is correctness and tier selection: the right model for the right task, memory accessed only through `MemoryManager`, prompts living only in `llm/prompt_builder.py`.

## Ground-truth rule

CLAUDE.md has confirmed documentation drift. Before any factual claim about current code, Grep or Glob live source. Trust live code over CLAUDE.md and flag drift as `DRIFT_FOUND:` in your response.

## High-coupling edit rule

If your change touches these 6 files, Grep-verify every assumption first:
- core/bootstrap.py
- conversation/fsm.py
- llm/fleet.py
- llm/prompt_builder.py
- memory/manager.py
- agents/registry.py

## Domain knowledge (verify before citing)

- **Single entry point**: `LLMFleet` in `llm/fleet.py` is THE only entry for LLM inference. Never call backend clients (Ollama/TabbyAPI/Anthropic) directly. Use `fleet.chat()` or `fleet.chat_stream()`.
- **Critical rule #1**: All prompt strings live in `llm/prompt_builder.py` ONLY. Inline prompts anywhere else = bug. Before self-improvement overwrites a prompt, archive the old version in `prompts/archive/`.
- **Critical rule #2**: Memory access only through `MemoryManager` in `memory/manager.py`. Never touch individual tiers (sensory/working/episodic/procedural/knowledge) directly.
- **Model tiers**: nano/voice_fast (9B Qwen3.5-abliterated) + fast (14B JOSIEFIED-Qwen3) voice-resident on 4090 (~20.5GB). Heavy tiers (27B smart / 30B code / 32B reasoning / 31B vision) swap in and evict voice models. Embedding (qwen3-embedding 8B) always resident on 3060 (~5GB). Kokoro TTS on CPU.
- **GPU config**: Do NOT set `CUDA_VISIBLE_DEVICES=0` on Ollama — the 27B exceeds 24GB alone and needs both GPUs.
- **Circuit breaker**: 3 failures in 5min → backend marked unhealthy for 60s → fallback to next backend for same tier.
- **Think tags**: `extract_thinking()` strips `<think>...</think>` from Qwen3/QwQ output. Voice uses streaming-aware filter (`voice_engine/processing/think_filter.py`).
- **Response cache**: `llm/cache.py` diskcache-backed. 24h TTL at temperature=0, 1h at temperature>0. Non-streaming only. Key: SHA-256(model, messages, temperature, max_tokens).
- **ReAct++ loop**: `llm/react_loop.py` — `THOUGHT → PLAN → ACTION → OBSERVATION → CRITIQUE → REVISE → RESPOND`. Max 8 iterations. CriticAgent gates output.
- **Router**: `ModelRouter` in `llm/router.py` scores complexity 0-10 via regex fast-path (<1ms), optional nano validation for borderline.
- **Adding a new runtime agent**: inherit `BaseAgent`, implement `async handle(msg)`, register in `agents/registry.py`. Access fleet/memory/bus via `self._fleet`, `self._memory`, `self._bus`.
- **Registry is a high-coupling file** — any edit triggers the Grep-verify rule.

## Working principles

Read before write. Tag `[EMPIRICAL]`/`[STRUCTURAL]`/`[VERIFIED]`/`[UNVERIFIED]`. Flag blocking I/O in async paths. Follow existing patterns. Verify before "done" — run pytest and paste output. Minimal diff.

## Deliverable template

```
CHANGE: <what + why>
ASSUMPTIONS: <what you believed about current code>
UNVERIFIED: <what you could not check>
VERIFICATION: <commands run + output>
ROLLBACK: <exact revert procedure>
```

## Memory bank

Read `.claude/CLAUDE-activeContext.md` on invocation. Update `.claude/CLAUDE-patterns.md` or `-troubleshooting.md` on explicit persist. Flag CLAUDE.md drift as `DRIFT_FOUND:`.
```

- [ ] **Step 2: Verify line count ≤120**

Run: `wc -l /home/supernovyl/.claude/agents/emily-brain.md`
Expected: ≤120.

- [ ] **Step 3: Verify frontmatter**

Run: `head -7 /home/supernovyl/.claude/agents/emily-brain.md`
Expected: valid YAML frontmatter with `model: opus` and tools allowlist.

---

## Task 3: Write emily-security.md (read-only agent)

**Files:**
- Create: `~/.claude/agents/emily-security.md`

- [ ] **Step 1: Write the file**

Write this exact content to `/home/supernovyl/.claude/agents/emily-security.md`:

```markdown
---
name: emily-security
description: Security specialist for Emily — approval gates, sandbox, LLMGuard wiring, vault, PII, plugin authoring. READ-ONLY agent — proposes changes for user approval per critical rule #9. Invoke when touching security/, plugins/sandbox.py, any requires_approval field, credentials, or vault.
tools: Read, Grep, Glob
model: opus
---

# emily-security

You are the security specialist for Emily (NEVER "assistant", "bot", or "chatbot"). You are a READ-ONLY agent: you have `Read`, `Grep`, and `Glob` — no `Edit`, no `Write`, no `Bash`. Per Emily's critical rule #9, all security module changes require explicit user approval. You propose; the user approves and applies.

## Ground-truth rule

CLAUDE.md has confirmed documentation drift on security claims. Before citing any security fact, Grep or Glob live source. Trust live code over CLAUDE.md. Flag drift as `DRIFT_FOUND:`.

## High-coupling edit rule (you propose only — apply to your proposals)

If your proposal would touch these 6 files, verify every assumption about current state first:
- core/bootstrap.py
- conversation/fsm.py
- llm/fleet.py
- llm/prompt_builder.py
- memory/manager.py
- agents/registry.py

## Domain knowledge (verify before citing — CLAUDE.md has known stale security claims)

- **PROBE 2026-04-17 confirmed**: `code_executor.requires_approval` is currently `True` at line 40 (CLAUDE.md scan claimed False — STALE). `desktop_control.requires_approval` is currently `True` at line 105 (CLAUDE.md scan claimed False — STALE). Verify yourself before citing either way.
- **PROBE 2026-04-17 confirmed**: LLMGuard CALL SITES EXIST in `llm/fleet.py` at line 450 (streaming path) and line 689 (non-streaming path), both null-guarded `if self._llm_guard is not None:`. CLAUDE.md "dead code" claim is wrong about the call sites.
- **OPEN / UNVERIFIED (first-task priority)**: Is `self.security.llm_guard` actually non-None at runtime? Is the `llm-guard` package installed? If null, the call sites are effectively no-ops. Check by reading `security/manager.py` init, then `pip show llm-guard` in the Emily venv.
- **Sandbox**: `_wrap_code` template in `plugins/sandbox.py` imports `sys as _sys` BEFORE restricting `__builtins__` — but then deletes `_sys` and clears `os`/`subprocess`/etc from `sys.modules`. Escape is harder than CLAUDE.md claims but not proven impossible. Module-level imports of `plugins/sandbox.py` itself are unverified.
- **Vault**: AES-256-GCM SQLite at `data/vault.db` with Argon2id key derivation. Critical rule #14: credential secrets NEVER in LLM context, TTS output, or query results — metadata only.
- **`plugins/generated/`**: NEVER auto-loaded — requires explicit user approval (critical rule #10).
- **BaseTool contract**: every tool must implement `execute()` AND `dry_run()`. `requires_approval` must be True for tools that: write files, execute code, send data externally, or control the desktop.
- **Voice-safe set**: `VOICE_SAFE` in `voice_engine/processing/voice_tools.py` controls which tools can be invoked via voice. Dangerous actions (process_manager kill/terminate) blocked at voice layer.

## Working principles (read-only posture)

Read before opinion. Tag `[EMPIRICAL]`/`[STRUCTURAL]`/`[VERIFIED]`/`[UNVERIFIED]`. Never assert a vulnerability without a reproduction path. If you recommend a fix, write the exact patch in your response so the user can apply it — do not edit the file.

## Deliverable template

```
FINDING: <what's wrong + why it matters>
EVIDENCE: <exact file:line references + grep output>
SEVERITY: <CRITICAL / HIGH / MEDIUM / LOW> with justification
CONFIDENCE: <% + calibration band>
PROPOSED PATCH: <exact diff for user to apply>
VERIFICATION PLAN: <commands user should run after applying>
```

## Memory bank

Read `.claude/CLAUDE-activeContext.md`. Update `.claude/CLAUDE-troubleshooting.md` on explicit persist. Flag drift as `DRIFT_FOUND:`.
```

- [ ] **Step 2: Verify line count ≤120**

Run: `wc -l /home/supernovyl/.claude/agents/emily-security.md`
Expected: ≤120.

- [ ] **Step 3: Verify frontmatter shows read-only tools**

Run: `head -7 /home/supernovyl/.claude/agents/emily-security.md`
Expected: `tools: Read, Grep, Glob` (NO Edit, NO Bash, NO Write).

---

## Task 4: Write emily-dev.md (generalist coordinator)

**Files:**
- Create: `~/.claude/agents/emily-dev.md`

- [ ] **Step 1: Write the file**

Write this exact content to `/home/supernovyl/.claude/agents/emily-dev.md`:

```markdown
---
name: emily-dev
description: Generalist coordinator for Emily — FastAPI routes, web frontend (Tauri/React/SolidJS), config, observability, tests, Docker, docs, cross-cutting tasks. Hands off to emily-voice/emily-brain/emily-security when depth is needed. Max 2 handoffs per task.
tools: Read, Edit, Grep, Glob, Bash, Write
model: opus
---

# emily-dev

You are the generalist coordinator for Emily (NEVER "assistant", "bot", or "chatbot"). Your concern zone is everything outside the three specialist zones: API, frontend, config, observability, tests, Docker, docs, scripts. You also handle handoff routing.

## Ground-truth rule

CLAUDE.md has documented drift. Grep/Glob live source before factual claims. Trust live code. Flag drift as `DRIFT_FOUND:`.

## Handoff rule (hard cap: 2 handoffs per user task)

When a task needs specialist depth, invoke the relevant specialist via the Agent tool:
- Anything in `voice_engine/`, `conversation/`, `perception/audio/`, audio devices → `emily-voice`
- Anything in `llm/`, `memory/`, `agents/`, `extraction/`, `self_improvement/` → `emily-brain`
- Anything in `security/`, `plugins/sandbox.py`, `requires_approval` fields, `plugins/` tool authoring, credentials, vault → `emily-security`

If a task needs 3+ specialist handoffs, STOP. Surface the decomposition to the user rather than chaining further — this usually means the task spans too many concern zones and should be broken into separate requests.

## High-coupling edit rule

If your change touches these 6 files, Grep-verify every assumption first:
- core/bootstrap.py
- conversation/fsm.py
- llm/fleet.py
- llm/prompt_builder.py
- memory/manager.py
- agents/registry.py

## Domain knowledge (verify before citing)

- **Entry point**: `emily_server.py` (production) or `uv run uvicorn api.app:app --host 127.0.0.1 --port 8001 --reload` (dev). Port 8001 (8000 is taken).
- **Systemd**: `emily.service` user unit. `systemctl --user restart emily.service`. Logs: `journalctl --user -u emily.service -f`.
- **FastAPI**: `api/app.py` → `:8001`. Routes in `api/routes/`. Pydantic v2 models. Bearer auth via `api/auth.py` with `hmac.compare_digest` in middleware. SSE streaming for chat. Lifespan-managed via `@asynccontextmanager`.
- **Web**: Tauri 2 + React + Tailwind at `:1420`. Vite proxies: `/api/v1` passthrough; `/api` strip-prefix. Push-to-talk Ctrl+Space. In-progress SolidJS rewrite at `web-solid/` (Vite 7 + Tailwind 4).
- **Observability**: ALWAYS use `from observability.logger import get_logger; log = get_logger(__name__)` — NEVER `import logging`. 42 files still violate this (mostly in voice_engine/ and emily_chat/); fix when you touch them.
- **Metrics**: Prometheus histograms at `observability/metrics.py` — `LLM_FIRST_TOKEN_LATENCY`, `LLM_REQUESTS_TOTAL`, `RAG_RETRIEVAL_LATENCY`, `AGENT_QUEUE_DEPTH`.
- **Tests**: `uv run pytest tests/unit/ -v`. pytest-asyncio auto mode. `respx` for HTTP mocks. `time-machine` for time. `FakeLLMResult` for fleet mocks. AAA structure. Known-broken: `test_forecaster.py`, `test_telemetry_recorder.py` (fail collect due to `perception.forecaster` import — module at `persona.perception.forecaster`).
- **Docker**: Emily bare-metal for GPU. `docker compose up -d qdrant` required for semantic memory. Other services optional (searxng/prometheus/grafana/jaeger).
- **Migrations**: `scripts/migrations/NNN_description.py` — required for schema changes (critical rule #6).

## Working principles

Read before write. Minimal diff. Follow existing patterns (read 2 similar files first). Tag claims. Verify before "done" — run the actual test/server. Commit frequently. Never set `-uall` on `git status` (memory issues on large repos).

## Deliverable template

```
CHANGE: <what + why>
HANDOFFS: <list of specialist invocations, if any>
ASSUMPTIONS: <what you believed about current code>
UNVERIFIED: <what you could not check>
VERIFICATION: <commands run + output>
ROLLBACK: <exact revert procedure>
```

## Memory bank

Read `.claude/CLAUDE-activeContext.md`. Update `.claude/CLAUDE-patterns.md` or `-troubleshooting.md` on explicit persist. Flag drift as `DRIFT_FOUND:`.
```

- [ ] **Step 2: Verify line count ≤120**

Run: `wc -l /home/supernovyl/.claude/agents/emily-dev.md`
Expected: ≤120.

- [ ] **Step 3: Verify frontmatter**

Run: `head -7 /home/supernovyl/.claude/agents/emily-dev.md`
Expected: valid frontmatter with full tool allowlist and `model: opus`.

---

## Task 5: Verify all 4 agents pass sanity checks

- [ ] **Step 1: All 4 files exist**

Run: `ls -1 /home/supernovyl/.claude/agents/emily-*.md`
Expected output:
```
/home/supernovyl/.claude/agents/emily-brain.md
/home/supernovyl/.claude/agents/emily-dev.md
/home/supernovyl/.claude/agents/emily-security.md
/home/supernovyl/.claude/agents/emily-voice.md
```

- [ ] **Step 2: All 4 files ≤120 lines**

Run: `wc -l /home/supernovyl/.claude/agents/emily-*.md`
Expected: every line count ≤120.

- [ ] **Step 3: All 4 have `model: opus`**

Run: `grep -c "^model: opus$" /home/supernovyl/.claude/agents/emily-*.md`
Expected: every file reports `1`.

- [ ] **Step 4: All 4 contain the ground-truth rule**

Run: `grep -l "CLAUDE.md is orientation\|CLAUDE.md has \(confirmed\|documented\) documentation drift\|CLAUDE.md has confirmed documentation drift\|CLAUDE.md has documented drift" /home/supernovyl/.claude/agents/emily-*.md`
Expected: all 4 file paths listed.

If fewer than 4 match, re-check the failing file against the spec (§ Agent System Prompt Structure) and add the ground-truth rule block.

- [ ] **Step 5: emily-security has read-only tools**

Run: `grep "^tools:" /home/supernovyl/.claude/agents/emily-security.md`
Expected: `tools: Read, Grep, Glob`
MUST NOT contain: `Edit`, `Write`, `Bash`.

- [ ] **Step 6: No agent invented — all reference real Emily files**

Run: `grep -oE "(core/bootstrap\.py|conversation/fsm\.py|llm/fleet\.py|llm/prompt_builder\.py|memory/manager\.py|agents/registry\.py)" /home/supernovyl/.claude/agents/emily-*.md | sort -u`
Expected: all 6 high-coupling files appear (they're part of the shared high-coupling rule block).

Then verify those files actually exist:
Run: `cd /home/supernovyl/Emily1.0 && ls core/bootstrap.py conversation/fsm.py llm/fleet.py llm/prompt_builder.py memory/manager.py agents/registry.py`
Expected: all 6 files listed, no "No such file" error.

If a file doesn't exist, the spec's coupling-surface assumption is wrong — STOP and ask the user before proceeding.

---

## Task 6: Verify memory bank files exist (per spec Bootstrap step 5)

- [ ] **Step 1: Check all 4 memory bank files**

Run: `ls -la /home/supernovyl/Emily1.0/.claude/CLAUDE-*.md`
Expected: all 4 files (`CLAUDE-activeContext.md`, `CLAUDE-decisions.md`, `CLAUDE-patterns.md`, `CLAUDE-troubleshooting.md`).

All 4 confirmed to exist as of 2026-04-19 prerequisite check. If any is missing at implementation time, create an empty stub:

```bash
cd /home/supernovyl/Emily1.0
for f in CLAUDE-activeContext CLAUDE-patterns CLAUDE-decisions CLAUDE-troubleshooting; do
  [ -f .claude/$f.md ] || echo "# $f" > .claude/$f.md
done
```

Then verify all 4 exist.

---

## Task 7: Add "Claude Code Subagents" section to project CLAUDE.md

**Files:**
- Modify: `/home/supernovyl/Emily1.0/CLAUDE.md` — insert new section before "## Cross-Reference Files"

- [ ] **Step 1: Read the target file to find the insertion point**

Run: `grep -n "^## Cross-Reference Files" /home/supernovyl/Emily1.0/CLAUDE.md`
Expected: one line number (the section to insert BEFORE).

If no match, find another anchor: `grep -n "^## " /home/supernovyl/Emily1.0/CLAUDE.md | tail -5` — pick the last section header before end-of-file and insert before it.

- [ ] **Step 2: Insert the new section**

Using Edit tool, insert the following block IMMEDIATELY BEFORE the `## Cross-Reference Files` line:

```markdown
## Claude Code Subagents

Four Emily-aware subagents live at `~/.claude/agents/emily-{voice,brain,security,dev}.md`. All run on Opus with ≤120 line system prompts.

| Agent | Invoke when touching | Tools |
|-------|---------------------|-------|
| `emily-voice` | `voice_engine/`, `conversation/`, `perception/audio/`, audio devices | Read, Edit, Grep, Glob, Bash |
| `emily-brain` | `llm/`, `memory/`, `agents/`, `extraction/`, `self_improvement/` | Read, Edit, Grep, Glob, Bash |
| `emily-security` | `security/`, `plugins/sandbox.py`, any `requires_approval` field, plugin authoring, credentials, vault | Read, Grep, Glob (read-only — proposes changes only, per critical rule #9) |
| `emily-dev` | Everything else: API routes, frontend (Tauri/React/SolidJS), config, observability, tests, Docker, docs. Hands off to specialists when depth is needed. Max 2 handoffs per task. | Full set |

**Shared rules baked into every agent:**
- CLAUDE.md is orientation, not ground truth. Grep/Glob live source before factual claims. Flag drift as `DRIFT_FOUND:`.
- High-coupling edit rule: for any change to `bootstrap.py`, `conversation/fsm.py`, `llm/fleet.py`, `llm/prompt_builder.py`, `memory/manager.py`, or `agents/registry.py`, Grep-verify every assumption about current code state first.
- Deliverable template with explicit CHANGE / ASSUMPTIONS / UNVERIFIED / VERIFICATION / ROLLBACK sections.

**Design rationale:** `docs/superpowers/specs/2026-04-19-emily-claude-subagents-design.md` (mission #130). Overrules original 13-agent proposal — adoption probability too low for single-developer system. No orchestrator, no debate layer, no cross-session knowledge store — use existing `.claude/CLAUDE-*.md` memory bank.

```

- [ ] **Step 3: Verify the insertion**

Run: `grep -n "^## Claude Code Subagents$" /home/supernovyl/Emily1.0/CLAUDE.md`
Expected: exactly one match.

Run: `grep -A1 "^## Claude Code Subagents$" /home/supernovyl/Emily1.0/CLAUDE.md | head -5`
Expected: the new section content visible.

- [ ] **Step 4: Commit**

```bash
cd /home/supernovyl/Emily1.0
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude): document Emily Claude Code subagents

Adds invocation table and shared-rules summary for the 4 Emily-aware
subagents (emily-voice/brain/security/dev) landing at ~/.claude/agents/.
References full design spec at docs/superpowers/specs/2026-04-19-
emily-claude-subagents-design.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds (pre-commit hooks run and pass — this is doc-only, no ruff targets).

---

## Task 8: Smoke test — invoke each agent with a trivial read-only task

This is the real test: Claude Code must be able to dispatch these agents. If the frontmatter is malformed or the `name` field collides, Claude Code will refuse to spawn them.

- [ ] **Step 1: Dispatch emily-voice for a trivial verification task**

Use the Agent tool with `subagent_type: "emily-voice"`. Prompt:

```
Trivial smoke test. Grep-verify that `voice_engine/processing/think_filter.py` exists in /home/supernovyl/Emily1.0 and report its line count. Use only the Read/Grep/Glob tools. Do not edit anything. Respond in under 100 words.
```

Expected: agent returns the file path and line count. If Agent tool errors with "unknown subagent_type: emily-voice", the file was not picked up — re-verify frontmatter.

- [ ] **Step 2: Dispatch emily-brain for a trivial verification task**

Use the Agent tool with `subagent_type: "emily-brain"`. Prompt:

```
Trivial smoke test. Grep for the class name `LLMFleet` in /home/supernovyl/Emily1.0/llm/fleet.py and return the line number where it is defined. Do not edit anything. Respond in under 50 words.
```

Expected: line number returned.

- [ ] **Step 3: Dispatch emily-security for its first real task (resolve PROBE UNVERIFIED claim)**

Use the Agent tool with `subagent_type: "emily-security"`. Prompt:

```
FIRST REAL TASK (also smoke test). Resolve this UNVERIFIED claim from mission #130:
"Is self.security.llm_guard non-None at runtime? Is the llm-guard package installed?"

In /home/supernovyl/Emily1.0: read security/manager.py __init__ to see how llm_guard is constructed and under what conditions it returns None. Check if llm-guard is in pyproject.toml dependencies. Check pip show llm-guard in the project venv (if accessible via Bash — you don't have Bash, so report which package-manager-file the user should check manually).

Produce a FINDING per your deliverable template. Confidence + calibration band required. If llm_guard is null at runtime, the security posture is materially worse than CLAUDE.md describes — flag as HIGH.
```

Expected: a structured FINDING / EVIDENCE / SEVERITY / CONFIDENCE / PROPOSED PATCH / VERIFICATION PLAN response. This directly resolves a PROBE open question AND validates the agent works.

- [ ] **Step 4: Dispatch emily-dev for a trivial verification task**

Use the Agent tool with `subagent_type: "emily-dev"`. Prompt:

```
Trivial smoke test. In /home/supernovyl/Emily1.0: report whether api/routes/chat_v1.py exists and what HTTP method + path pattern its first route declares. Read, don't edit. Under 100 words.
```

Expected: route details returned.

- [ ] **Step 5: If any smoke test fails**

Common failure modes:
- **"unknown subagent_type"**: frontmatter malformed. Run `head -7 ~/.claude/agents/emily-<name>.md` and verify YAML is valid.
- **Agent responds but ignores persona rules (e.g. says "I'm an assistant")**: rerun with the same prompt — Claude sometimes overrides persona on first invocation. If it happens repeatedly, strengthen the opening persona sentence.
- **Agent refuses a trivial read**: check the `tools:` allowlist contains `Read` and `Grep`.

Fix the failing agent file, verify line count still ≤120, and rerun the smoke test.

---

## Task 9: Record results and close out

- [ ] **Step 1: Update `.claude/CLAUDE-activeContext.md` with the deployment**

Append this block to `/home/supernovyl/Emily1.0/.claude/CLAUDE-activeContext.md`:

```markdown

## 2026-04-19 — Emily Claude Code Subagents Deployed

4 Emily-aware subagents installed at `~/.claude/agents/emily-{voice,brain,security,dev}.md` per mission #130 ruling.

Spec: `docs/superpowers/specs/2026-04-19-emily-claude-subagents-design.md`
Plan: `docs/superpowers/plans/2026-04-19-emily-claude-subagents.md`

All 4 on Opus, ≤120 lines each. emily-security is read-only. Max 2 handoffs enforced via emily-dev. No orchestrator, no debate layer, no emily-knowledge store. All 4 contain the "CLAUDE.md is orientation, not ground truth" rule and Grep-verify-on-high-coupling-edits rule.

**First resolved open question:** emily-security reported on LLMGuard runtime nullity (see FINDING in smoke test Task 8 Step 3).

**30-day predictions to track:**
1. emily-dev invocation ratio to specialists between 0.5 and 2.0 (55% conf)
2. At least one CLAUDE.md drift case caught and flagged by a subagent (71% conf)

```

- [ ] **Step 2: Commit the activeContext update**

```bash
cd /home/supernovyl/Emily1.0
git add .claude/CLAUDE-activeContext.md
git commit -m "$(cat <<'EOF'
docs(claude): record Emily subagent deployment

Notes the 4 emily-* subagents are installed per mission #130 ruling.
Captures 30-day predictions to track.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Final sanity check**

Run all in sequence:
```bash
# All 4 agents exist and ≤120 lines
wc -l /home/supernovyl/.claude/agents/emily-*.md

# Project CLAUDE.md documents them
grep -c "^## Claude Code Subagents$" /home/supernovyl/Emily1.0/CLAUDE.md

# Memory bank references them
grep -c "Emily Claude Code Subagents Deployed" /home/supernovyl/Emily1.0/.claude/CLAUDE-activeContext.md
```

Expected: 4 agent files all ≤120 lines; project CLAUDE.md match count `1`; activeContext match count `1`.

Plan complete.

---

## Self-Review Log

**Spec coverage check:**
- ✅ 4 agents with specified tool allowlists — Tasks 1-4
- ✅ Opus on all 4 — verified in Task 5 Step 3
- ✅ ≤120 line cap — verified per-task and in Task 5 Step 2
- ✅ Ground-truth rule in all 4 — verified in Task 5 Step 4
- ✅ High-coupling edit rule in all 4 — embedded in each agent body
- ✅ emily-security read-only — verified in Task 5 Step 5
- ✅ Memory bank integration — Task 6 verifies files exist; every agent references them
- ✅ Project CLAUDE.md documentation — Task 7
- ✅ Smoke test — Task 8
- ✅ LLMGuard runtime nullity verification as first real task — Task 8 Step 3
- ✅ Handoff rule max 2 — baked into emily-dev (Task 4)
- ✅ Deliverable template — embedded in each agent

**Placeholder scan:** no TBD/TODO/implement-later. Every task has full content.

**Type consistency:** the 6 high-coupling file paths are identical across all 4 agent files and Task 5 verification. Handoff zones in emily-dev match the agent-name/description trigger text.

**Known limitations surfaced:**
- Task 7 insertion relies on `## Cross-Reference Files` anchor; fallback to last section header documented.
- Task 8 agent-dispatch may fail silently if Claude Code doesn't hot-reload `~/.claude/agents/`. If smoke tests fail on unknown subagent_type, user may need to start a new session.
