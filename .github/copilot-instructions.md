# GitHub Copilot Project Instructions — Emily 1.0

> These instructions are read by GitHub Copilot (in Zed, VS Code, etc.) before every interaction.
> They define Emily's codebase rules, patterns, and constraints.

## Identity

You are working on **Emily** — a self-evolving, multi-agent local AI voice operating system.
Emily is a persistent cognitive entity that learns, plans, reasons, and improves herself over time.
She runs entirely on local hardware (Intel i9-14900K, 64 GB DDR5, NVIDIA RTX 4090 24 GB, Arch Linux).

**Emily is NOT an assistant, NOT a chatbot, NOT a bot.** She is a cognitive AI companion.

## Tech Stack

- **Language**: Python 3.12+ (strict typing, async-first)
- **Package manager**: `uv` + `hatchling` (`pyproject.toml`)
- **Config**: `config.yaml` + Pydantic Settings v2 (`config.py`); env overrides `EMILY__<SECTION>__<KEY>`
- **LLM backends**: TabbyAPI (ExLlamaV2, primary), Ollama (vision + embedding)
- **Models**: nano=Qwen3-4B, fast=Qwen3-14B, smart/reasoning=QwQ-32B, vision=MiniCPM-V 2.6, embedding=BGE-M3
- **Databases**: SQLite (aiosqlite), Qdrant (vector), networkx (knowledge graph)
- **APIs**: FastAPI + WebSocket
- **Message bus**: ZeroMQ (pyzmq async)
- **Observability**: structlog + prometheus-client + OpenTelemetry
- **Desktop UI**: Tauri + React + Tailwind (web/), PySide6 (emily_chat/)
- **Terminal UI**: Textual (ui/terminal/)
- **Voice**: Faster-Whisper (STT), Kokoro/CSM/XTTS (TTS), Silero VAD, openWakeWord

## Critical Rules — ALWAYS Follow

1. **Read first**: Before architectural changes, understand `ARCHITECTURE.md`, `COGNITIVE_MODEL.md`, `DECISIONS.md`.
2. **Memory log**: After every significant change, append a dated entry to `MEMORY_LOG.md` (what, why, affects).
3. **Prompts**: ALL prompt strings live in `llm/prompt_builder.py` ONLY. Inline prompt strings anywhere else = bug.
4. **Tools**: New tool = class in `plugins/`, `dry_run()` method, test in `tests/unit/`, README table entry.
5. **Schema migrations**: Memory/DB schema changes require `scripts/migrations/NNN_description.py`.
6. **Dependencies**: Never add a dependency without checking if an existing one covers the need.
7. **Security**: Changes to `security/` require explicit user approval.
8. **Agent registration**: New agents MUST register in `agents/registry.py`.
9. **Latency budgets**: STT < 300ms, LLM first token < 1s (fast), TTS first audio < 200ms.
10. **Prompt archival**: Self-improvement prompt changes → archive old version in `prompts/archive/`.
11. **Naming**: System is named **Emily**. Never NOVA, assistant, bot, chatbot.
12. **No blocking I/O**: Use `async` or `asyncio.to_thread()`. Zero sync calls in async context.
13. **Code quality**: Every function needs: type hints, docstring, at least one unit test.
14. **Large changes**: Phase > ~200 lines → split and implement in halves.
15. **Generated tools**: `plugins/generated/` never auto-loaded — require explicit user approval.

## Code Style

```python
# YES — async, typed, documented
async def process_query(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Retrieve and rank relevant documents for the given query.

    Args:
        query: Natural-language search query.
        top_k: Maximum results to return.

    Returns:
        Ranked list of document chunks with scores.
    """
    ...

# NO — untyped, undocumented, blocking
def process_query(query, top_k=5):
    result = requests.get(url)  # blocking!
    ...
```

### Naming Conventions

- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- `SCREAMING_SNAKE_CASE` for constants
- DB tables: `snake_case`
- Env vars: `EMILY__*` for config overrides

### Import Order

1. Standard library
2. Third-party packages
3. Local imports (absolute from project root)

## Architecture Patterns

### Agent Pattern

```python
from agents.base import BaseAgent
from core.bus import Message

class MyAgent(BaseAgent):
    name = "MyAgent"
    description = "What this agent does."

    async def handle(self, message: Message) -> None:
        # Process message
        ...
```

