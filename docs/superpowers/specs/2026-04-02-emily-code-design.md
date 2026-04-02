# Emily Code — Design Spec

**Date:** 2026-04-02
**Status:** Approved
**Goal:** Give Emily Claude Code-level coding capabilities as always-available tools.

---

## 1. Core Principles

- **No mode switching.** Coding tools are always available. Emily uses them when appropriate.
- **Full local access for owner.** Owner-verified = unrestricted bash, git writes, file ops anywhere. Guest = sandboxed.
- **Single-agent driver with specialist escalation.** CodeAgent handles 90% of coding work. Dispatches to ResearchAgent, PlannerAgent, ReflectionAgent for complex sub-tasks.
- **Native tools for hot path, MCP for integrations.** Edit/Glob/Grep/Bash are native Python for sub-100ms latency. GitHub/Playwright/Context7 go through MCP.

---

## 2. Native Tools (plugins/builtin/)

### 2.1 EditTool — `plugins/builtin/edit_tool.py`

Surgical string replacement in files. Claude Code's Edit equivalent.

**Interface:**
```python
class EditTool(BaseTool):
    name = "edit"
    description = "Exact string replacement in files"
    requires_approval = False  # owner only; guest = True

    async def execute(self, params: dict, ctx: ExecutionContext) -> ToolResult:
        # params: file_path, old_string, new_string, replace_all (bool, default False)
        # Fails if old_string not found or not unique (unless replace_all=True)
        # Returns: diff of changes made
```

**Behavior:**
- Read file, find `old_string`, replace with `new_string`
- Fail if `old_string` not found → `ToolResult.fail("old_string not found in file")`
- Fail if `old_string` matches multiple locations and `replace_all=False` → `ToolResult.fail("old_string is not unique, use replace_all=True or provide more context")`
- Return unified diff of the change
- Atomic write (write to temp, rename)
- Preserve file permissions and encoding

### 2.2 GlobTool — `plugins/builtin/glob_tool.py`

Fast file pattern matching. Claude Code's Glob equivalent.

**Interface:**
```python
class GlobTool(BaseTool):
    name = "glob"
    description = "Find files by glob pattern"
    requires_approval = False

    async def execute(self, params: dict, ctx: ExecutionContext) -> ToolResult:
        # params: pattern (str), path (str, optional — defaults to cwd)
        # Returns: list of matching file paths, sorted by mtime (newest first)
```

**Behavior:**
- Uses `pathlib.Path.glob()` or `Path.rglob()` for `**` patterns
- Sorts results by modification time (newest first)
- Respects `.gitignore` patterns (skip `node_modules/`, `.git/`, `__pycache__/`, etc.)
- Max 1000 results (truncate with warning)

### 2.3 GrepTool — `plugins/builtin/grep_tool.py`

Content search with ripgrep. Claude Code's Grep equivalent.

**Interface:**
```python
class GrepTool(BaseTool):
    name = "grep"
    description = "Search file contents with regex"
    requires_approval = False

    async def execute(self, params: dict, ctx: ExecutionContext) -> ToolResult:
        # params: pattern (str, regex), path (str, optional),
        #         glob (str, optional — file filter e.g. "*.py"),
        #         type (str, optional — file type e.g. "py"),
        #         output_mode ("content"|"files_with_matches"|"count", default "files_with_matches"),
        #         context (int, optional — lines before+after),
        #         case_insensitive (bool, default False),
        #         max_results (int, default 100)
        # Returns: matching lines/files/counts depending on output_mode
```

**Behavior:**
- Shells out to `rg` (ripgrep) if available, falls back to Python `re` + `os.walk`
- Supports all ripgrep output modes: content (with line numbers), files_with_matches, count
- Context lines (-A/-B/-C equivalent)
- File type filtering (--type py, --type ts, etc.)
- Glob filtering (--glob "*.tsx")
- Case-insensitive flag
- Respects `.gitignore` by default

### 2.4 BashTool — `plugins/builtin/bash_tool.py`

