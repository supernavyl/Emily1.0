# AI.md — Project Intelligence File (Cursor only)

**For Cursor’s AI only.** Read this first before touching code. Not used by the Emily application at runtime.

This project uses `.cursorrules` (coding standards), `AI.md` (this file), and optionally `.cursor/mcp.json` (MCP servers). Cursor skills: **elite-coder**, **create-rule**, **create-skill**, **update-cursor-settings** when relevant.

---

## PROJECT OVERVIEW

**Project:** Emily  
**What it does:** Self-evolving, multi-agent local AI voice operating system — persistent cognitive entity that learns, plans, reasons, and improves over time on local hardware.  
**Who uses it:** Solo developer / single-user local deployment.  
**Core value prop:** Local-first voice OS with always-on perception (audio, vision, telemetry), multi-agent cognitive core (Conversation, Planner, Memory, Reflection, Research, Code, etc.), pentagonal memory, RAG, and tool/plugin ecosystem.  
**Current phase:** Prototype  
**Last updated:** 2026-02-22

---

## TECH STACK

- **Runtime:** Python 3.12+ (pyproject.toml; uv recommended)
- **Config:** `config.yaml` + env overrides `EMILY__<SECTION>__<KEY>=value`; see `config.py` (Pydantic Settings v2)
- **LLM backends:** Ollama (primary), llama-cpp-python (nano / voice_fast tiers for low latency)
- **Model fleet:** nano (Qwen3-4B), voice_fast (Qwen3-4B), fast (Qwen3-14B), smart/reasoning (QwQ-32B), vision (MiniCPM-V 2.6), embedding (BGE-M3) — see ARCHITECTURE.md and DECISIONS.md
- **Databases:** SQLite (emily_chat: `~/.emily-chat/conversations.db`; knowledge: `data/knowledge.db` via migrations)
- **Memory / RAG:** Qdrant + networkx knowledge graph; memory tiers (sensory buffer, working, episodic, semantic, procedural); RAG in `memory/semantic/`, `rag/`
- **APIs:** FastAPI in `api/` (auth via `EMILY_API_SECRET` or config)
- **Observability:** `observability/` (brain_tap, tracing)
- **No:** Stripe, Railway, Clerk, Redis, Langfuse (unless you add them)

---

## AI/LLM ARCHITECTURE

- **Primary models:** nano/voice_fast → Qwen3-4B (llamacpp when GGUF present); fast → Qwen3-14B; smart/reasoning → QwQ-32B; vision → MiniCPM-V 2.6; embedding → BGE-M3 (all via Ollama or llama-cpp).
- **Prompt location:** All prompts in `llm/prompt_builder.py` only. No inline prompt strings (`.cursorrules` rule 3). Old versions archived in `prompts/archive/` when self-improvement changes them (rule 10).
- **RAG:** Chunking (child 256 / parent 2048 tokens), BM25 + BGE-M3 dense, RRF fusion, reranker, knowledge graph expansion. See `memory/semantic/`, `rag/`.
- **Agents:** ReAct++ loop; agents in `agents/` (Conversation, Planner, Memory, Reflection, Research, Code, etc.); register in `agents/registry.py` (rule 8). Bounded iterations; AgentBus in `core/bus.py`.
- **Cost tracking:** `emily_chat/models/cost_tracker.py`; token/cost per message in chat DB.
- **Latency targets (`.cursorrules` rule 9):** STT < 300ms, LLM first token < 1s (fast model), TTS first audio < 200ms.

---

## DATABASE SCHEMA (KEY AREAS)

**Emily Chat (SQLite, `~/.emily-chat/conversations.db`):** conversations (id, title, model, provider, tokens, cost, etc.); messages (id, conversation_id, role, content, tokens_in/out, cost_usd, etc.); FTS5 for search. See `emily_chat/storage/database.py` and `emily_chat/storage/models.py`.

**Knowledge (SQLite, `data/knowledge.db`):** entities, people, relationships, facts, events. Migration: `scripts/migrations/001_knowledge_schema.py`.

---

## PROJECT STRUCTURE

```
llm/              # LLM client, streaming, ReAct/critic, router, prompt_builder, providers (ollama/llamacpp)
memory/           # Working memory, knowledge store, query engine; memory/semantic/ (retriever, vectors, BM25)
rag/              # Ingestors, parsers (docx, pdf, audio, etc.)
agents/           # Conversation, Planner, Memory, Reflection, Research, Code, etc.; registry.py
plugins/          # Base + builtin (calendar, shell, web_fetch, etc.) + sandbox; generated/ not auto-loaded
api/              # FastAPI app, auth, routes (voice_engine, vault, people, graph)
perception/       # Audio pipeline, STT, VAD, wake word; vision pipeline
voice/            # TTS, singing, prosody, filler engine
core/             # Bus (Perception + Agent), FSM, scheduler, bootstrap
config.py         # Single config entry; config.yaml
emily_chat/       # Desktop chat UI, storage, models, providers (Ollama, LlamaCpp, OpenAI, etc.)
extraction/       # Entity/relation extraction, pipeline
security/         # Audit, vault, PII scrubber, dead man's switch
observability/    # Tracing, brain_tap
tests/unit/       # Unit tests (required per .cursorrules rule 13)
scripts/migrations/  # DB migrations (required for memory schema changes — rule 5)
```