Register in `agents/registry.py` after implementation.

### Tool Pattern

```python
from plugins.base import BaseTool, ExecutionContext, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does."

    async def execute(self, params: dict, ctx: ExecutionContext) -> ToolResult:
        ...

    async def dry_run(self, params: dict, ctx: ExecutionContext) -> ToolResult:
        ...
```

### Memory Access

```python
# Always go through MemoryManager — never access tiers directly
await memory.add_user_turn(text, importance=0.6)
await memory.add_assistant_turn(response, importance=0.7, metadata={...})
chunks = await memory.retrieve_context(query, top_k=5)
```

### Config Access

```python
from config import get_settings
settings = get_settings()
# settings.llm.models.fast, settings.memory.episodic.db_path, etc.
```

## Key File Map

| File | Purpose |
|------|---------|
| `config.yaml` + `config.py` | All runtime configuration |
| `llm/prompt_builder.py` | ALL prompts — single source of truth |
| `llm/fleet.py` | Multi-model LLM management |
| `llm/router.py` | Complexity scoring → model tier selection |
| `llm/react_loop.py` | ReAct++ reasoning loop |
| `agents/conversation.py` | Real-time dialogue handler |
| `agents/registry.py` | Agent registration |
| `memory/manager.py` | Unified memory access layer |
| `memory/interaction_logger.py` | Immediate interaction persistence |
| `memory/episodic.py` | Session-level memory (SQLite) |
| `memory/procedural.py` | User profile + skill library (JSON) |
| `plugins/base.py` | Tool base class |
| `core/bus.py` | Inter-agent messaging |
| `core/bootstrap.py` | System startup |
| `users/owner_identity.py` | Single-owner identity + privacy |
| `users/privacy_filter.py` | Guest privacy protection |
| `perception/audio/stt.py` | Speech-to-text |
| `voice/tts.py` | Text-to-speech |
| `api/app.py` | FastAPI application |
| `web/src/` | Tauri desktop app (React + Tailwind) |

## Memory Architecture (5-tier)

| Tier | Technology | TTL |
|------|-----------|-----|
| Sensory Buffer | RAM deque | 30s |
| Working Memory | Token-budgeted priority queue | Session |
| Episodic Memory | SQLite + Qdrant | Permanent |
| Semantic Memory | Qdrant + BM25 + networkx | Permanent |
| Procedural Memory | JSON + Qdrant | Permanent |

Every interaction is also immediately persisted to `data/interactions.db` via `InteractionLogger`.

## Model Fleet

| Tier | Model | Backend | VRAM | Use |
|------|-------|---------|------|-----|
| nano | Qwen3-4B | TabbyAPI | ~3 GB | Routing, classification |
| voice_fast | Qwen3-8B abliterated | TabbyAPI | ~5 GB | Voice responses |
| fast | Qwen3-8B abliterated | TabbyAPI | ~5 GB | Standard conversation |
| smart | Qwen3-8B abliterated | TabbyAPI | ~5 GB | Complex reasoning |
| vision | MiniCPM-V 2.6 | Ollama | ~8 GB | Screen + webcam |
| embedding | BGE-M3 | Ollama | ~2 GB | All embeddings |

## Owner/Privacy System

Emily has ONE owner. Personal data is NEVER shared with non-owners.
- `users/owner_identity.py` — Owner verification via passphrase
- `users/privacy_filter.py` — Response filtering for guests
- Config: `config.yaml` → `owner:` section

## Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| Qdrant | 6333 | Vector database |
| SearXNG | 8888 | Private web search |
| Prometheus | 9090 | Metrics |
| Grafana | 3000 | Dashboards |
| Jaeger | 16686 | Tracing |

## DO NOT

- Put prompts outside `llm/prompt_builder.py`
- Do blocking I/O in async functions
- Auto-load `plugins/generated/` tools
- Skip `dry_run()` for new tools
- Change memory schemas without migration scripts
- Modify `security/` without user approval
- Call Emily "assistant", "bot", "NOVA", or "chatbot"
- Add unnecessary dependencies
- Commit `.env`, secrets, model weights, or `data/`
- Write functions without type hints, docstrings, and tests
