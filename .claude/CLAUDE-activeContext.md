# Active Context

## Current Branch
`feat/emily-loop-integration` — ~120 uncommitted files. LoopAgent integration + SolidJS web rewrite in progress.

## Recent Work
- **LoopAgent**: Replaced PlannerAgent with LoopAgent for complexity >= 7 tasks. FleetAdapter, ToolBridgeAdapter, MemoryBridge wired up.
- **SolidJS rewrite**: `web-solid/` — migrating React frontend to SolidJS + Vite 7 + Tailwind 4 + Tauri 2. Reasoning panel, brain page, settings page done.
- **Echo cancellation fix**: Changed `config.yaml` input_device from `"auto"` to `"yourfriend Echo-Cancelled Mic"` to prevent Emily hearing herself through speakers.

## Codebase Scan 2026-04-13 (DEEP)
- **Health: C-** | Critical: 4, High: 8, Medium: 10, Low: 8
- **Top finding**: LLMGuard is dead code — security scanning layer exists but is never called in any inference path
- **Kill chain**: web_fetch prompt injection → ReAct → desktop_control → RCE (no approval gates, no LLM scanning)
- **Architecture debt**: perception/ vs persona/perception/ duplication, two 1300-LOC god objects
- **Report**: `.claude/scan-reports/2026-04-13-1630-DEEP.md`

## Priority Actions
1. **Security triage** (week 1): Wire LLMGuard, fix approval gates, fix sandbox bypass
2. **Quick wins**: `ruff check . --fix --select F401,I001`, fix test import paths, async autobiography
3. **Architecture**: Merge perception trees, extract bootstrap phases

## 2026-04-19 — Emily Claude Code Subagents Deployed

4 Emily-aware subagents installed at `~/.claude/agents/emily-{voice,brain,security,dev}.md` per mission #130 ruling.

Spec: `docs/superpowers/specs/2026-04-19-emily-claude-subagents-design.md`
Plan: `docs/superpowers/plans/2026-04-19-emily-claude-subagents.md`

All 4 on Opus, ≤120 lines each (actual: 64/57/54/64). emily-security is read-only (tools: Read, Grep, Glob). Max 2 handoffs enforced via emily-dev. No orchestrator, no debate layer, no emily-knowledge store. All 4 contain the "CLAUDE.md is orientation, not ground truth" rule and the Grep-verify-on-high-coupling-edits rule.

**Session-restart required** to pick up the new agents — Claude Code did not hot-reload during deployment. Once restarted, verify via `Agent(subagent_type="emily-voice", ...)`.

**First resolved open question (from PROBE mission #130):** LLMGuard runtime nullity.
Finding: `self.security.llm_guard` IS non-None at runtime. Call sites at `llm/fleet.py:450` (streaming) and `:689` (non-streaming) DO fire. BUT the `llm-guard` pip package is NOT installed — `pyproject.toml:115-117` explicitly excludes it due to `transformers>=5.x` conflict. `uv pip show llm-guard` returns not-found. Every scan call therefore returns immediate passthrough `is_valid=True` via `security/llm_guard.py:92-95, 107-108, 145-146`.
Severity: HIGH (not CRITICAL — architectural path correct, trade-off intentional and documented).
Fix options:
- A) Install `llm-guard` (requires resolving transformers conflict first)
- B) Expose explicit `security.llm_guard_enabled` config flag so the disabled state is observable, not accidental.
DRIFT_FOUND: CLAUDE.md currently says "LLMGuard is dead code — zero callers exist" — wrong on mechanism (callers exist), right on outcome (no scanning happens).

**30-day predictions to track:**
1. emily-dev invocation ratio to specialists between 0.5 and 2.0 (55% conf)
2. At least one CLAUDE.md drift case caught and flagged by a subagent (71% conf) — ALREADY VALIDATED on day 0: the LLMGuard finding above is a drift case caught in the first real subagent task.