---

## NAMING CONVENTIONS

- Python: `snake_case` for functions/vars, `PascalCase` for classes, `SCREAMING_SNAKE_CASE` for constants.
- DB tables: `snake_case`. IDs: UUID hex or project convention.
- Env: `EMILY__*` for config overrides; `EMILY_API_SECRET`, `EMILY_CONFIG`, `OLLAMA_HOST`, etc.

---

## CRITICAL BUSINESS RULES (.cursorrules)

1. Read **ARCHITECTURE.md**, **COGNITIVE_MODEL.md**, and **DECISIONS.md** before any architectural change.
2. Append a dated entry to **MEMORY_LOG.md** after every significant change.
3. **All prompts** in `llm/prompt_builder.py` only; inline prompt strings are a bug.
4. **Tools:** class in `plugins/`, `dry_run()` method, test in `tests/unit/`, README plugin table entry.
5. **Memory schema changes:** migration script in `scripts/migrations/`.
6. No new dependency without checking if an existing one covers the need.
7. **Security module** (`security/`): explicit user approval before implementation.
8. New agents must register in **agents/registry.py**.
9. **Latency:** STT < 300ms, LLM first token < 1s (fast), TTS first audio < 200ms.
10. Self-improvement prompt changes: archive old version in **prompts/archive/**.
11. System is named **Emily** — never NOVA, assistant, bot, chatbot.
12. **No blocking I/O in async context** — use async or `asyncio.to_thread`.
13. Every function: type hints, docstring, at least one unit test.
14. Large phases (> ~200 lines): split and ask which half first.
15. **plugins/generated/** never auto-loaded — explicit user approval.

---

## ENVIRONMENT VARIABLES

- **EMILY_CONFIG** — Optional; path to config file (default `config.yaml`).
- **EMILY_API_SECRET** — API auth (Bearer); required for protected API.
- **OLLAMA_HOST** — Ollama base URL (default `http://localhost:11434`).
- **EMILY__&lt;SECTION&gt;__&lt;KEY&gt;** — Override any config key (e.g. `EMILY__LLM__OLLAMA_BASE_URL`).
- **Provider API keys** (optional, for cloud fallbacks): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. — see `emily_chat/models/providers/` and `config.py`.

---

## KNOWN GOTCHAS / LANDMINES

1. **Nano GGUF path:** nano/voice_fast use llama-cpp when `llm.llamacpp.enabled` is true and the GGUF file exists under `llm.llamacpp.models_dir` (e.g. `qwen3-4b-instruct-q4_k_m.gguf`). If missing, tier falls back to Ollama.
2. **Tier backends:** `config.py` `TierBackend` defaults: nano/voice_fast → `llamacpp`, others → `ollama`. Don’t assume all tiers use the same backend.
3. **Blocking I/O in async:** Rule 12 — use async or `asyncio.to_thread`; no sync file/network calls in async context.
4. **Security changes:** Any change under `security/` requires explicit user approval (rule 7).
5. **Generated tools:** Code in `plugins/generated/` is never auto-loaded; require explicit user approval (rule 15).

---

## COMMON PATTERNS

- **Config:** `from config import get_config`; `get_config()` returns validated config; override with env `EMILY__*`.
- **Agents:** Implement base in `agents/base.py`, register in `agents/registry.py`; communicate via `core/bus.py` (AgentBus).
- **Plugins:** Subclass in `plugins/`, implement `dry_run()`, add unit test and README table entry.
- **Prompts:** Add or change only in `llm/prompt_builder.py`; reference by constant name in code.

For full patterns and data flow, see **ARCHITECTURE.md**, **COGNITIVE_MODEL.md**, and **DECISIONS.md**.

---

## RECENT DECISIONS

See **DECISIONS.md** and **MEMORY_LOG.md** for dated decisions (LLM backend, model tiers, security audit, migrations, etc.).

---

## DEPLOYMENT / LOCAL DEV

- **Local:** Run main entrypoint (e.g. `main.py` or desktop chat); Ollama and (optionally) llama-cpp GGUF must be available. Chat DB and profiles under `~/.emily-chat/`.
- **API:** FastAPI in `api/app.py`; set `EMILY_API_SECRET` for auth.
- **Migrations:** Run `scripts/migrations/001_knowledge_schema.py` for knowledge DB; chat DB migrates on first run via `emily_chat/storage/database.py`.