Unrestricted shell execution. Replaces current allowlisted ShellTool for owner.

**Interface:**
```python
class BashTool(BaseTool):
    name = "bash"
    description = "Execute shell commands"
    requires_approval = False  # owner only; guest = requires_approval + sandbox

    async def execute(self, params: dict, ctx: ExecutionContext) -> ToolResult:
        # params: command (str), timeout_ms (int, default 120000),
        #         run_in_background (bool, default False)
        # Returns: stdout + stderr combined, exit code
```

**Behavior:**
- Owner: unrestricted execution via `asyncio.create_subprocess_shell`
- Guest: bubblewrap sandboxed execution (existing sandbox.py)
- Configurable timeout (default 2 min, max 10 min)
- Background execution support (returns immediately, result retrievable later)
- Working directory persists between calls within a session
- Environment inherits from user's shell profile
- Streams output for long-running commands

**Safety (even for owner):**
- Log all commands to audit log
- Warn on destructive patterns (`rm -rf /`, `dd if=`, `mkfs`) — execute after confirmation

### 2.5 GitTool (upgrade) — `plugins/builtin/git_tool.py`

Extend existing read-only git tool with write operations.

**New write operations:**
```python
# New actions added to existing GitTool:
"commit"    # stage files + commit with message
"branch"    # create/delete/switch branches
"push"      # push to remote (with -u flag support)
"pull"      # pull from remote
"merge"     # merge branches
"stash"     # stash/pop/list
"checkout"  # checkout files/branches
"tag"       # create/list tags
```

**Safety guards (even for owner, require confirmation):**
- `push --force` / `push --force-with-lease`
- `reset --hard`
- `branch -D` (force delete)
- `checkout .` / `restore .` (discard all changes)
- Push to `main`/`master`

**Existing read operations (unchanged):**
- `status`, `log`, `diff`, `show`, `blame`

### 2.6 LSPTool — `plugins/builtin/lsp_tool.py`

Language server protocol integration for code intelligence.

**Interface:**
```python
class LSPTool(BaseTool):
    name = "lsp"
    description = "Code intelligence via language servers"
    requires_approval = False

    async def execute(self, params: dict, ctx: ExecutionContext) -> ToolResult:
        # params: action (str), file_path (str), line (int), character (int)
        # actions: "definition", "references", "hover", "diagnostics",
        #          "completion", "rename", "symbols"
        # Returns: locations, type info, diagnostics, etc.
```

**Supported language servers:**
- Python: `basedpyright` (already in project deps)
- TypeScript: `typescript-language-server`
- Rust: `rust-analyzer`

**Behavior:**
- Lazy-start language servers on first use per language
- Keep servers alive for session duration
- JSON-RPC 2.0 over stdio (standard LSP transport)
- Cache workspace symbols for fast lookup

---

## 3. MCP Client — `mcp/client.py`

Emily consumes MCP servers as a client. New module.

### 3.1 Architecture

```
Emily LLM → CodeAgent → tool dispatch
                ├── native tool (edit/glob/grep/bash/git/lsp)
                └── mcp/client.py → MCP Server (stdio subprocess)
                        ├── GitHub MCP
                        ├── Playwright MCP
                        ├── Filesystem MCP
                        ├── Sequential Thinking MCP
                        └── Context7 MCP
```

### 3.2 MCP Client Implementation

```python
# mcp/client.py
class MCPClient:
    """Manages connections to MCP servers."""

    async def connect(self, server_name: str) -> None:
        """Lazy-start an MCP server subprocess, perform initialize handshake."""

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on a connected MCP server via JSON-RPC 2.0."""

    async def list_tools(self, server_name: str) -> list[ToolSchema]:
        """List available tools from a server."""

    async def disconnect(self, server_name: str) -> None:
        """Gracefully shut down a server subprocess."""

    async def disconnect_all(self) -> None:
        """Shut down all servers (called on Emily shutdown)."""
```

### 3.3 Auto-Registration

