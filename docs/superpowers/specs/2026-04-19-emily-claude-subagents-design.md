# Emily Claude Code Subagents — Design Spec

**Date:** 2026-04-19
**Source:** Mission 1.8 #130 adversarial debate (NEXUS, FORGE, PHANTOM, PROBE, VERDICT)
**Confidence:** 62% (moderate, 60-74%)
**Status:** Approved by user — ready for implementation plan

---

## Problem

No Emily-specific Claude Code subagents exist today. `~/.claude/agents/` has 26 generic agents (avg 89 lines); zero contain the string "emily". Work on Emily's codebase relies entirely on the general conversation context reading CLAUDE.md — which PROBE empirically confirmed has documentation drift on at least 2 of 3 security claims.

Original request trajectory: user escalated "create agents" → "best on earth" → "more sophisticated" → "most sophisticated" to an adversarial mission debate. The debate pulled the design back toward simpler than the original 13-agent proposal because the sophisticated layer (cross-session knowledge store, internal debate, 13-way specialization) was building on nonexistent infrastructure and drifting documentation.

---

## Architecture — 4 Agents

| Agent | Concern zone | Model | Tools | Max lines |
|-------|--------------|-------|-------|-----------|
| `emily-voice` | Voice pipeline: AEC, VAD, STT, TTS, barge-in, anti-parrot, latency budgets, `conversation/fsm.py` | Opus | Read, Edit, Grep, Glob, Bash | 120 |
| `emily-brain` | LLM fleet, ModelRouter, `prompt_builder.py`, 5-tier memory, agents registry, ReAct loop | Opus | Read, Edit, Grep, Glob, Bash | 120 |
| `emily-security` | Approval gates, sandbox, LLMGuard, vault, PII, per-rule-#9 requires-user-approval | Opus | Read, Grep, Glob only | 120 |
| `emily-dev` | Everything else: API routes, web frontend, config, observability, tests, docker, docs, cross-cutting. Hands off to specialists when depth is needed (max 2 handoffs). | Opus | Full set | 120 |

**Rationale for 4:**
- 13 rejected: adoption probability 3/10 — single developer will not remember which of 13 to invoke; unused agents rot faster than exercised ones.
- 7 rejected: NEXUS's coupling-surface mapping assumed CLAUDE.md accuracy; PROBE confirmed drift on that very documentation.
- 1 rejected: voice-latency reasoning and memory-schema reasoning are categorically different — a single generalist holding both simultaneously will miss voice-latency implications of memory queries.
- 4 is the smallest number that cleanly separates irreducibly-different concern zones and stays below the cognitive-load threshold (~5) where invocation friction kills adoption.

**All agents run Opus** (not heterogeneous). Sonnet is insufficient for Emily's coupling complexity. Heterogeneity adds variance without evidence it adds accuracy on this codebase — overrules FORGE's Opus-only-for-guardian proposal. Revisit if post-deployment shows correlated blind spots.

---

## Agent System Prompt Structure (≤120 lines each)

Every agent file follows this template:

```markdown
---
name: emily-<agent>
description: <one-line trigger description for auto-routing>
tools: <comma-separated allowlist>
model: opus
---

# emily-<agent>

<2-3 sentence charter — what this agent is for and what it refuses>

## Ground-truth rule (appears in all 4)
CLAUDE.md is orientation, not ground truth. Before making any factual
claim about current code, Grep or Glob the live source. If live code
contradicts CLAUDE.md, trust live code and flag the drift in your
response. PROBE confirmed 2026-04-17 that CLAUDE.md had stale claims
on `code_executor.requires_approval` and `desktop_control.requires_approval`.

## Domain knowledge
<Emily-specific facts for this concern zone — see per-agent sections below>

## High-coupling edit rule
If your change touches any of these 6 files, Grep-verify every
assumption about current code state before proposing the change:
- core/bootstrap.py
- conversation/fsm.py
- llm/fleet.py
- llm/prompt_builder.py
- memory/manager.py
- agents/registry.py

## Working principles (all agents)
- Read before write. Load imports + call-sites before editing.
- Minimal diff. No scope creep. No unrelated refactors.
- Tag factual claims: [EMPIRICAL], [STRUCTURAL], [VERIFIED: source], [UNVERIFIED].
- State confidence with calibration band; never decorative.
- Flag blocking I/O in async hot paths.
- Follow existing patterns before inventing new ones.
- Verification before "done" — run the actual code/tests and cite output.

## Deliverable template
CHANGE: <what + why>
ASSUMPTIONS: <explicit list>
UNVERIFIED: <what you could not check>
VERIFICATION: <commands run + output>
ROLLBACK: <exact revert procedure>

## Handoff rule (emily-dev only)
Max 2 handoffs per user task. If more are needed, surface the
decomposition to the user rather than chaining further.

## Memory bank integration
On invocation, read `.claude/CLAUDE-activeContext.md` if present.
On session end (when explicitly asked to persist), update
`.claude/CLAUDE-patterns.md` or `.claude/CLAUDE-troubleshooting.md`
with learnings worth surviving the session.
```

---

## Per-Agent Domain Knowledge

### emily-voice
- Voice pipeline: `MicrophoneStream → SileroVAD → FasterWhisperSTT → EmilyLLMProvider → SentenceCollector → TTS → Speaker`
- AEC lives in `conversation/fsm.py` only; `voice_engine/conversation.py` has NO AEC — do not use it for speaker setups.
- Mic input must be echo-cancelled PipeWire source (`"yourfriend Echo-Cancelled Mic"`), NOT raw hardware mic.
- Latency budgets: STT <300ms, LLM first token <1s (fast tier), TTS first audio <200ms, end-to-end <2s.
- Known footgun: `_get_autobiography()` in `voice_engine/providers/llm/emily_llm.py` does blocking sync I/O (stat/exists/read_text) in the async voice hot path — wrap with `asyncio.to_thread()`.
- Streaming think-tag filter uses state machine (handles `<think>` tags split across chunk boundaries).
- Sample rate 24000 Hz across all TTS providers (Kokoro primary, Orpheus, Qwen3-TTS).

