# Emily — Threat Model & Security Analysis

> Emily runs entirely on local hardware and is designed with a **zero-trust,
> zero-egress-by-default** security posture. This document analyzes threats,
> mitigations, and residual risks.

---

## Trust Boundaries

```
┌─────────────────────────────────────────────────────┐
│  TRUSTED ZONE (Emily's process space)               │
│  ┌──────────────┐   ┌──────────────┐                │
│  │ Core Agents  │   │  Memory DBs  │                │
│  └──────────────┘   └──────────────┘                │
│  ┌──────────────┐   ┌──────────────┐                │
│  │ LLM (Ollama) │   │  Qdrant      │                │
│  └──────────────┘   └──────────────┘                │
├─────────────────────────────────────────────────────┤
│  SEMI-TRUSTED (sandboxed tool execution)            │
│  ┌──────────────────────────────────────┐           │
│  │  bubblewrap containers               │           │
│  │  (no network, limited filesystem)    │           │
│  └──────────────────────────────────────┘           │
├─────────────────────────────────────────────────────┤
│  UNTRUSTED (external inputs)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Voice   │  │  Files   │  │  Web content     │  │
│  │  Input   │  │  Dropped │  │  (SearXNG fetch) │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Threat Analysis

### T1 — Prompt Injection via Voice or Text

**Attack**: Adversary speaks or sends text containing instructions that override Emily's system prompt or make her execute unintended actions.

**Severity**: High  
**Likelihood**: Medium (requires physical or network access)

**Mitigations**:
- System prompt prepended with injection resistance instructions in `llm/prompt_builder.py`
- Tool calls with `requires_approval=True` require explicit confirmation even if Emily "decides" to call them
- All LLM-generated tool calls validated against JSON Schema before execution
- Audit log records every tool invocation with its triggering prompt segment

**Residual Risk**: LLMs cannot be made fully injection-proof. The consent gate (Layer 9) is the primary defense for high-impact actions.

---

### T2 — Prompt Injection via Ingested Documents (RAG Poisoning)

**Attack**: A malicious document placed in `knowledge/` contains hidden instructions (e.g., white text on white background in PDF) that Emily ingests and later retrieves as context, causing unintended behavior.

**Severity**: High  
**Likelihood**: Low (requires file system access to knowledge/)

**Mitigations**:
- Ingested documents are chunked as data, not instructions
- System prompt explicitly marks RAG context as "external data, not instructions"
- PII scrubber (`security/pii_scrubber.py`) scans all ingested content
- Documents are stored with source metadata; Emily can be asked "where did you learn that?"
- File system watcher only monitors `knowledge/` — path is configurable and access-controlled

**Residual Risk**: Sophisticated adversarial documents can still influence model behavior through the RAG context window. Manual review of ingested documents is recommended.

---

### T3 — Tool Sandbox Escape

**Attack**: A malicious or buggy generated Python tool attempts to access the filesystem outside the allowlist, make network connections, or escalate privileges.

**Severity**: Critical  
**Likelihood**: Low (generated tools require user approval)

**Mitigations**:
- All tool execution in `bubblewrap` user-namespace containers
- No network access inside sandbox (verified by bwrap `--unshare-net`)
- Filesystem limited to `allowed_paths` from config + `/tmp/emily_sandbox`
- Process resource limits: CPU time, memory (ulimit enforced in bwrap invocation)
- Every tool has `dry_run()` that must be implemented and tested
- Generated tools (ToolBuilderAgent) require explicit user approval before loading
- Code executor uses restricted Python: blocked modules list (os.system, subprocess, socket, etc.)

**Residual Risk**: User-namespace escapes exist in older kernels. Arch Linux with kernel 6.18+ mitigates known escapes. Running as non-root (no setuid) reduces impact.

---

### T4 — LLM Model Weight Tampering

**Attack**: Adversary replaces Ollama model files with compromised weights.

**Severity**: Critical  
**Likelihood**: Very Low (requires local filesystem access)

**Mitigations**:
- Ollama verifies model manifest SHA256 checksums on load
- Model files in `/usr/share/ollama` (system path, root-owned)
- Audit log records model version used for every inference
- `scripts/setup.sh` validates model checksums after download

**Residual Risk**: If an attacker has root access, all local security is compromised regardless.

---

### T5 — Memory Exfiltration

**Attack**: Adversary reads Emily's memory databases (SQLite, Qdrant storage, procedural JSON) to extract sensitive user information.

**Severity**: High  
**Likelihood**: Medium (requires filesystem read access)

**Mitigations**:
- All memory databases encrypted at rest using `age` (X25519 + ChaCha20-Poly1305)
- Key stored in `~/.emily_key` (user home, mode 0600)
- Qdrant storage directory encrypted at OS level via LUKS (user-configured)
- PII scrubber removes/redacts sensitive entities before disk writes
- Dead man's switch: if device leaves home network for >30 days, episodic/semantic memory auto-wipes

**Residual Risk**: Memory is decrypted at runtime. Cold boot attacks or live memory dumps could expose plaintext data.

---

### T6 — API Endpoint Abuse

**Attack**: Process on the same machine or local network calls the Emily REST API or WebSocket endpoint to extract data or trigger unintended actions.

**Severity**: Medium  
**Likelihood**: Medium (API bound to 127.0.0.1 by default)

**Mitigations**:
- API server bound to `127.0.0.1` by default (loopback only)
- All endpoints require Bearer token authentication when `EMILY_API_SECRET` or `api.secret_key` is set (`api/auth.py` + middleware)
- Rate limiting on all endpoints (configurable `api.rate_limit_requests` / `api.rate_limit_window_s`)
- CORS configurable via `api.cors_origins` (default local-only origins)
- Request body size limit via `api.max_body_size_bytes`
- Tool-invoking endpoints (POST /tools/{name}) require the same approval as voice-triggered tools

**Residual Risk**: Local process with user permissions can call the API if it has the secret. This is accepted; Emily is a single-user local system.

---

### T7 — Microphone / Camera Eavesdropping

**Attack**: Emily continuously listens via microphone and captures webcam frames; this data could be misused or exfiltrated.

**Severity**: High (privacy)  
**Likelihood**: Very Low (local process only)

**Mitigations**:
- Audio: only VAD-gated speech segments sent to STT. Raw audio never written to disk.
- Webcam: frame captures processed in-process by vision model, never written to disk unless explicitly requested
- Sensory buffer is a RAM ring buffer with no disk persistence
- Zero-egress firewall policy: no audio/video data can leave the machine
- Physical indicator (TUI status bar) always shows when microphone is active

**Residual Risk**: Process compromise could enable live audio access. Physical microphone mute is the ultimate safeguard.

---

### T8 — Generated Tool Malware

**Attack**: ToolBuilderAgent generates a tool that contains malicious code (either via LLM hallucination or prompt injection).

**Severity**: High  
**Likelihood**: Low

**Mitigations**:
- Generated tool code presented to user for review (diff view in TUI/web UI) before loading
- All generated tools run in bubblewrap sandbox (T3 mitigations apply)
- Generated tools are statically analyzed before presentation (AST scan for dangerous patterns)
- Generated tools placed in `plugins/generated/` which is excluded from auto-load on startup
- Audit log records when a generated tool was loaded and by whom

**Residual Risk**: User may approve malicious code without reviewing carefully.

---

### T9 — PII Leakage into Logs

**Attack**: Sensitive user data (passwords spoken aloud, credit card numbers, SSNs) is captured via STT and written to logs.

**Severity**: High  
**Likelihood**: Medium (conversational AI naturally handles personal information)

**Mitigations**:
- PII scrubber (`security/pii_scrubber.py`) runs NER on all text before log writes
- Detected PII entities are either redacted (`[REDACTED]`) or encrypted inline
- Audit log uses different retention policy from debug logs
- structlog JSON formatter strips patterns matching common PII regexes as a secondary defense

**Residual Risk**: Novel PII formats not covered by NER patterns will not be detected. Users should be informed of this limitation.

---

### T10 — Home Assistant Integration Abuse

**Attack**: Emily's Home Assistant integration is used to trigger dangerous automations (e.g., unlock doors, disable alarms).

**Severity**: High  
**Likelihood**: Low

**Mitigations**:
- Home Assistant tool (`plugins/builtin/home_assistant.py`) is in `requires_approval=True` by default for write operations
- Allowlist of permitted entity domains configured in `config.yaml`
- HA token stored in environment variable, never in config.yaml or logs
- Voice confirmation phrase required for physical security entities

**Residual Risk**: User may grant broad HA permissions. HA-side automation restrictions (minimum required privileges) are recommended.

---

## Security Checklist

- [ ] `age` key generated and stored in `~/.emily_key` (mode 0600)
- [ ] `bubblewrap` installed and verified: `bwrap --version`
- [x] API secret: set `EMILY_API_SECRET` in `.env` or environment (not in `config.yaml`); required for API auth
- [ ] LUKS encryption on the partition containing `data/qdrant_storage/` (operational; see setup docs)
- [ ] HA token has minimum required scope (not admin token)
- [ ] Firewall egress rules applied via `scripts/setup.sh` (operational)
- [ ] `knowledge/` directory permissions: 700 (owner only)
- [x] Audit log retention: set `security.audit_retention_days` (e.g. 30) to trim on startup; rotation is configurable
- [ ] Run `pip-audit` (or `uv pip audit`) periodically or in CI to check dependencies for known vulnerabilities

---

## Privacy Guarantees

| Data Type | Storage | Encrypted | Retention |
|-----------|---------|-----------|-----------|
| Voice audio | RAM only (never disk) | N/A | Discarded after STT |
| Transcripts | `data/transcripts/` | Yes (age) | Until manual deletion |
| Episode summaries | `data/episodes.db` | Yes (age) | Configurable |
| Semantic memories | Qdrant storage | Yes (age) | With temporal decay |
| Webcam frames | RAM only (never disk) | N/A | Discarded after vision model |
| API keys / tokens | `.env` only | No (env var) | Until file deletion |
| Audit log | `logs/audit.log` | Append-only | 90 days rolling |