On startup (or first use), each MCP server's tools are discovered via `tools/list` and registered in Emily's `PluginRegistry` with naming convention `mcp__<server>__<tool>`:

```python
# Example: GitHub MCP's "create_pull_request" becomes:
# tool name: "mcp__github__create_pull_request"
# registered in plugins/registry.py alongside native tools
# CodeAgent can call it like any other tool
```

### 3.4 Configuration

```yaml
# config.yaml addition
mcp:
  servers:
    github:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"
    playwright:
      command: "npx"
      args: ["-y", "@playwright/mcp@latest"]
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/supernovyl"]
    sequential_thinking:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    context7:
      command: "npx"
      args: ["-y", "@upstash/context7-mcp@latest"]
```

### 3.5 Transport

- **stdio** (primary) — MCP server runs as subprocess, communicate via stdin/stdout JSON-RPC 2.0
- JSON-RPC 2.0 message framing: `Content-Length: N\r\n\r\n{json}`
- Async reader/writer tasks per server connection
- Heartbeat: if server doesn't respond within 30s, restart it

---

## 4. CodeAgent Upgrade — `agents/code_agent.py`

### 4.1 Agentic Coding Loop

```
User request
  → CodeAgent (code tier: Qwen3.5 27B abliterated)
    1. UNDERSTAND — read relevant files (Glob → Grep → Read)
    2. PLAN — inline reasoning, or escalate to Sequential Thinking MCP / PlannerAgent
    3. IMPLEMENT — Edit/Write tools to modify files
    4. VERIFY — Bash: run tests, linters (ruff, pyright, tsc), type checkers
    5. ITERATE — if verify fails, read error output, fix, re-verify (max 3 loops)
    6. COMMIT — Git tool: stage + commit with descriptive message
    7. ESCALATE — if stuck after 3 iterations, ask user or dispatch to specialist:
        → ResearchAgent (unknown API, need docs → Context7 MCP)
        → PlannerAgent (multi-file architecture change)
        → ReflectionAgent (post-task learning, update procedural memory)
```

### 4.2 Context Injection