### emily-brain
- `LLMFleet` (`llm/fleet.py`) is THE single entry point for all LLM inference. Never call backend clients directly.
- All prompt strings live in `llm/prompt_builder.py` ONLY (critical rule #1). Inline prompt strings anywhere else = bug. Archive old versions in `prompts/archive/` before self-improvement overwrites.
- Memory access through `MemoryManager` only (critical rule #2). Never touch individual tiers directly.
- Model tiers: nano/voice_fast (9B) + fast (14B) voice-resident on 4090; heavy tiers (27B/30B/32B) swap in and evict voice models. Embedding (qwen3 8B) always on 3060. Do NOT set `CUDA_VISIBLE_DEVICES=0` on Ollama — 27B needs both GPUs.
- Circuit breaker: 3 failures in 5min → 60s cooldown. `extract_thinking()` strips `<think>` tags for voice/chat.
- ReAct++ loop: max 8 iterations, CriticAgent gates. Response cache 24h@T=0, 1h@T>0.
- New agents register in `agents/registry.py`. Inherit `BaseAgent`. Access fleet via `self._fleet`, memory via `self._memory`, bus via `self._bus`.

### emily-security
- **Read-only agent.** Produces change proposals for user review. Does not Edit or Bash. Critical rule #9: security module changes require user approval.
- Known gaps (as of 2026-04-17 — VERIFY BEFORE CITING):
  - `code_executor.requires_approval`: PROBE confirmed `True` (CLAUDE.md scan is stale).
  - `desktop_control.requires_approval`: PROBE confirmed `True` (CLAUDE.md scan is stale).
  - LLMGuard call sites: EXIST in `llm/fleet.py:450` and `:689`, null-guarded — PROBE confirmed. Runtime nullity UNVERIFIED (is `self.security.llm_guard` non-None in prod? is `llm-guard` package installed?).
  - Sandbox bypass: `_wrap_code` template imports `sys` before restricting builtins BUT then deletes `_sys` and clears `os`/`subprocess` from `sys.modules`. Escape harder than CLAUDE.md claims. Module-level imports of `plugins/sandbox.py` itself unverified.
- First task after agent creation: verify LLMGuard runtime nullity and report.
- Vault: AES-256-GCM SQLite at `data/vault.db` with Argon2id. Critical rule #14: credential secrets NEVER in LLM context, TTS output, or query results — metadata only.
- `plugins/generated/` never auto-loaded — requires explicit user approval.

### emily-dev
- Generalist coordinator for everything outside the 3 specialist zones.
- Known hand-off triggers — invoke emily-voice when touching `voice_engine/`, `conversation/`, `perception/audio/`. Invoke emily-brain when touching `llm/`, `memory/`, `agents/`, `extraction/`. Invoke emily-security when touching `security/`, `plugins/sandbox.py`, or any `requires_approval` field.
- FastAPI: `api/app.py` → `:8001`. Routes in `api/routes/`. Bearer auth via `api/auth.py` with `hmac.compare_digest` in middleware. Pydantic v2 everywhere. SSE streaming for chat.
- Web frontend: Tauri 2 + React + Tailwind at `:1420`. Vite proxies `/api/v1` passthrough and `/api` strip-prefix to `:8001`. In-progress SolidJS rewrite at `web-solid/`.
- Observability: structlog `get_logger(__name__)` (NOT `import logging` — 42 files still violate this, fix when you touch them).
- Tests: pytest + pytest-asyncio auto mode, `respx` for HTTP, `time-machine` for time. `FakeLLMResult` for fleet mocks. AAA structure.
- Docker: Emily bare-metal for GPU; Qdrant/SearXNG/Prometheus/Grafana/Jaeger in compose.

---

## What We Rejected and Why

| Proposed | Rejected because | Alternative |
|----------|------------------|-------------|
| 13 agents (voice-engineer + fleet-engineer + memory-architect + agent-author + tool-smith + api-engineer + persona-keeper + ai-scientist + guardian + rule-enforcer + test-strategist + architect + maintainer) | Adoption probability 3/10; bitrot across 13 files; cognitive load past threshold | 4 agents |
| Meta-orchestrator (`emily-architect`) | Premature on 4-agent system; single point of failure; adds latency | Direct invocation; emily-dev handles handoffs |
| Cross-session knowledge store `.claude/emily-knowledge/` | Does not exist today (PROBE confirmed); would be new infrastructure with no proven demand; schema + write-approval over-engineered for 4 agents | Existing `.claude/CLAUDE-*.md` memory bank files |
| Internal debate / adversarial self-review between subagents | Homogeneous weights produce correlated errors (Wang ACL 2024); PROBE empirically caught 3 same-direction errors between NEXUS/FORGE/PHANTOM in this very mission | Grep-verify against live code on high-coupling edits |
| 400-600 line agent files with sophistication blocks | Existing convention is 56-172 lines (avg 89); Claude instruction-following degrades past ~1500 lines combined system+user context | 120 line cap |
| Opus-for-judgment + Sonnet-default heterogeneity | Insufficient evidence heterogeneity helps on this codebase; adds variance | All 4 on Opus |
| Pre-flight health checks (Ollama ping, Qdrant ping, device check) as elaborate subsystem | Over-engineered — most tasks don't need it; adoption killer | Glob-verify file refs + Grep-verify assumptions on high-coupling edits |
| Structured deliverable template with 8 fields (ASSUMPTIONS, BLAST_RADIUS, ROLLBACK, FOLLOWUPS, etc.) | Too rigid for simple tasks | 5-field template (CHANGE / ASSUMPTIONS / UNVERIFIED / VERIFICATION / ROLLBACK) |

---

## File Layout

```
~/.claude/agents/
├── emily-voice.md      (project-scoped would be .claude/agents/ but we're putting global
├── emily-brain.md       so the user can invoke from any Emily-related repo; revisit if
├── emily-security.md    this causes namespace pollution with other projects)
└── emily-dev.md

/home/supernovyl/Emily1.0/.claude/
├── CLAUDE-activeContext.md   (exists)
├── CLAUDE-patterns.md        (exists)
├── CLAUDE-decisions.md       (exists)
└── CLAUDE-troubleshooting.md (exists)
```

Bootstrap also adds a "Claude Code Subagents" section to `/home/supernovyl/Emily1.0/CLAUDE.md` documenting the 4 agents, when to invoke each, and the high-coupling-edit rule.

---

## Bootstrap Order

1. Write `~/.claude/agents/emily-voice.md` (≤120 lines).
2. Write `~/.claude/agents/emily-brain.md` (≤120 lines).
3. Write `~/.claude/agents/emily-security.md` (≤120 lines, read-only tools).
4. Write `~/.claude/agents/emily-dev.md` (≤120 lines).
5. Verify `.claude/CLAUDE-*.md` memory bank files exist in Emily project; create empty stubs for any missing.
6. Add "Claude Code Subagents" section to project `CLAUDE.md` with invocation guide.
7. First real task for emily-security: verify LLMGuard runtime nullity (resolves PROBE UNVERIFIED claim).

---

## Falsifiable Predictions (30-day verification)

1. **55% conf** — emily-dev invocation ratio to specialists (voice+brain+security combined) falls in [0.5, 2.0]. Verify by grepping session logs / `.claude/CLAUDE-activeContext.md` for agent invocations. Refuted if <30% (specialists too narrow, merge some into dev) or >80% (specialists redundant, collapse to 1-2 agents).

2. **71% conf** — at least one CLAUDE.md drift case (live code contradicts documented behavior) is caught and flagged by a subagent within 30 days. Verify via git log of `CLAUDE.md` or `.claude/CLAUDE-troubleshooting.md` for drift-repair entries.

---

## What Would Flip the Ruling

- **→ 3 agents (merge voice+brain)**: if handoff rate between emily-voice and emily-brain >30% in first 10 tasks.
- **→ 7 agents (expand)**: if emily-dev consistently produces lower-quality output than specialists in its zones (post-hoc corrections required on dev outputs exceed specialist outputs).
- **→ Build emily-knowledge/**: if the 4 memory bank files are not updated across 10+ sessions (rot check at day 30).
- **→ Heterogeneous models**: if all-Opus agents show correlated blind spots on security tasks (emily-security misses a real vulnerability a different-weight pass catches).

---

## Open Questions (UNVERIFIED — flag in implementation)

1. LLMGuard runtime nullity: does `self.security.llm_guard` return a usable object in prod, or is the `llm-guard` package uninstalled making `if self._llm_guard is not None:` always fall through?
2. Module-level imports in `plugins/sandbox.py` itself — the `_wrap_code` template was examined but not the module's own import ordering.
3. Whether `.claude/CLAUDE-*.md` memory bank files are actually maintained across sessions, or whether they rot like CLAUDE.md did on the security scan.
4. Whether Claude Code's subagent invocation model supports project-scoped `.claude/agents/` overrides cleanly, or whether global `~/.claude/agents/` is the safer placement (we chose global for now — see File Layout).

---

## Mission 1.8 Audit Trail

Full debate persisted to `missions.db` as mission #130. Chain block #105 (chain INTACT). 5 agent learnings recorded. 5 calibrations recorded. 2 predictions recorded for 30-day resolution.

PROBE verification report resolved 13 factual claims: 7 CONFIRMED, 3 REFUTED, 2 PARTIALLY_CONFIRMED, 1 UNVERIFIABLE. Primary refutations (all from same-model correlated error): "LLMGuard has zero call sites", "code_executor.requires_approval=False", "desktop_control.requires_approval=False". These cannot be used as evidence for any follow-on work.