Before the coding loop starts, CodeAgent auto-gathers:
- `git status` + current branch
- `git diff --stat` (what's changed)
- Project structure (top-level tree via Glob)
- Relevant file contents (based on user's request)
- Any `CLAUDE.md` / project-level instructions

This context is injected into the system prompt for the coding LLM call.

### 4.3 Tool Selection Intelligence

CodeAgent follows these rules (encoded in prompt):
- **Read before edit.** Never modify a file you haven't read.
- **Edit over Write.** Use Edit for existing files, Write only for new files.
- **Grep for discovery.** Don't guess file paths — search first.
- **Verify after implement.** Run tests/linters after every change. "Should work" is not verification.
- **Small edits.** Prefer surgical Edit replacements over rewriting entire files.
- **Git discipline.** Commit logical units. Descriptive messages. Never force push without asking.

---

## 5. Prompt Engineering — `llm/prompt_builder.py`

### 5.1 Coding Context Prompt

New method: `build_coding_context_prompt()` — injected when coding tools are in use.

```python
def build_coding_context_prompt(
    git_status: str,
    git_branch: str,
    project_structure: str,
    project_instructions: str | None,  # CLAUDE.md or similar
) -> str:
    """Build context block for coding tasks."""
```

Contains:
- Project structure summary
- Git state (branch, dirty files, recent commits)
- Project-level instructions if any (`CLAUDE.md`)
- Tool usage rules (read before edit, verify after implement, etc.)
- Anti-patterns (don't guess paths, don't write untested code, etc.)

### 5.2 Tool Descriptions

Each tool gets a precise description that teaches the LLM when and how to use it:
- Edit: "For modifying existing files. Provide exact old_string to match."
- Glob: "For finding files by name pattern. Use before reading unknown paths."
- Grep: "For searching file contents. Use regex. Prefer over Bash grep."
- Bash: "For running commands. Use for tests, builds, linters. Not for file reading."
- Git: "For version control. Always commit logical units with descriptive messages."
- LSP: "For code intelligence. Use for go-to-definition, find references, diagnostics."

---

## 6. Security Model

### 6.1 Owner (verified via `owner/owner_identity.py`)

- Full local access: unrestricted bash, file ops anywhere, git writes
- MCP servers: all available
- Destructive operations: require confirmation (force push, rm -rf, reset --hard)
- Audit log: all tool calls logged to `logs/audit.log`

### 6.2 Guest

- Sandboxed execution: bubblewrap for bash, restricted file paths
- Git: read-only
- MCP servers: Context7 and Sequential Thinking only (no GitHub write, no Playwright)
- File ops: restricted to `config.yaml → tools.allowed_paths`

### 6.3 Audit

All tool executions logged:
```json
{"timestamp": "...", "tool": "bash", "command": "pytest tests/", "user": "owner", "exit_code": 0}
```

---

## 7. Configuration

### 7.1 config.yaml additions

```yaml
mcp:
  servers:
    github:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"
    playwright:
      command: "npx"
      args: ["-y", "@playwright/mcp@latest"]
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/supernovyl"]
    sequential_thinking:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    context7:
      command: "npx"
      args: ["-y", "@upstash/context7-mcp@latest"]

coding:
  max_iteration_loops: 3        # max fix-verify loops before asking user
  auto_commit: false             # don't auto-commit unless user asks
  auto_lint: true                # run ruff/pyright after edits
  auto_test: true                # run related tests after edits
  lsp_servers:
    python: "basedpyright-langserver"
    typescript: "typescript-language-server"
    rust: "rust-analyzer"
```

### 7.2 config.py additions

```python
class MCPServerConfig(BaseModel):
    command: str
    args: list[str] = []
    env: dict[str, str] = {}

class MCPConfig(BaseModel):
    servers: dict[str, MCPServerConfig] = {}

class CodingConfig(BaseModel):
    max_iteration_loops: int = 3
    auto_commit: bool = False
    auto_lint: bool = True
    auto_test: bool = True
    lsp_servers: dict[str, str] = {}
```

---

## 8. File Map

New files:
```
mcp/
  __init__.py
  client.py              — MCP client (JSON-RPC 2.0 stdio transport)
  registry.py            — MCP tool auto-registration into Emily's PluginRegistry

plugins/builtin/
  edit_tool.py           — Surgical file editing (old_string → new_string)
  glob_tool.py           — Fast file pattern matching
  grep_tool.py           — Ripgrep content search
  bash_tool.py           — Unrestricted shell execution (owner) / sandboxed (guest)
  lsp_tool.py            — Language server protocol integration
```

Modified files:
```
plugins/builtin/git_tool.py  — Add write operations (commit, push, branch, merge, etc.)
plugins/registry.py          — Register new tools + MCP tool auto-registration
agents/code_agent.py         — Agentic coding loop (understand→plan→implement→verify→iterate)
llm/prompt_builder.py        — Add build_coding_context_prompt()
config.py                    — Add MCPConfig, CodingConfig
config.yaml                  — Add mcp + coding sections
core/bootstrap.py            — Initialize MCP client on startup, shutdown on exit
```

Test files:
```
tests/unit/test_edit_tool.py
tests/unit/test_glob_tool.py
tests/unit/test_grep_tool.py
tests/unit/test_bash_tool.py
tests/unit/test_git_tool_write.py
tests/unit/test_lsp_tool.py
tests/unit/test_mcp_client.py
tests/unit/test_code_agent_loop.py
```

---

## 9. Implementation Priority

1. **Edit + Glob + Grep + Bash tools** — core coding power, no external deps
2. **Git write operations** — extend existing tool
3. **MCP client + auto-registration** — enables GitHub/Playwright/Context7
4. **CodeAgent agentic loop** — the brain that uses all the tools
5. **LSP tool** — code intelligence (can be added incrementally)
6. **Coding context prompt** — teaches the LLM to use tools well
7. **Config + bootstrap wiring** — tie it all together
8. **Tests** — unit tests for each component
