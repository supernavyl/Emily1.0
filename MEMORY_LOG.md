# Emily — Memory Log

This file records all significant architectural and implementation changes.
Append a new entry for every phase completion and every significant decision change.

Format:
```
## YYYY-MM-DD — Phase N: <title>
**Changed:** <what changed>
**Why:** <rationale>
**Affects:** <list of affected modules>
---

## 2026-02-28 — Desktop App: Password Protection, Settings, Privacy & Policies

**What changed:**

1. **Rust-side password authentication** (`web/src-tauri/src/auth.rs`):
   - SHA-256 password hashing (never stored plaintext)
   - `auth_is_setup`, `auth_set_password`, `auth_verify`, `auth_change_password` Tauri commands
   - 5-attempt lockout with 5-minute cooldown
   - Persisted to `emily_auth.json` in app data dir

2. **Login page** (`web/src/pages/LoginPage.tsx`):
   - First-run: password creation with confirmation
   - Subsequent: password entry with show/hide toggle
   - Lockout display, error messages, themed UI

3. **Auth store** (`web/src/stores/auth.ts`):
   - Zustand store bridging React ↔ Tauri Rust commands
   - `checkSetup`, `login`, `setupPassword`, `changePassword`, `logout`

4. **Settings page** (`web/src/pages/SettingsPage.tsx`) — 6 tabs:
   - **Display**: font size, animations, compact mode, metrics toggle
   - **Privacy**: privacy level (full/balanced/strict), analytics, error reporting
   - **Security**: auto-lock, lock timeout, change password, lock now
   - **Data**: retention period, auto-backup toggle
   - **Advanced**: debug mode, experimental features, memory limit, voice logging, reset
   - **Policies**: full Privacy Policy v1.0, Terms of Service v1.0, open source licenses

5. **Settings store** (`web/src/stores/settings.ts`):
   - Zustand + persist middleware (localStorage)
   - All display, privacy, security, data, advanced settings
   - Policy acceptance tracking with timestamps

6. **App.tsx** updated:
   - Auth gate — LoginPage shown until authenticated
   - Loading spinner during auth check
   - Settings route added (`/settings`)

7. **AppNav** updated: Settings icon in nav bar

8. **Tauri config**:
   - `Cargo.toml`: added `sha2` crate
   - `lib.rs`: wired auth commands into invoke handler
   - `capabilities/default.json`: added `core:path:default` permission

**Why:** User requested password protection for the Tauri desktop app, advanced settings/customization, and official privacy policies/terms of service.

**Affects:**
- New: `web/src-tauri/src/auth.rs` (Rust password auth)
- Modified: `web/src-tauri/src/lib.rs` (auth commands registered)
- Modified: `web/src-tauri/Cargo.toml` (sha2 dep)
- Modified: `web/src-tauri/capabilities/default.json` (path permission)
- New: `web/src/pages/LoginPage.tsx`
- New: `web/src/pages/SettingsPage.tsx` (6-tab settings)
- New: `web/src/stores/auth.ts`
- New: `web/src/stores/settings.ts`
- Modified: `web/src/App.tsx` (auth gate + settings route)
- Modified: `web/src/components/layout/AppNav.tsx` (settings nav)

---

## 2026-02-28 — Single Owner Identity & Privacy System

**What changed:**

1. **Owner Identity System** (`users/owner_identity.py`):
   - Created `OwnerIdentityManager` for single-owner mode
   - `SpeakerType` enum: OWNER, GUEST, UNKNOWN, VERIFICATION_NEEDED
   - Passphrase-based verification (SHA-256 hashed)
   - Lockout protection after failed attempts
   - Session-based verification with timeout
   - Personal facts storage (only accessible by owner)

2. **Enhanced Onboarding** (`users/onboarding_enhanced.py`):
   - Personal questions with CONFIRMATION of each answer
   - Questions: name, passphrase, occupation, hobbies, projects, preferences
   - Passphrase setup during onboarding (never spoken aloud after)
   - Correction flow if user says answer is wrong
   - Privacy topic collection (what never to share)

3. **Privacy Filter** (`users/privacy_filter.py`):
   - Filters Emily's responses for non-owners
   - Detects when response contains personal info
   - Replaces personal facts with "[private]" for guests
   - Provides polite refusal messages for private queries
   - Privacy-aware system prompt injection

4. **Configuration** (`config.yaml`, `config.py`):
   - Added `owner` section with settings:
     - `enabled: true` - Single-owner mode
     - `require_verification: true` - Passphrase required
     - `verification_timeout_minutes: 60`
     - `guest_mode_enabled: true` - Allow limited guest access
     - `share_personal_with_guests: false` - NEVER share personal info
     - `lockout_after_failed_attempts: 3`

5. **Documentation** (`OWNER_PRIVACY_SYSTEM.md`):
   - Complete guide to owner identity system
   - Privacy protection details
   - Configuration options
   - Integration guide for developers
   - FAQ

**Why:** User requested:
1. Emily asks personal questions first and confirms answers
2. Only ONE user (owner) who Emily listens to
3. Other people treated as guests
4. Personal data only shared with the owner

**Affects:**
- New: `users/owner_identity.py` (OwnerIdentityManager)
- New: `users/onboarding_enhanced.py` (personal questions with confirmation)
- New: `users/privacy_filter.py` (response filtering)
- New: `users/__init__.py` (module exports)
- Modified: `config.yaml` (added `owner` section)
- Modified: `config.py` (added `OwnerConfig` class)
- New: `OWNER_PRIVACY_SYSTEM.md` (documentation)

**Data files created:**
- `data/owner_identity.json` (auto-created on first run)

**Privacy guarantees:**
- ✅ Single owner mode
- ✅ Passphrase verification (SHA-256 hashed, never stored plaintext)
- ✅ Personal facts only accessible to verified owner
- ✅ Guests get polite refusals for personal queries
- ✅ All responses filtered to remove personal info for non-owners
- ✅ Lockout after failed verification attempts
- ✅ Session timeout for re-verification

---

## 2026-02-28 — Complete Interaction Persistence System

**What changed:**
1. **New interaction logging system** (`memory/interaction_logger.py`):
   - Dedicated SQLite database for all user/assistant turns
   - Write-through persistence with `PRAGMA synchronous=FULL`
   - WAL mode for durability and concurrent access
   - Full-text search (FTS5) for searching conversations
   - Automatic backups every 30 minutes
   - Export functionality to JSON
   - Comprehensive API for viewing and querying interactions

2. **Configuration updates**:
   - `config.py`: Added `EpisodicMemoryConfig` fields:
     - `save_all_interactions: bool = True`
     - `interactions_db_path: str = "data/interactions.db"`
     - `auto_backup_interval_minutes: int = 30`
   - `config.yaml`: Enabled interaction persistence by default

3. **Memory manager integration** (`memory/manager.py`):
   - Added `InteractionLogger` initialization and connection
   - Modified `add_user_turn()` to immediately save to interactions.db
   - Modified `add_assistant_turn()` to immediately save to interactions.db
   - Added `shutdown()` method to properly close logger with final backup

4. **New viewing tool** (`scripts/view-interactions.py`):
   - View recent interactions with filters
   - Full-text search across all conversations
   - Session-specific views
   - Export to JSON (all or by session)
   - Statistics (total, by role, etc.)
   - Manual backup creation

5. **Documentation** (`INTERACTION_PERSISTENCE.md`):
   - Complete guide to interaction persistence
   - Usage examples for viewing tool
   - Storage details and database structure
   - Privacy, security, and performance information
   - Troubleshooting guide

**Why:** User requested that every interaction must be saved on the computer in Emily's memory. This implements a fail-safe, crash-resistant persistence layer that guarantees zero data loss. Every single user input and Emily response is immediately written to disk with full durability guarantees, separate from the existing episodic memory system for redundancy.

**Affects:**
- `config.py` - Added interaction logging configuration
- `config.yaml` - Enabled `save_all_interactions: true`
- `memory/interaction_logger.py` - New comprehensive logging system (496 lines)
- `memory/manager.py` - Integrated interaction logger into startup/turns/shutdown
- `scripts/view-interactions.py` - New CLI tool for viewing/exporting
- `INTERACTION_PERSISTENCE.md` - Complete documentation
- New database: `data/interactions.db` (auto-created)
- New backups: `data/backups/` (auto-created)

**Data guarantees:**
- ✅ Every turn saved immediately to SQLite with fsync
- ✅ WAL mode + synchronous=FULL for crash safety
- ✅ Automatic backups every 30 minutes
- ✅ Full-text search capability
- ✅ Export to JSON for external processing
- ✅ Zero data loss even if Emily crashes

---

## 2026-02-28 — Multilingual Capabilities Documentation

**What changed:**
1. **New documentation** (`MODELS_AND_LANGUAGES.md`):
   - Comprehensive guide to Emily's AI models
   - Full multilingual support details (119 languages for text, 99 for speech)
   - Model architecture and use cases
   - Language-specific configuration instructions
   - Performance by language tier breakdown
2. **README.md updated**:
   - Added note about 119-language support in Operations Guide
   - Added link to detailed language documentation

**Why:** User asked about what models Emily uses and whether she supports multiple languages. Created comprehensive documentation explaining Emily's multilingual capabilities (119 languages via Qwen3 models, 99 languages via Whisper STT) and the complete model fleet architecture.

**Affects:**
- New file: `MODELS_AND_LANGUAGES.md`
- Updated: `README.md` (added multilingual note)
- Documentation: Complete reference for model selection and language support

---

## 2026-02-28 — Vision System Enabled: Camera and Screen Access

**What changed:**
1. **`config.yaml`**:
   - Set `vision.enabled: true` to enable vision pipeline
   - Enabled `vision.emotion_detection: true` for facial expression analysis
2. **New setup script** (`scripts/setup-vision.sh`):
   - Automated setup script for camera and screen access permissions
   - Checks and installs required dependencies (opencv-python, mss, Pillow)
   - Verifies video group membership and device access
   - Tests camera and screen capture functionality
3. **New documentation** (`docs/VISION_SETUP.md`):
   - Comprehensive guide for enabling vision system
   - Linux permissions setup
   - Troubleshooting common issues
   - Privacy and security information

**Why:** User requested camera and screen access be enabled. Vision system provides Emily with visual context awareness including screen understanding, presence detection, and optional emotion recognition via facial analysis.

**Affects:** 
- `config.yaml` (vision section)
- `perception/vision/` (screen_capture.py, webcam.py, pipeline.py)
- New files: `scripts/setup-vision.sh`, `docs/VISION_SETUP.md`
- Runtime: Vision pipeline will now initialize and capture screen/webcam when Emily starts

---

## 2026-02-27 — Live Voice Stabilization: Backchannels Disabled

**What changed:**
1. **`config.yaml`**:
   - Set `voice_engine.backchannels_enabled: false` for live runtime.
2. Restarted Emily GUI voice engine to apply config.

**Why:** Live FSM traces showed persistent `LISTENING ↔ BACKCHANNELING` oscillation causing unstable turn handling and poor user experience. Disabling backchannels removes this loop entirely while preserving STT → PROCESSING → SPEAKING flow.

**Affects:** Live conversational behavior (no backchannel interjections). Turn processing should be more stable under noisy conditions.

---

## 2026-02-27 — Backchannel FSM Thrash Guard

**What changed:**
1. **`conversation/fsm.py`**:
   - Added backchannel cooldown state fields:
     - `_backchannel_cooldown_until`
     - `_backchannel_retry_s`
     - `_backchannel_emit_cooldown_s`
   - Added helper methods:
     - `_can_enter_backchanneling()` to gate LISTENING -> BACKCHANNELING transitions
     - `_mark_backchannel_attempt()` to apply cooldown after backchannel cycles
   - Updated turn detection path so `TurnAction.BACKCHANNEL` only transitions when cooldown allows.
   - Updated backchannel loop to mark cooldown for both emitted and non-emitted backchannel attempts.
2. **`tests/unit/test_conversation_fsm.py`**:
   - Added `TestBackchannelCooldown` coverage for initial allow, retry cooldown, and longer post-emit cooldown behavior.

**Why:** Live runtime logs showed rapid `LISTENING ↔ BACKCHANNELING` oscillation (state thrash) causing noisy behavior and premature processing transitions.

**Affects:** Conversation FSM backchannel stability during live voice interactions; reduces repetitive backchannel transition loops.

---

## 2026-02-27 — Removed Generic LLM Error Reply

**What changed:**
1. **`llm/orchestrator.py`**:
   - Removed the hardcoded generic fallback sentence in `ConversationLLMOrchestrator.generate_streaming()` exception handling.
   - On generation error, the orchestrator now logs `llm_generation_error` and returns without yielding canned speech.

**Why:** User requested removal of generic responses. This avoids stock apology phrasing being spoken when upstream LLM generation fails.

**Affects:** Voice response behavior during LLM streaming exceptions (silent fail with logs instead of generic fallback text).

---

## 2026-02-27 — Live Voice STT Noise-Loop Guardrails

**What changed:**
1. **`perception/audio/streaming_stt.py`**:
   - Added stronger final transcript quality gates in `commit_utterance()` beyond confidence-only checks.
   - Implemented lexical-noise heuristics (minimum words, unique-token ratio, max repeated-token ratio, short-utterance confidence gate).
   - Added structured rejection reasons/logging (`low_confidence`, `fragmented`, `repetitive`) and centralized empty-transcript reject handling.
2. **`conversation/fsm.py`**:
   - Added `_is_transcript_usable()` defensive gate before LLM response generation.
   - Rejected noisy/fragmented non-empty transcripts before orchestrator/agent-bus calls to prevent repeated fallback speech loops.
   - Emitted `stt_rejected` perception diagnostics and applied cooldown when transcript quality is insufficient.
3. **`config.py` / `config.yaml`**:
   - Extended `STTConfig` and runtime config with new streaming quality controls:
     - `streaming_min_final_words`
     - `streaming_min_unique_ratio`
     - `streaming_max_repeat_ratio`
     - `streaming_short_utterance_confidence`
4. **Tests**:
   - `tests/unit/test_streaming_stt_config.py`: Added regression tests for repetitive-fragment rejection and short high-confidence acceptance.
   - `tests/unit/test_conversation_fsm.py`: Added transcript usability tests covering rejection and acceptance boundaries.

**Why:** Live logs showed STT committing fragmented/repetitive utterances that still triggered response generation, causing repeated generic “I had trouble with that” replies.

**Affects:** Live voice turn acceptance path, STT/FSM resilience to noisy transcripts, and debuggability via explicit rejection reasons.

---

## 2026-02-27 — Voice Test Stabilization (AEC + Lifecycle)

**What changed:**
1. **`tests/unit/test_voice_engine.py`**:
   - Updated `TestAEC.test_pure_echo_reduction` to use the current `AECConfig` API (`tail_length_ms` + `sample_rate`) instead of removed `filter_length` constructor arg.
   - Kept equivalent legacy test intent (100 filter taps) by setting `tail_length_ms=100` and `sample_rate=1000`.
2. **`tests/unit/test_voice_engine_lifecycle.py`**:
   - Fixed `test_turn_detector_receives_config_thresholds` to use `_patch_voice_engine_imports()` so `VoiceEngine.start()` stays fully mocked and does not hang on real FSM runtime.
   - Extended `_patch_voice_engine_imports()` to expose `turn_cls` from the patched `conversation.turn_detector` module for explicit constructor-argument assertions.
   - Added `SimpleNamespace` import to carry mocked handles (`fsm`, `turn_cls`) from the helper context.

**Why:** Voice/STT test execution surfaced two blockers: one hard failure from an outdated AEC test signature and one lifecycle test hang caused by incomplete mocking of lazy imports in `VoiceEngine.start()`.

**Affects:** Voice unit test reliability and CI/local test determinism for AEC and VoiceEngine lifecycle threshold wiring.

---

## 2026-02-27 — Live Tabby runtime activation and model-ID sync

**What changed:**
- Installed and initialized TabbyAPI runtime in `~/TabbyAPI` with CUDA inference extras (`[cu12]`), then launched it with local EXL2 model `Huihui-Qwen3-14B-abliterated-v2-exl2`.
- Downloaded the abliterated EXL2 model into `~/models/tabby/Huihui-Qwen3-14B-abliterated-v2-exl2`.
- Updated `config.yaml` text tiers (`nano`, `voice_fast`, `fast`, `smart`, `reasoning`) to match the currently loaded Tabby `/v1/models` ID.
- Updated `scripts/verify-tabbyapi.sh` hardcoded model expectations/startup hints to current active model and improved model ID parsing from `config.yaml` with section-scoped `awk`.

**Why:** Tabby-first routing was already implemented, but runtime still produced `tabbyapi_model_not_loaded` warnings due to model-ID mismatch. This change makes the running Tabby model and Emily config consistent so voice/chat can execute on the active uncensored Tabby model without text-tier mismatch warnings.

**Affects:** `config.yaml`, `scripts/verify-tabbyapi.sh`, runtime environment (`~/TabbyAPI`, `~/models/tabby`).

---

## 2026-02-27 — Tabby-first voice routing and backend isolation

**What changed:**

1. **Tabby-first text/voice tier config** (`config.yaml`): Set `llm.backend` to `tabbyapi`, moved `nano`/`voice_fast`/`fast`/`smart`/`reasoning` to Tabby model IDs, and updated `llm.tier_backend` so all text/voice tiers route to TabbyAPI by default.

2. **Balanced voice escalation** (`agents/conversation.py`): Removed unconditional `VOICE_FAST` forcing in voice mode. Voice now forces `voice_fast` only below `voice_fast_complexity_threshold`, allowing complex turns to escalate to higher tiers.

3. **Tabby-first health validation updates** (`llm/fleet.py`, `scripts/verify-tabbyapi.sh`, `scripts/start-emily.sh`):
   - Startup now validates all Tabby-backed text tiers (including `nano` and `voice_fast`).
   - Verification script now checks Tabby backend mapping for `nano`/`voice_fast`/`fast`/`smart`/`reasoning` and reports configured model IDs per tier.
   - Startup script messaging and flow were updated to reflect Tabby-first runtime semantics.

4. **Non-Tabby capability isolation** (`llm/fleet.py`): Embedding now follows configured backend (TabbyAPI supported), and vision calls are explicitly guarded as Ollama-only with a clear runtime error when misconfigured.

5. **Routing tests added** (`tests/unit/test_conversation_rag.py`): Added coverage proving voice mode forces `voice_fast` for simple turns and allows escalation for complex turns.

**Why:** This implements a Tabby-first runtime for all feasible text/voice paths while keeping non-Tabby capabilities explicit and isolated, improving voice quality/latency tradeoffs without hard-locking every turn to `voice_fast`.

**Affects:** `config.yaml`, `agents/conversation.py`, `llm/fleet.py`, `scripts/verify-tabbyapi.sh`, `scripts/start-emily.sh`, `tests/unit/test_conversation_rag.py`.

---

## 2026-02-27 — Temporary Ollama abliterated routing for live voice test

**What changed:**

1. **LLM routing switched for test run** (`config.yaml`): set text tiers (`nano`, `voice_fast`, `fast`, `smart`, `reasoning`) to Ollama backend and mapped model IDs to `huihui_ai/qwen3-abliterated:8b` to bypass unavailable local TabbyAPI during voice validation.

2. **Local abliterated model provisioned** (runtime): pulled `huihui_ai/qwen3-abliterated:8b` via Ollama for local uncensored inference in the voice pipeline.

3. **End-to-end bring-up revalidated** (`main.py --no-gui`): full-duplex voice engine reached steady running state with STT + Kokoro TTS active and voice model pre-warmed against the new abliterated Ollama model.

4. **Fleet inference check completed** (`llm/fleet.py` path): direct `LLMFleet.chat()` returned `READY` using `huihui_ai/qwen3-abliterated:8b`, confirming text generation path no longer depends on TabbyAPI for this test profile.

**Why:** Voice pipeline could initialize but failed response generation when TabbyAPI was unreachable. Temporary Ollama routing was required to validate uncensored local model response path for voice testing.

**Affects:** `config.yaml`, local Ollama model store, voice testing workflow (`main.py --no-gui`, `llm/fleet.py`).

---

## 2026-02-27 — Voice runtime unblock for headless E2E validation

**What changed:**

1. **Startup script parser fix** (`scripts/start-emily.sh`): corrected the broken `case` entry for `infra` so `status` and other command paths execute without shell syntax failure.

2. **Voice/runtime dependency bootstrap** (environment): installed missing runtime packages required for voice test bring-up: `pyrage`, `sounddevice`, `faster-whisper`, `pytest`, `pytest-asyncio`.

3. **Virtualenv pip restoration** (environment): installed `pip` inside `.venv` via `ensurepip`, which unblocked runtime code paths that invoke package installation hooks during startup.

4. **Headless voice startup re-validated** (`main.py --no-gui`): Emily now reaches `voice_mode_new_engine`, starts capture/STT/TTS stack, and remains running in steady state; Kokoro loads successfully while CSM remains unavailable due gated model access.

**Why:** Full voice pipeline tests were blocked before runtime by multiple environment and scripting issues (security backend unavailable, shell syntax breakage, missing audio/STT deps, missing pip in venv). These fixes were required to get Emily into an actual running full-duplex voice state.

**Affects:** `scripts/start-emily.sh`, local `.venv` runtime environment, voice bring-up path through `main.py`/`core/bootstrap.py`.

---

## 2026-02-27 — Voice full-flow reliability tuning (start/run/stop + fallback)

**Changed:** Applied targeted voice reliability updates and validations:
- `conversation/fsm.py` silence fallback now requires longer stable silence and stronger transcript content before forcing PROCESSING.
- Added short-term dedupe for repeated fallback transcript snippets to reduce looped responses on noisy/partial speech.
- Updated runbook note in `docs/RUN_EVERYTHING.md` to clarify safe idempotent behavior when `core`/`gui` is already running.
- Re-ran full-cycle startup and focused tests (`test_voice_engine`, `test_conversation_fsm`, `simple_voice_test`).

**Why:** Runtime logs showed STT capture working but frequent low-content silence fallback commits causing repetitive responses and unstable interaction flow.

**Affects:** conversation/fsm.py, docs/RUN_EVERYTHING.md, MEMORY_LOG.md.

---

## 2026-02-27 — Temporarily neutralized persona intensity

**Changed:** Updated `config.yaml` persona dimensions to neutral values (`curiosity`, `warmth`, `directness`, `formality` set to `0.5`, `humor` reduced to `0.2`) and set `evolution_rate` to `0.0` to pause personality drift.

**Why:** User requested to remove dominant personality behavior for now and make voice responses less forceful/repetitive.

**Affects:** config.yaml (`persona` section), MEMORY_LOG.md.

---

## 2026-02-27 — Prevent duplicate core startup port collisions

**Changed:** Updated `scripts/start-emily.sh` to detect already-running Emily core processes and bus port conflicts (`5555/5556`) before launching `core` or `gui`. Script now exits gracefully with actionable stop/retry instructions instead of allowing a `ZMQError: Address already in use`.

**Why:** Re-running `./scripts/start-emily.sh core` while Emily was already active caused startup crashes due to duplicate ZeroMQ binds.

**Affects:** scripts/start-emily.sh, MEMORY_LOG.md.

---

## 2026-02-27 — Fixed voice FSM response loop crash

**Changed:** Added missing `import contextlib` in `conversation/fsm.py` to prevent runtime `NameError` in the response generator cleanup path (`with contextlib.suppress(asyncio.CancelledError)`).

**Why:** During live voice-core runs, STT capture and utterance commits were working, but response handling repeatedly logged `response_loop_error: name 'contextlib' is not defined`, interrupting reliable turn completion.

**Affects:** conversation/fsm.py, MEMORY_LOG.md.

---

## 2026-02-27 — Fixed TabbyAPI startup in start script

**Changed:** Updated `scripts/start-emily.sh` TabbyAPI launcher to use correct CLI flags (`--model-dir`, `--model-name`, `--disable-auth true`), switched default model to local installed `Huihui-Qwen3-14B-abliterated-v2-exl2`, and added a preflight check for missing model `config.json`.

**Why:** TabbyAPI startup was timing out because the script used an invalid ambiguous argument and a model path/name combination that did not exist in the local model directory.

**Affects:** scripts/start-emily.sh, MEMORY_LOG.md.

---

## 2026-02-27 — Added full-stack run guide

**Changed:** Added `docs/RUN_EVERYTHING.md` with a single, direct workflow for starting, checking, and stopping the full Emily stack, plus partial-mode commands and recovery steps.

**Why:** User requested a dedicated Markdown file that clearly explains how to run everything without jumping across multiple docs.

**Affects:** docs/RUN_EVERYTHING.md, MEMORY_LOG.md.

---

## 2026-02-27 — Cursor skills and tooling boost

**Changed:** Added Cursor productivity assets for this repository: new skills `cursor-ops` and `cursor-extension-setup`, new always-on rule `.cursor/rules/cursor-tooling.mdc`, and extension baseline doc `.cursor/extensions/RECOMMENDED.md`.

**Why:** Improve Cursor agent behavior consistency and speed up onboarding by codifying reusable setup, extension guidance, and tooling standards in-project.

**Affects:** .cursor/skills/cursor-ops/SKILL.md, .cursor/skills/cursor-extension-setup/SKILL.md, .cursor/rules/cursor-tooling.mdc, .cursor/extensions/RECOMMENDED.md, MEMORY_LOG.md.

---

## 2026-02-22 — Cursor-only setup (AI.md, MCP, guide)

**Changed:** Added Cursor IDE setup only — no change to Emily application runtime. New files: `AI.md` (project intelligence for Cursor’s AI: overview, stack, schema, env, .cursorrules summary, gotchas); `.cursor/mcp.json` (MCP servers: filesystem scoped to repo, postgres optional, github, brave-search, memory, sequential-thinking, sentry); `docs/CURSOR-GUIDE.html` (reference guide: 9 LLM patterns, forbidden patterns, MCP table, master prompt, setup checklist).

**Why:** Plan to adopt Cursor setup for this workspace so Cursor’s AI has one “read first” doc and project-level MCP; guide kept in repo as reference. All of this is for the IDE only, not for the Emily app.

**Affects:** AI.md (new), .cursor/mcp.json (new), docs/CURSOR-GUIDE.html (new), MEMORY_LOG.md.

---

## 2026-02-22 — install-extensions.sh added

**Changed:** Added `install-extensions.sh` at project root. Script detects `cursor` or `code` in PATH and installs Python, Pylance, pytest, Markdown, YAML, GitLens, and EditorConfig extensions.

**Why:** User ran Cursor Agent installer then tried to run a missing install-extensions.sh; script did not exist in repo. Added so extension setup is one-command after cloning.

**Affects:** install-extensions.sh (new), MEMORY_LOG.md.

---

## 2026-02-22 — LlamaCpp/Ollama compatibility and Emily Editor

**Changed:** Desktop chat now supports both Ollama and LlamaCpp (GGUF) local models, and adds an Emily Editor for building system profiles.

- **Ollama discovery:** On startup (after DB init), controller runs `_discover_ollama_models()` which calls `OllamaProvider.discover_models()`, registers each with `register_dynamic_model("ollama-<name>", spec)`. Top bar `group_models()` builds a "LOCAL (Ollama)" section from all registry entries with `provider == "ollama"`.
- **LlamaCpp provider:** New `emily_chat/models/providers/llamacpp.py`: loads GGUF list from main config (`llm.llamacpp`), registers tiers and discovered `.gguf` files via `list_gguf_models()`. `LlamaCppProvider` implements `BaseProvider.stream()` using llama-cpp-python in a thread-pool executor. Provider factory and controller discovery added. Top bar shows "LOCAL (LlamaCpp)" from registry.
- **Profiles:** New `emily_chat/profiles.py`: roles (core, coding, research, writing, reasoning, fast), `EmilyProfile` (id, name, roles), `SKILL_TO_ROLE` mapping, load/save to `~/.emily-chat/profiles.json`. `AppSettings.active_profile_id` added.
- **Controller:** Model resolution uses `resolve_model_for_skill(profiles, active_profile_id, skill_id, fallback_model)` so the active profile’s role-for-skill selects the registry key; "auto" keeps existing auto-routing.
- **Emily Editor UI:** New `emily_chat/ui/emily_editor.py`: dialog with profile list (New, Duplicate, Delete), role→model dropdowns (same source as top bar), Apply (set active profile), Save (persist), "Export to voice config" (writes main config.yaml with backup, mapping profile roles to voice tiers and Ollama/llamacpp model ids). Top bar options menu entry "Emily Editor (Systems)" and signal `emily_editor_requested`; controller opens dialog on signal.

**Why:** Plan: make desktop compatible with llamacpp and ollama, and allow users to select among local models and construct Emily systems (e.g. Coding Emily with best coding Ollama model) via profiles and optional export to voice config.

**Affects:** emily_chat/controller.py, emily_chat/ui/top_bar.py, emily_chat/config.py, emily_chat/models/registry.py (use of register_dynamic_model), emily_chat/models/provider_factory.py, emily_chat/models/providers/llamacpp.py (new), emily_chat/profiles.py (new), emily_chat/ui/emily_editor.py (new), MEMORY_LOG.md.

---

## 2026-02-22 — gpu-cuda optional deps: resolvable with CUDA stack

**Changed:** `pyproject.toml` optional dependencies adjusted so `uv sync --extra gpu-cuda --extra desktop` resolves and installs a full CUDA stack (torch, torchaudio, faster-whisper, kokoro, llama-cpp-python, ctranslate2, nvidia-* libs). Removed from gpu-cuda: TTS (Coqui/XTTS — conflicts with networkx>=3.3), audiocraft/rvc-python (singing — conflicts with torchaudio>=2.3), deepface (pulls tensorflow, no Py3.13/3.14 wheels), openwakeword (pulls tflite-runtime, cp311-only). Those remain documented as manual installs or separate-venv if needed. Venv may be recreated with Python 3.13 when using gpu-cuda (uv can switch Python to satisfy constraints).

**Why:** User requested "use cuda"; previous sync failed due to audiocraft/torchaudio, TTS/networkx, tensorflow/tflite-runtime and Python 3.14. Making the main CUDA path resolvable ensures STT (faster-whisper), TTS (kokoro), llama-cpp, and desktop app work with GPU.

**Affects:** pyproject.toml, MEMORY_LOG.md.

---

## 2026-02-21 — Tier / backend / model alignment

**Changed:** Enforced the canonical tier table across config defaults, config.yaml, and docs. config.py: TierBackend defaults for nano and voice_fast set to "llamacpp" (others remain "ollama"). config.yaml: nano GGUF filename updated from qwen2.5-3b-instruct-q4_k_m.gguf to qwen3-4b-instruct-q4_k_m.gguf with a comment to place the file in models_dir. ARCHITECTURE.md: Attention Router and data flow now reference Qwen3-4B; model fleet table updated with Backend column and voice_fast row (llamacpp/ollama per tier). COGNITIVE_MODEL.md: Attention Router description updated from Phi-3-mini to Qwen3-4B. DECISIONS.md: LLM Backend section updated to state that nano and voice_fast default to llamacpp when enabled and GGUF present, others to Ollama, with fallback to Ollama if GGUF missing or llamacpp disabled. README.md: added "Model tiers and backends" subsection with the full 7-tier table (Tier, Model, Backend, Use case) and a note on the nano GGUF path.

**Why:** Single source of truth for tier → model → backend mapping (nano/voice_fast → qwen3:4b + llamacpp; fast/smart/reasoning/vision/embedding → ollama with qwen3:14b, qwq:latest, minicpm-v:latest, bge-m3).

**Affects:** config.py, config.yaml, ARCHITECTURE.md, COGNITIVE_MODEL.md, DECISIONS.md, README.md, MEMORY_LOG.md.

---

## 2026-02-21 — Security measures audit implementation

**Changed:** Implemented security improvements from the security audit plan.

- **API auth**: `api/auth.py` — Bearer token dependency; secret from `EMILY_API_SECRET` or `api.secret_key`. `.env` loaded at API startup. Middleware enforces auth and rate limiting; CORS is configurable via `api.cors_origins`. Request body size limit via `api.max_body_size_bytes`.
- **Rate limiting**: In-memory per-IP rate limit middleware (`api.rate_limit_requests` / `api.rate_limit_window_s`).
- **Sandbox**: `plugins/sandbox.py` — `_wrap_code()` now assigns restricted `__builtins__` so user code cannot use `__import__`, `open`, `exec`, etc., inside the sandboxed process.
- **Encryption**: `security/encryption.py` — `AgeEncryption(strict=True)` when `encrypt_at_rest` is true; no plaintext fallback; missing backend raises. `security/manager.py` — encryption key init failure on startup is fatal when encrypt_at_rest is true.
- **Audit log**: `security/audit_log.py` — `trim_retention_days(days)`; `SecurityConfig.audit_retention_days`; trim on SecurityManager start when set.
- **Dead man's switch**: `security/dead_man_switch.py` — `heartbeat_path` configurable via `SecurityConfig.dead_man_switch_heartbeat_path` (resolved to absolute at init).
- **Input validation**: Vault routes — `credential_id` path param validated as UUID; Pydantic `max_length` on vault request body fields; global max body size middleware.
- **Docs**: THREAT_MODEL.md checklist updated; README Security section and dependency audit note (`pip-audit`); config `APIConfig` extended with `cors_origins`, `rate_limit_*`, `max_body_size_bytes`; `SecurityConfig` with `audit_retention_days`, `dead_man_switch_heartbeat_path`.

**Why:** Align implementation with threat model (API auth, rate limiting, no plaintext encryption fallback, audit retention, stable heartbeat path, input validation) and document dependency scanning.

**Affects:** api/app.py, api/auth.py, api/routes/vault.py, config.py, security/encryption.py, security/manager.py, security/audit_log.py, security/dead_man_switch.py, plugins/sandbox.py, THREAT_MODEL.md, README.md, MEMORY_LOG.md. New tests: tests/unit/test_api_auth.py, tests/unit/test_sandbox.py.

---

## 2026-02-20 — Phase 1: Project Scaffold

**Changed:** Full project directory structure created. Core infrastructure implemented:
- `config.py` — Pydantic Settings v2, YAML + env var loading
- `config.yaml` — all runtime configuration with Emily-specific values
- `core/bus.py` — ZeroMQ PerceptionBus (PUSH/PULL) and AgentBus (PUSH/PULL + handler registry)
- `core/fsm.py` — SystemFSM with 8 states, validated transitions, async observer pattern
- `core/scheduler.py` — Priority queue scheduler with per-tier concurrency caps
- `core/bootstrap.py` — Composition root, startup/shutdown lifecycle management
- `observability/logger.py` — structlog configuration, JSON + console renderers
- `observability/metrics.py` — Prometheus counters, histograms, gauges for all subsystems
- `observability/tracing.py` — OpenTelemetry setup with OTLP export + in-memory fallback
- `main.py` — CLI entry point
- All four architecture documents: ARCHITECTURE.md, DECISIONS.md, COGNITIVE_MODEL.md, THREAT_MODEL.md
- `pyproject.toml` — uv-managed, all dependency groups (base, gpu-cuda, cpu-only, dev)

**Why:** Phase 1 deliverable — all modules must be importable with consistent config, logging, and observability before any feature work begins.

**Affects:** All future phases depend on these foundations.

---

## 2026-02-20 — Cognitive Knowledge OS: Phases 1–9

**Changed:** Full personal knowledge OS and encrypted credential vault integrated into Emily.

- `scripts/migrations/001_knowledge_schema.py` — SQLite migration for knowledge.db (entities, people, relationships, facts, events)
- `memory/knowledge_models.py` — dataclasses for all 5 knowledge table types
- `memory/knowledge_store.py` — async SQLite CRUD (self-bootstrapping via connect())
- `memory/semantic/knowledge_vectors.py` — 4 new Qdrant collections (emily_entities, emily_facts, emily_events, emily_knowledge) with importance scoring
- `memory/query_engine.py` — unified NL query router across SQLite + Qdrant + NetworkX + Vault (metadata only)
- `extraction/` — entity extractor (LLM NER), relation extractor, Jaro-Winkler deduplicator, pipeline orchestrator
- `security/vault/` — Argon2id KDF + AES-256-GCM vault: models, crypto, TOTP, health checker, CredentialVault class
- `ingestion/` — coordinator + parsers for vCard, iCal, PDF, conversation transcripts
- `proactive/engine.py` — birthday alerts, upcoming events, credential health, relationship drift, contradiction detection
- `api/routes/` — people, vault (auth-gated, display-only), query, graph REST endpoints
- `ui/terminal/knowledge_view.py` — Textual TUI with 5 tabs (People, Facts, Events, Vault, Alerts)
- `llm/prompt_builder.py` — 3 new prompt builders for entity extraction, relation extraction, query classification
- `config.py` — KnowledgeStoreConfig, VaultConfig
- New deps: argon2-cffi, pyotp, vobject, icalendar

**Why:** Implements the full personal knowledge OS — entities, relationships, encrypted credentials (local Bitwarden-style), proactive intelligence — integrated into Emily's existing cognitive architecture. Secrets never enter LLM context, TTS, or logs. 73/73 unit tests pass.

**Affects:** memory/, security/, extraction/, ingestion/, proactive/, api/routes/, ui/terminal/, llm/prompt_builder.py, config.py

---

## 2026-02-20 — Voice Pipeline Wiring + Audio Device Selection

**Changed:**
- `core/bootstrap.py` — Wired AudioPipeline (mic→VAD→STT), TTSManager, AudioOutputStream, and a perception→TTS bridge into the main startup sequence. Emily now listens via microphone, transcribes with Faster Whisper, sends to LLM (fast model), and speaks the response via TTS. Background tasks handle model loading and the event bridge.
- `config.py` — Added `output_device: str | None` to `AudioConfig` for speaker selection.
- `config.yaml` — Added `output_device: null` to audio section.
- `core/fsm.py` — Added IDLE→PROCESSING transition to support text input bypassing LISTENING state.
- `api/routes/audio.py` — New API router: list audio devices, get/set input/output device, voice pipeline status, TTS test endpoint.
- `api/app.py` — Registered audio routes, added "Voice & Audio" page to dashboard with mic/speaker dropdowns, device table, TTS test button, pipeline status cards.

**Why:** The voice stack components (AudioPipeline, STT, TTS, VAD, wake word) were all implemented but never wired into Bootstrap or exposed via API/UI. This change connects them end-to-end so Emily can hear, think, and speak. Audio device selection lets the user pick their microphone and speakers from the web dashboard.

**Affects:** core/bootstrap.py, core/fsm.py, config.py, config.yaml, api/app.py, api/routes/audio.py

---

## 2026-02-20 — Voice/Provider Selection + Chat-Voice Integration

**What changed:**
- `api/routes/audio.py` — Added `/audio/voice/voices` (list TTS voices by provider), `/audio/voice/settings` GET/PUT (read/update provider & voice), and updated `/audio/voice/test-tts` to respect selected provider. Added `tts_voice` and `tts_provider` to shared state.
- `api/app.py` — Added TTS Provider and Voice dropdown cards to Voice & Audio page. Added "Speak responses" toggle button (speaker icon) to the chat input bar — when ON, Emily speaks her text chat responses via TTS. Added voice transcript SSE endpoint (`/chat/voice-transcript`) that tails `logs/voice_transcript.jsonl` to stream voice pipeline conversations into the chat panel. Dashboard JS connects to the SSE on init; voice messages appear in chat with a "voice" badge.
- `core/bootstrap.py` — `_perception_tts_bridge` now writes both user (STT) and Emily (LLM response) transcripts to `logs/voice_transcript.jsonl` so the web UI can display voice conversations.

**Why:** Users needed quick voice and provider switching without editing config files, and voice conversations were invisible in the chat UI. The speak toggle bridges text chat → voice output, and the transcript SSE bridges voice pipeline → chat display.

**Affects:** api/routes/audio.py, api/app.py, core/bootstrap.py, MEMORY_LOG.md

---

## 2026-02-20 — Full-Duplex Voice Engine Implementation

**What changed:**
- Created 4 design documents: VOICE_ARCHITECTURE.md, TIMING_MODEL.md, PSYCHOACOUSTICS_MODEL.md, SIGNAL_FLOW.md
- `perception/audio/capture.py` — Full-duplex audio capture engine with independent input/output streams, ring buffers, SCHED_FIFO real-time priority, AEC reference loopback
- `perception/audio/aec.py` — Acoustic echo cancellation with NLMS adaptive filter, double-talk detection, spectral subtraction fallback, session calibration
- `perception/audio/noise_suppress.py` — Two-stage noise suppression: noisereduce (CPU) + DeepFilterNet (GPU), with speech feature protection (breaths, hesitations, emotion preserved)
- `perception/audio/speaker_engine.py` — Speaker diarization (pyannote 3.1) + voiceprint enrollment (ECAPA-TDNN via SpeechBrain), 2-speaker tracking
- `perception/audio/streaming_stt.py` — Streaming STT with partial hypothesis tracking, committed/speculative word buffers, emotion marker detection
- `perception/audio/prosody_analyzer.py` — Continuous prosody extraction: F0 (parselmouth), energy, rate, voice quality, final lengthening, glottalization, per-speaker baselines
- `perception/audio/emotion_detector.py` — 10-category speech emotion recognition from prosody + lexical cues, with valence/arousal/cognitive-load dimensions
- `conversation/__init__.py`, `conversation/turn_detector.py` — 14-signal turn detection fusion engine (acoustic + linguistic + contextual), weighted scoring, 0.85 response threshold
- `conversation/fsm.py` — Master conversation state machine (IDLE/LISTENING/BACKCHANNELING/PROCESSING/FILLING/SPEAKING/INTERRUPTED) with concurrent async loops at 100Hz
- `conversation/interrupt_handler.py` — 6 interrupt types with graceful trail-off, word-boundary detection, acknowledgment generation, context preservation for resumption
- `conversation/backchannel.py` — 6 backchannel types (continuer/acknowledgment/agreement/empathy/surprise/completion), timing rules, volume control, token diversity
- `conversation/rhythm_sync.py` — Rhythm entrainment engine (0.4 degree), tracks user speaking rate/pauses/response latency, cross-session profile export/import
- `conversation/emotion_sync.py` — Emotion adaptation: mirror positive, calm negative, never amplify negative, drives TTS style parameters + LLM instructions
- `conversation/voice_engine.py` — Top-level bootstrap integration, creates and wires all modules, replaces linear _perception_tts_bridge
- `voice/filler_engine.py` — Pre-rendered thinking sounds (4 categories), crossfade blending, 5-minute cooldown, synthetic fallbacks
- `voice/breath_injector.py` — Breath sound injection at natural locations, 6 breath types, synthetic generation, 15-25s micro-breath intervals
- `voice/prosody_planner.py` — Full prosody planning for TTS: questions/lists/emphasis/parentheticals/technical/emotional content, per-sentence parameters
- `llm/orchestrator.py` — Streaming LLM with interrupt awareness, emotion/style-driven system prompts, speculative pre-generation
- `llm/speculative.py` — Speculative generation cache with edit-distance divergence checking (20% threshold)
- `timing/__init__.py`, `timing/latency_budget.py` — Per-stage latency enforcement with timeout + fallback cascade, auto-disable after 3 violations in 60s
- `timing/metrics.py` — Prometheus histograms/counters for all voice engine stages, turn detections, backchannels, interrupts, perceived latency
- `config.py` — Added VoiceEngineConfig with all voice engine parameters
- `config.yaml` — Added voice_engine section with full configuration

**Why:** Transform Emily from a half-duplex walkie-talkie into a full-duplex conversational presence. The new voice engine runs input and output simultaneously, detects turn completion via 14 fused signals instead of fixed silence timers, generates backchannels while the user speaks, breathes between sentences, trails off gracefully when interrupted, and synchronizes speech rhythm to the user.

**Affects:** All new files listed above, plus config.py, config.yaml. The existing audio pipeline, TTS, STT, and output stream remain as fallbacks. The voice engine is opt-in via config.yaml voice_engine.enabled.

---

## 2026-02-20 — Voice Quality Improvements

**What changed:**

1. **`voice/output_stream.py`** — Rewrote from scratch. The old version buffered ALL audio chunks before playing anything. New version uses a producer/consumer queue: each chunk is decoded, normalized, and played immediately as it arrives. Added `normalize_audio()` to prevent volume jumps between sentences and engines.

2. **`voice/prosody.py`** — Fixed scoping bug: `pause_after_ms` was only defined inside one `elif` branch but the fallback used `"pause_after_ms" in dir()` which is unreliable. Rewrote with:
   - Proper `pause_after_ms` for every sentence type (questions: 350ms, exclamations: 250ms, trailing: 500ms, colons: 300ms, lists: 150ms)
   - Parenthetical detection (slower, quieter)
   - Emphasis/hedging word detection (modulates energy + pitch)
   - Sentence position tracking with `reset_position()` — first sentence gets 5% energy boost, long responses taper naturally
   - Abbreviation-aware sentence splitting (Dr., Mr., etc. no longer cause false splits)

3. **`llm/streaming.py`** — Major improvements:
   - Lowered `tts_chunk_min_chars` default from 80 to 40 (reduces first-audio latency)
   - Added `clean_for_tts()` that strips markdown bold/italic, code blocks, headings, links, images, URLs, bullets, and numbered lists before sending to TTS
   - Replaced naive regex sentence boundary detection with `_is_sentence_boundary()` that understands abbreviations, decimal numbers, and single-letter initials

4. **`voice/tts.py`** — Per-sentence prosody and streaming improvements:
   - `TTSManager.speak()` now splits text into sentences and computes prosody independently for each
   - Kokoro engine now synthesizes per-sentence instead of sending the whole text at once (faster first-audio)
   - Added `crossfade()` utility for smooth transitions between audio segments
   - Added inter-sentence silence insertion based on prosody `pause_before_ms`
   - Audio clipping protection in Kokoro (`np.clip` before int16 conversion)

5. **`core/bootstrap.py`** — Wired VoiceEngine into the startup sequence:
   - If `voice_engine.enabled` is true and the module is importable, starts `VoiceEngine` instead of the legacy bridge
   - Falls back to legacy bridge if voice engine fails to start
   - Legacy bridge upgraded: uses streaming LLM → sentence chunking → per-sentence TTS instead of waiting for full LLM response
   - Added `voice_engine_instance` cleanup in `shutdown()`

**Why:** The old pipeline had several quality problems: audio was fully buffered before playback (defeating "streaming"), prosody was computed once for the entire response instead of per-sentence, Kokoro synthesized the entire text in one pass, markdown artifacts were spoken aloud, and the sentence splitter broke on common abbreviations.

**Affects:** `voice/output_stream.py`, `voice/prosody.py`, `voice/tts.py`, `llm/streaming.py`, `core/bootstrap.py`. All 55 existing unit tests pass.

---

## 2026-02-20 — Switch to New Voice Engine Mode

**What changed:**

1. **`core/bootstrap.py`** — When `voice_engine.enabled` is true, the old `AudioPipeline` is no longer started (it would open a competing mic stream that fights the new `AudioCaptureEngine`). Only TTS is loaded (shared by both modes). Added `_wire_api_voice_state()` to inject voice engine refs into API route modules at startup. On voice engine failure, falls back to legacy bridge automatically.

2. **`api/routes/audio.py`** — `VoiceStatusResponse` now reports `voice_mode` ("full_duplex" or "legacy"), `fsm_state`, and `modules_loaded`. The `set_audio_state()` function accepts `voice_engine` parameter. Input device switching now works with both the new `AudioCaptureEngine` (via voice engine modules) and the old `AudioPipeline`. Status endpoint auto-detects which mode is active.

3. **`api/app.py`** — Included `voice_engine_routes.router` so the `/voice-engine/*` endpoints (status, turn-signal, emotion, rhythm, latency, stats) are now live. Lifespan creates a `VoiceEngine` instance when running standalone (without bootstrap). Config dump now includes `voice_engine` section. Dashboard Voice & Audio panel updated: shows "FULL-DUPLEX" / "LEGACY" mode badge, conversation FSM state, and loaded module list.

4. **`api/routes/voice_engine.py`** — No code changes; was already correct but previously unreachable because the router was not included in `api/app.py`.

**Why:** The voice engine was fully implemented but not wired into the system. Bootstrap still started the old AudioPipeline even when voice engine was enabled (creating two competing mic streams). The API had no way to report voice engine status or control it. The dashboard Voice panel only showed legacy pipeline fields.

**Affects:** `core/bootstrap.py`, `api/routes/audio.py`, `api/app.py`. The old `AudioPipeline` + bridge remain as fallback when `voice_engine.enabled: false`. All 55 unit tests pass.

---

## 2026-02-20 — Fix TTS crash (Python 3.14 regex) and chat space stripping

**What changed:**
1. `voice/prosody.py`: Replaced `r"\1\x00\2"` replacement string in `re.sub()` with a lambda — Python 3.14's `re` module rejects `\x` in replacement strings, causing `PatternError: bad escape \x at position 2` on every TTS call.
2. `voice/tts.py`: Added `strip_emojis_token()` — a streaming-safe variant that removes only emoji characters without calling `.strip()`, so space-only tokens survive SSE streaming.
3. `api/app.py`: Streaming chat endpoint (`/chat/stream`) now uses `strip_emojis_token` instead of `strip_emojis` to preserve whitespace between words.

**Why:** TTS was completely non-functional (every `speak()` call crashed at sentence splitting). Chat text was rendered without any spaces because `.strip()` on individual streaming tokens destroyed space-only tokens.

**Affects:** `voice/prosody.py`, `voice/tts.py`, `api/app.py`. Server restarted to apply.

---

## 2026-02-20 — Emily Chat Desktop App: Phase 1 — App Shell

**Changed:** Created the `emily_chat/` subdirectory with the full Phase 1 desktop application shell:

- `emily_chat/__init__.py` — Package marker with version string.
- `emily_chat/config.py` — `AppSettings` (Pydantic BaseModel) with JSON persistence to `~/.emily-chat/settings.json`. Stores window geometry, panel widths, theme, font size.
- `emily_chat/main.py` — Entry point: creates QApplication, loads bundled Inter + JetBrains Mono fonts, applies theme, creates MainWindow + SystemTrayManager.
- `emily_chat/app.py` — Thin bootstrap wrapper around `main()`.
- `emily_chat/ui/custom_titlebar.py` — `CustomTitleBar`: frameless title bar with drag-to-move, double-click maximize/restore, styled minimize/maximize/close buttons. Zero hardcoded colours.
- `emily_chat/ui/main_window.py` — `MainWindow(QMainWindow)`: frameless window with 8-edge resize hit-testing, three-panel `QSplitter` (left sidebar, center chat, right panel), geometry + panel size persistence on close/restore, `Ctrl+Shift+E` toggle shortcut, tray-aware close event.
- `emily_chat/ui/theme_engine.py` — `ThemeEngine`: loads `.qss` files, performs `@variable` token substitution from per-theme palettes, instant theme switch via `app.setStyleSheet()`.
- `emily_chat/ui/system_tray.py` — `SystemTrayManager(QSystemTrayIcon)`: tray icon with context menu (Show/Hide, Quit), left-click toggle, first-minimize balloon notification.
- `emily_chat/assets/themes/dark.qss` — Full dark theme matching spec colours (background #0a0a0f, surface #111118, accent #7c6af7, etc.). Styles for all core widget types + scrollbars + menus + tooltips.
- `emily_chat/assets/themes/light.qss` — Light theme with white backgrounds, same accent purple.
- `emily_chat/assets/fonts/` — Bundled Inter (Regular/Medium/SemiBold/Bold) and JetBrains Mono (Regular/Bold) TTFs.
- `emily_chat/assets/icons/emily_avatar.png` — Placeholder purple-circle icon with white "E".
- `pyproject.toml` — Added `desktop` optional dependency group (`PySide6>=6.7`) and `emily-chat` script entry point.

**Why:** Phase 1 deliverable for the Emily Chat desktop app (per `deskto_app.md` spec). Establishes the PySide6 application shell, frameless chrome, theme system, system tray integration, and three-panel layout as the foundation for all subsequent desktop UI phases.

**Affects:** New `emily_chat/` directory (self-contained, no changes to existing Emily1.0 modules). `pyproject.toml` updated with desktop deps and script entry.

---

## 2026-02-20 — Phase 2-3: Left Sidebar + Chat Database

**Changed:**

- `emily_chat/storage/__init__.py` — Package marker for the storage layer.
- `emily_chat/storage/models.py` — Pydantic models: `ConversationSummary`, `Message`, `SearchResult`.
- `emily_chat/storage/database.py` — `ConversationDatabase`: async SQLite via `aiosqlite`, auto-migration, CRUD for conversations/messages, FTS5 full-text search, duplicate/fork operations, aggregate counters. DB path: `~/.emily-chat/conversations.db`.
- `emily_chat/storage/migrations/001_initial.sql` — Schema: `conversations`, `messages`, `messages_fts` (FTS5 virtual table with sync triggers), `skills`, `settings`, `schema_version` tables.
- `emily_chat/ui/left_sidebar.py` — `LeftSidebar` widget: search bar with 150ms debounce, date-grouped conversation list (PINNED/TODAY/YESTERDAY/THIS WEEK/THIS MONTH/older), `ConversationItemWidget` with provider colour dot, relative time, hover actions, right-click context menu (Rename, Pin, Duplicate, Fork, Export, Archive, Delete with 5s undo timer), `SkillsSection` with 12 built-in skills, footer with Settings button. Pure functions `group_conversations()` and `relative_time()` extracted for testability.
- `emily_chat/ui/async_bridge.py` — `AsyncRunner(QThread)`: background asyncio event loop for non-blocking database calls from the Qt main thread, with token-based result/error delivery via signals.
- `emily_chat/config.py` — Added `last_conversation_id` and `sidebar_collapsed_groups` settings.
- `tests/unit/test_chat_database.py` — 12 tests: CRUD, FTS5 search, pin/unpin, archive, duplicate, fork.
- `tests/unit/test_left_sidebar.py` — 15 tests: date grouping, relative time formatting, provider colour map.

**Why:** Phase 2 (sidebar) requires Phase 3 (database) to display real conversations. Combined into one delivery so the sidebar is functional end-to-end.

**Affects:** `MainWindow` will import `LeftSidebar` and `ConversationDatabase`; all future UI phases depend on the storage layer.

---

## 2026-02-20 — Phase 5: Anthropic Provider — Claude 4.5 Streaming + Extended Thinking

**Changed:**

Part A — Provider layer and streaming infrastructure:
- `emily_chat/models/__init__.py` — Package init, re-exports core types.
- `emily_chat/models/base.py` — `StreamChunk` (thinking/text/usage/stop), `ModelSpec`, `GenerationSettings`, `BaseProvider` ABC with `async stream()` and `validate_key()`.
- `emily_chat/models/registry.py` — `EMILY_MODEL_REGISTRY` with three Anthropic models (Opus, Sonnet ★ default, Haiku); `get_model()`, `get_default_model()`, `list_models()`.
- `emily_chat/models/providers/anthropic.py` — `AnthropicProvider`: lazy `AsyncAnthropic` client, streams via `client.messages.stream()`, extracts `thinking_delta` and `text_delta` content blocks, reports usage, supports extended thinking via `thinking.budget_tokens`.
- `emily_chat/models/streaming_engine.py` — `StreamingEngine`: resolves provider from `ModelSpec`, applies Emily persona filter to text (not thinking), tracks `first_token_ms`/`latency_ms`/`cost_usd`, supports `asyncio.Event` interrupt for stop button.
- `emily_chat/ui/async_bridge.py` — Added `submit_streaming()` for async iterator support, `chunk_received` and `stream_done` signals, `cancel_stream()`.
- `pyproject.toml` — Added `anthropic>=0.40.0` to `desktop` optional dependencies.
- `tests/unit/test_anthropic_provider.py` — 15 tests: registry lookups, thinking/text/usage/stop chunk emission, chunk ordering, no-key error, persona filter application, timing metadata, interrupt handling.

Part B — UI integration:
- `emily_chat/ui/right_panel.py` — `RightPanel` with `_ThinkingSection` (monospace live-streaming text area with timer) and `_MetadataSection` (model, tokens, cost, latency fields). Public slots: `append_thinking()`, `set_metadata()`, `finish_thinking()`, `clear()`.
- `emily_chat/ui/conversation_stream.py` — `ConversationStream(QScrollArea)` with `_UserBubble` (right-aligned), `_EmilyBubble` (left-aligned, streaming), `_EmptyState`, auto-scroll with pause-on-scroll-up. API: `append_user_message()`, `start_emily_message()`, `append_emily_text()`, `finish_emily_message()`, `load_messages()`.
- `emily_chat/ui/input_panel.py` — `InputPanel` with `_AutoTextEdit` (auto-expanding 1–10 lines, Enter sends, Shift+Enter newline), send button (greyed when empty), stop button (visible during generation). Signals: `message_submitted(str)`, `stop_requested()`.
- `emily_chat/ui/main_window.py` — Replaced placeholder panels with real `ConversationStream` + `InputPanel` (centre) and `RightPanel` (right). Added `conversation_stream`, `input_panel`, `right_panel` properties.
- `emily_chat/controller.py` — Full rewrite: owns `EmilyPersonaEngine`, `StreamingEngine`, wires `InputPanel.message_submitted` → save user message → build system prompt (identity + skill + privacy + session context) → `StreamingEngine.stream()` via `AsyncRunner.submit_streaming()` → route thinking to `RightPanel`, text to `ConversationStream`, identity-filtered → save assistant message with full metadata to DB. Handles stop via interrupt event. Auto-creates conversation on first message.
- `emily_chat/config.py` — Added `default_model: str = "claude-sonnet-4-5"` and `active_skill_id: str = "normal"`.
- `emily_chat/main.py` — Updated `ChatController` construction to pass all four panel refs.
- `emily_chat/assets/themes/dark.qss` + `light.qss` — QSS styles for conversation bubbles, input panel, right panel thinking/metadata sections, empty state.

**Why:** Phase 5 deliverable — first LLM provider (Anthropic Claude 4.5) with extended thinking support. Thinking tokens stream live to the right panel, response text streams to the chat panel, messages are saved to SQLite with full metadata (tokens, cost, latency). All 42 desktop unit tests pass (15 new + 27 existing).

**Affects:** `emily_chat/models/`, `emily_chat/ui/right_panel.py`, `emily_chat/ui/conversation_stream.py`, `emily_chat/ui/input_panel.py`, `emily_chat/ui/main_window.py`, `emily_chat/ui/async_bridge.py`, `emily_chat/controller.py`, `emily_chat/config.py`, `emily_chat/main.py`, `pyproject.toml`, `tests/unit/test_anthropic_provider.py`. All future provider phases (6–9) extend `BaseProvider` and register in `streaming_engine._PROVIDERS`. All future UI phases (10–18) extend the widgets created here.

---

## 2026-02-20 — Phase 6: OpenAI Provider — GPT-5 Series + o3/o4 Reasoning

**Changed:**

- `emily_chat/models/` — New package: `__init__.py`, `providers/__init__.py`.
- `emily_chat/models/providers/base.py` — `BaseProvider` ABC defining the contract all providers implement: `stream()` (async iterator of `StreamChunk`), `validate_key()`, `supports_thinking()`, `supports_vision()`, `close()`.
- `emily_chat/models/registry.py` — `ModelSpec` frozen dataclass + `EMILY_MODEL_REGISTRY` with 5 OpenAI entries: `gpt-5-2` ($15/$60, 256k ctx), `gpt-5` ($8/$32, 256k ctx), `gpt-4o` ($2.5/$10, 128k ctx), `o3` ($10/$40, 200k ctx, thinking+reasoning_effort), `o4-mini` ($1.10/$4.40, 200k ctx, thinking+reasoning_effort). Helpers: `get_model()`, `get_models_for_provider()`, `get_default_model()`.
- `emily_chat/models/streaming_engine.py` — `ChunkType` enum, `StreamChunk` dataclass, `GenerationSettings` (temperature, max_tokens, reasoning_effort, thinking_budget), `UsageStats`, `EmilyStreamingEngine` with callback-based `stream()` that applies `EmilyResponseFilter` to text chunks (thinking exempt), tracks timing/usage, supports interrupt.
- `emily_chat/models/cost_tracker.py` — `estimate_cost()` (thinking tokens billed at output rate) and `format_cost()`.
- `emily_chat/models/token_counter.py` — tiktoken-based `count_tokens()` and `count_messages()` for OpenAI models.
- `emily_chat/models/providers/openai.py` — `OpenAIProvider(BaseProvider)`: direct httpx SSE streaming (no openai SDK). GPT-5 series: `delta.content` → text chunks with temperature. o-series (o3, o4-mini): `delta.reasoning_content` → thinking chunks, `reasoning_effort` param, temperature omitted. Vision via `build_vision_message()`. Usage extraction including `completion_tokens_details.reasoning_tokens`. Key validation via `/v1/models`.
- `emily_chat/controller.py` — Fixed imports to use actual module paths (`streaming_engine` not `base`), `EmilyStreamingEngine` not `StreamingEngine`, `chunk.metadata` not `chunk.usage`, proper `get_default_model()` tuple unpacking.
- `tests/unit/test_openai_provider.py` — 36 tests across 8 classes: `_is_reasoning_model` detection, SSE line parsing, GPT-5 text streaming + request body verification, o3/o4-mini reasoning separation + reasoning_effort forwarding + usage extraction, vision message building, key validation, cost tracking, streaming engine identity filter integration + interrupt + error handling.

**Why:** Phase 6 deliverable — OpenAI provider with full GPT-5 series + o3/o4 reasoning support. Reasoning chunks correctly separated into thinking vs text for the right-panel display. No new dependencies (uses httpx already in deps). All 36 tests pass.

**Affects:** `emily_chat/models/` (new package), `emily_chat/controller.py`, `tests/unit/test_openai_provider.py`. Future providers (Anthropic, Google, Groq, etc.) extend `BaseProvider` and add entries to `EMILY_MODEL_REGISTRY`. The streaming engine, persona filter, and UI handle all providers identically via the `StreamChunk` interface.

---

## 2026-02-20 — Phase 7: Google Provider — Gemini 3 Streaming + Thinking Extraction

**Changed:**

- `emily_chat/models/providers/google.py` — New `GoogleProvider(BaseProvider)`: direct httpx SSE streaming against `generativelanguage.googleapis.com/v1beta`. Uses `alt=sse` query parameter for SSE format. System prompt via `systemInstruction` field (not a message). Thinking enabled via `thinkingConfig` in `generationConfig` when `settings.thinking_budget > 0` — sets `thinkingBudget` and `includeThoughts: true`. Thought parts identified by `part.thought == true` boolean flag on candidate content parts. Conversation role mapping: `assistant` → `model`, `system` messages skipped (handled via `systemInstruction`). Usage extracted from `usageMetadata` fields: `promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`. Key validation via `/models` list endpoint.
- `emily_chat/models/registry.py` — Added 3 Google Gemini models: `gemini-3-pro` (gemini-3-pro-preview, 2M context, thinking + vision + video + audio, $2.50/$15.00, tier "best-multimodal"), `gemini-3-flash` (gemini-3-flash, 1M context, thinking + vision, $0.10/$0.40, tier "excellent"), `gemini-2-5-pro` (gemini-2.5-pro-preview, 1M context, thinking + vision, $1.25/$10.00, tier "very-good").
- `emily_chat/models/providers/__init__.py` — Updated docstring listing all three implemented providers.
- `tests/unit/test_google_provider.py` — 40 tests across 9 classes: message conversion (role mapping, system skip, multi-turn), SSE parsing (text/thinking/usage/mixed parts, edge cases), registry (3 models, specs, thinking flag, pricing), text streaming (full stream, stop chunk, usage chunk, request body structure, API errors), thinking streaming (separation, budget forwarding, budget=0 omits config, thinking token usage), key validation, cost tracking, streaming engine integration (identity filter on text, thinking exempted, interrupt, error routing), multi-model (flash + 2.5-pro streaming).

**Why:** Phase 7 deliverable — third LLM provider (Google Gemini 3 series + 2.5 Pro). Thinking parts stream to the right panel, text parts stream to the chat panel with Emily identity filter applied. No new dependencies (uses httpx already in deps, same as OpenAI provider). All 40 new tests pass, all 36 existing OpenAI tests pass.

**Affects:** `emily_chat/models/providers/google.py`, `emily_chat/models/registry.py`, `emily_chat/models/providers/__init__.py`, `tests/unit/test_google_provider.py`. Future provider phases (8–9) follow the same pattern. The streaming engine, persona filter, and UI handle Google chunks identically to OpenAI — no UI changes needed.

---

## 2026-02-20 — Phase 9: OpenRouter Pass-Through + Ollama Auto-Discovery

**Changed:**
- `emily_chat/models/providers/openrouter.py` — New provider extending `OpenAICompatibleProvider`. Adds OpenRouter-required `HTTP-Referer` and `X-Title` attribution headers. Think-tag detection for Kimi K2, GLM 4.7, DeepSeek R1, Qwen3, QwQ model patterns via substring matching. Static `create_custom_spec()` factory for user-specified arbitrary model strings.
- `emily_chat/models/providers/ollama.py` — New provider extending `BaseProvider` directly (Ollama uses JSON-per-line streaming, not SSE). Implements `stream()` parsing `{"message":{"content":"..."}, "done":false}` lines, `validate_key()` as a connectivity check (no auth), `discover_models()` for auto-discovering locally installed models via `GET /api/tags`, and think-tag extraction via `ThinkTagExtractor` for local DeepSeek R1 / Qwen3 / QwQ models. Static `create_local_spec()` factory with zero-cost pricing.
- `emily_chat/models/registry.py` — Added 3 new `ModelSpec` entries: `kimi-k2-thinking` (openrouter, 200K context, thinking, $0.85/$2.50), `glm-4-7-thinking` (openrouter, 128K context, thinking, $0.50/$1.50, MIT), `ollama-local` (ollama, placeholder, $0/$0). Added `register_dynamic_model()` helper for runtime registration of discovered/custom models.
- `emily_chat/models/providers/__init__.py` — Added `OpenRouterProvider` and `OllamaProvider` to exports.
- `tests/unit/test_openrouter_provider.py` — 18 tests covering: registry entries, SSE streaming, usage chunks, think-tag separation (Kimi K2, GLM 4.7), think-tag detection for various model patterns, attribution header verification, custom spec factory, error handling, key validation.
- `tests/unit/test_ollama_provider.py` — 24 tests covering: registry entry, dynamic registration, JSON-line streaming, usage/stop emission, request body format, think-tag separation (DeepSeek R1, Qwen3), think-tag detection, model discovery (populated/empty/unreachable), connectivity checks, API errors, connect errors, local spec factory (thinking/non-thinking/no-colon).

**Why:** Phase 9 deliverable — OpenRouter enables access to 300+ models via a single API key with any model string, and Ollama enables 100% local/private inference with auto-discovery. Both reuse `ThinkTagExtractor` from `_openai_compat.py`. No new dependencies (both use httpx). All 42 new tests pass, all existing tests unaffected.

**Affects:** `emily_chat/models/providers/openrouter.py`, `emily_chat/models/providers/ollama.py`, `emily_chat/models/registry.py`, `emily_chat/models/providers/__init__.py`, test files. The registry now has 23 static `ModelSpec` entries across 9 providers. Dynamic registration enables Ollama auto-discovered models and OpenRouter custom models to be added at runtime.

---

### 2026-02-20 — Replaced Chat Interface with Voice Mode Panel in Dashboard

**What changed:** Removed the Chat panel (sidebar nav, HTML, CSS, JS state/methods) from the Emily web dashboard at `api/app.py` and replaced it with a dedicated Voice Mode panel. The chat interface is redundant because the standalone desktop app (`emily_chat/`) already provides a full text chat experience.

**New Voice Mode panel includes:**
- Hero section with animated FSM state orb (color-coded: idle/listening/processing/responding/error) and pipeline status
- TTS/STT readiness cards plus backchannel and interrupt counters
- Live voice transcript fed by the existing `/chat/voice-transcript` SSE endpoint (with timestamps, role styling, auto-scroll, 200-entry cap, clear button)
- Quick controls bar with mic/speaker device selection, Test Speaker, and Preview Voice buttons
- Real-time telemetry grid (polling every 3s) showing: user emotion (valence/arousal/engagement/cognitive load gauges), turn detection signal (action + confidence breakdown), latency budget (per-stage P50/P95/P99 table), rhythm synchronization (user profile + Emily targets + entrainment)

**Backend endpoints preserved:** `/chat`, `/chat/stream`, `/chat/voice-transcript` remain untouched for the desktop app. New panel consumes existing `/voice-engine/*` and `/audio/voice/*` REST endpoints — no backend changes needed.

**Affects:** `api/app.py` (inline dashboard HTML/CSS/JS). No other files changed. The desktop app (`emily_chat/`) is unaffected.

---

## 2026-02-20 — Knowledge Recency Pipeline: RAG + Web Search + Temporal Awareness

**Changed:**

- `llm/prompt_builder.py` — Added `TEMPORAL AWARENESS` section to the system prompt with `{current_datetime}` placeholder, auto-filled from `datetime.now(UTC)`. The model now knows today's date and is explicitly instructed to use its knowledge base and web search before claiming ignorance about recent events. `get_system_prompt()` accepts an optional `current_datetime` parameter.
- `memory/manager.py` — Added `set_retriever()` and `retrieve_context(query, top_k)` methods. When a `HybridRetriever` is attached, the manager delegates semantic/RAG lookups; otherwise returns `[]` gracefully. Keeps agents decoupled from Qdrant internals.
- `llm/recency_detector.py` — New module. `needs_web_search(text)` uses regex heuristics to detect recency-sensitive queries: current-year references, recency keywords (latest, today, breaking, trending…), news keywords (announced, released, launched…), and explicit search intent (look up, google, search for…).
- `agents/conversation.py` — `_generate_response()` now calls `memory.retrieve_context()` for RAG chunks and `needs_web_search()` + `WebSearchTool.execute()` for live web results before assembling the prompt. Both are formatted via `build_rag_context_block()` and passed as `context_block` to `build_messages()`. Added `_run_web_search()` helper that normalises SearXNG results into the `{content, source, score}` format. `__init__` now accepts an optional `web_search: BaseTool` parameter.
- `plugins/registry.py` — `load_builtins()` now accepts `tool_kwargs: dict[str, dict[str, Any]]` for passing constructor arguments to specific tools. `_register_from_module()` uses per-tool kwargs, so `WebSearchTool` can receive `searxng_url` from `config.tools.web_search_url` instead of using the hardcoded default.
- `scripts/migrations/migrate_embeddings.py` — New standalone script for safely switching embedding models. Scrolls all 5 Qdrant collections, re-embeds text via Ollama, recreates collections with the new vector dimension, and re-inserts all points. Supports `--dry-run`.
- `tests/unit/test_recency_detector.py` — 14 parametrised tests for positive/negative recency detection.
- `tests/unit/test_prompt_builder_temporal.py` — 5 tests for datetime injection, temporal section presence, format placeholder safety.
- `tests/unit/test_conversation_rag.py` — 5 async tests verifying RAG context injection, web search triggering on recency queries, web search skipping on factual queries, graceful behaviour when web search tool is absent.

**Why:** Emily was telling users "I only have data up to 2023" despite having a full RAG system, knowledge base, and SearXNG web search tool — they were all implemented but never wired into the conversation pipeline. This change connects the existing retrieval infrastructure end-to-end so Emily automatically checks her knowledge base and searches the web for recency-sensitive queries before responding.

**Affects:** `llm/prompt_builder.py`, `memory/manager.py`, `agents/conversation.py`, `plugins/registry.py`, new files: `llm/recency_detector.py`, `scripts/migrations/migrate_embeddings.py`, `tests/unit/test_recency_detector.py`, `tests/unit/test_prompt_builder_temporal.py`, `tests/unit/test_conversation_rag.py`.

---

## 2026-02-20 — Phases 10-13: Rich Markdown, Code Blocks, Message Widgets, Right Panel

**Changed:**

- `pyproject.toml` — Added `markdown-it-py[linkify,plugins]`, `mdit-py-plugins`, `pygments`, `matplotlib` to desktop extras for markdown rendering, syntax highlighting, and LaTeX math.
- `emily_chat/ui/markdown_renderer.py` — New module. `MarkdownRenderer` converts raw markdown to Qt-renderable HTML with CommonMark, GFM tables/tasks/strikethrough, Pygments syntax highlighting (inline CSS), LaTeX math rendering via matplotlib (base64 PNG `<img>`), and Mermaid diagram rendering via `mmdc` subprocess (SVG data URI, with code-block fallback). `render_with_code_blocks()` splits markdown at fence boundaries for widget embedding. `MarkdownTextBrowser` (QWidget) interleaves `QTextBrowser` prose segments with `CodeBlockWidget` instances, supports streaming via debounced re-render. `build_document_css()` generates theme-aware CSS for QTextBrowser documents.
- `emily_chat/ui/code_block_widget.py` — New module. `CodeBlockWidget` (QFrame) displays fenced code blocks with language badge, copy button (checkmark flash), Run button (Python sandbox via `asyncio.create_subprocess_exec` with optional `unshare --net`), expand/collapse for blocks >30 lines, and diff detection. `detect_language()`, `count_lines()`, `is_diff()`, `run_python_sandbox()` are testable standalone functions.
- `emily_chat/ui/right_panel.py` — Major rewrite. `_ThinkingSection` now auto-detects reasoning phases (ANALYZING, CONSIDERING, COMPARING, CONCLUDING, UNCERTAIN) via regex patterns and displays them as collapsible `_PhaseCard` widgets with coloured left borders and time ranges. Added Copy/Clear buttons and thinking token summary. `_MetadataSection` gains a context usage progress bar (`QProgressBar`). New `_SessionStatsSection` shows cumulative session statistics (messages, tokens, cost, avg latency, models used) with expandable per-model cost breakdown sorted descending. `compute_session_stats()` and `detect_phase()` are testable standalone functions.
- `emily_chat/ui/conversation_stream.py` — Major rewrite. `_UserBubble` replaced by `UserMessageWidget` with `MarkdownTextBrowser` body, edit mode (inline `QTextEdit` with version tracking), and action bar (Copy/Edit/Resend). `_EmilyBubble` replaced by `EmilyMessageWidget` with streaming markdown body, collapsible inline thinking block, and full action bar (Like/Dislike/Copy/Copy MD/Retry/Branch). New `ThinkingIndicator` widget with animated dots and deep-think timer mode. `ConversationStream` now emits `edit_requested`, `resend_requested`, `retry_requested`, `branch_requested`, `feedback_given`, and `message_clicked` signals.
- `emily_chat/controller.py` — Wired new `ConversationStream` signals to handler methods (`_on_edit_message`, `_on_resend_message`, `_on_retry_message`, `_on_branch_message`, `_on_feedback`). `_finish_generation` now accumulates session-level statistics and updates `RightPanel.set_session_stats()` via `compute_session_stats()`.
- `emily_chat/config.py` — Added `default_model: str = "claude-sonnet-4-5"` and `active_skill_id: str = "normal"`.
- `emily_chat/main.py` — Updated `ChatController` construction to pass all four panel refs.
- `emily_chat/assets/themes/dark.qss` + `light.qss` — QSS styles for conversation bubbles, input panel, right panel thinking/metadata sections, empty state.

**Tests added:** 157 new tests across 6 test files:
- `tests/unit/test_top_bar.py` (29 tests): formatting, warnings, grouping, signals.
- `tests/unit/test_input_panel_enhanced.py` (17 tests): slash commands, attachments, history, signals.
- `tests/unit/test_skills_system.py` (17 tests): load/save/delete custom skills, merge, validation.
- `tests/unit/test_auto_router.py` (25 tests): classification, routing decisions, cost estimation.
- `tests/unit/test_search_overlay.py` (19 tests): formatting, filters, commands, signals.
- `tests/unit/test_export_engine.py` (19 tests): markdown frontmatter, JSON roundtrip, HTML, PDF.

**Why:** These phases complete the UI interaction layer, making Emily Chat a fully functional desktop application with model/skill management, intelligent routing, search, and data export.

**Affects:** `controller.py`, `main_window.py`, `main.py`, `left_sidebar.py`, `skills.py`, `theme_engine.py`, `dark.qss`, `light.qss`, plus 7 new files.

---

## 2026-02-20 — System Improvements: Architecture Wiring, Async Fixes, Code Quality

**Changed:**

- `core/bootstrap.py` — Wired `LLMFleet`, `MemoryManager`, `AgentRegistry`, and `HybridRetriever` (with `CrossEncoderReranker`) into Bootstrap startup/shutdown. System now initializes the full multi-agent + pentagonal-memory + RAG stack. Qdrant/BM25/reranker failures degrade gracefully. Agent bus dispatch loop started as background task.
- `memory/semantic/retriever.py` — Added optional `reranker` parameter to `HybridRetriever.__init__()`. Integrated cross-encoder reranking after parent promotion in `retrieve()` — previously documented but never called.
- `core/bus.py` — `AgentBus._receive_loop()` now tracks handler tasks in a `_handler_tasks` set with a `_on_handler_done` callback that logs exceptions. Replaces silent fire-and-forget `create_task`.
- `agents/planner.py` — Replaced non-existent `SummaryAgent` reference with `ToolBuilderAgent` in available agents prompt.
- `agents/registry.py` — Added `("agents.tool_builder", "ToolBuilderAgent")` to specialist agent imports.
- `security/encryption.py` — Added `ensure_key_async()`, `encrypt_bytes_async()`, `decrypt_bytes_async()` wrappers using `asyncio.to_thread`.
- `security/pii_scrubber.py` — Added `"DATE": "<DATE>"` to NER replacements. Made `scrub_dict()` recursive (handles nested dicts and lists). Added `scrub_async()` and `scrub_dict_async()` wrappers.
- `api/app.py` — Replaced ~14 `except Exception: pass` blocks with logged warnings. Wrapped blocking `Path.read_text()` and `subprocess.run` calls in `asyncio.to_thread`. Replaced hardcoded debug log path with `settings.logs_dir / "debug.log"`. Added `_get_system_resources_async()` wrapper.
- `tests/unit/test_memory_manager.py` — 8 tests: startup, user/assistant turns, retrieve_context with/without retriever, error handling, push_perception, get_context_for_llm.
- `tests/unit/test_registry.py` — 5 tests: start_all, get by name, nonexistent agent, stop_all, graceful import failure.
- `tests/unit/test_retriever.py` — 5 tests: RRF fusion basic/single/empty, retrieve with/without reranker.
- `tests/unit/test_pii_scrubber.py` — 14 tests: regex scrub (email, phone, SSN, IP, credit card), no-PII passthrough, flat/recursive/list scrub_dict, fields filter, async wrappers.

**Why:** Proactive codebase health scan identified crash bugs, data loss paths, and code quality issues that would impact reliability.

**Affects:** `core/bootstrap.py`, `memory/semantic/retriever.py`, `core/bus.py`, `agents/planner.py`, `agents/registry.py`, `security/encryption.py`, `security/pii_scrubber.py`, `api/app.py`, plus 4 new test files.

---

### 2026-02-20 — README.md updated with current model stack and operations guide

**What changed:** Updated `README.md` to reflect the actual deployed model stack (Qwen2.5-3B nano, Phi-4 Q4_K_M fast, QwQ:latest, MiniCPM-V vision, BGE-M3 embedding). Replaced outdated `ollama pull` commands with correct tags. Added a comprehensive "Operations Guide" section covering: system status checks, VRAM co-residency table, model updating workflow, code updating workflow, test commands, troubleshooting table, and key config file reference. Fixed all commands to use `.venv/bin/python` prefix for consistency.

**Why:** Previous README had stale model names (phi3:mini, phi4:14b-q6_K, qwq:32b-q5_K_M) that don't exist in Ollama, and lacked operational guidance for day-to-day use.

**Affects:** `README.md`, `MEMORY_LOG.md`.

---

### 2026-02-21 — Brain Dashboard: in-process PySide6 live visualization of Emily's internals

**What changed:** Implemented a complete Brain Dashboard system that runs in-process with Emily via PySide6, providing real-time visualization of all internal events.

New files:
- `core/brain_hub.py` — Central event hub with Qt signals, ring buffer (1000 events), rate-limited log forwarding, thread-safe `emit_sync()` for structlog
- `observability/brain_tap.py` — structlog processor that mirrors log events to BrainEventHub, with noisy-event filtering
- `ui/brain/__init__.py`, `ui/brain/dashboard.py` — Main `BrainDashboard` QMainWindow with dark Catppuccin theme and 7-panel layout
- `ui/brain/widgets.py` — FSMStateWidget, LLMStreamWidget, ReActWidget, AgentBusWidget, PerceptionWidget, MemoryOpsWidget, MetricsWidget, EventLogWidget (with pause, filter, search)

Modified files:
- `core/bootstrap.py` — Accepts optional `brain_hub`, passes it to Fleet/Memory/Buses, registers FSM state change listener
- `core/bus.py` — PerceptionBus and AgentBus emit events to brain_hub when attached
- `llm/fleet.py` — Emits `llm.token_start/token/token_end` during streaming, `llm.request/response` for non-streaming
- `llm/react_loop.py` — Emits `react.iteration_start/thought/action/observation/final_answer` at each reasoning step
- `memory/manager.py` — Emits `memory.user_turn/assistant_turn/context_retrieved` on read/write ops
- `observability/logger.py` — `configure_logging()` accepts `brain_tap=True` to install the brain tap processor
- `main.py` — Rewritten with `--gui` (default) and `--no-gui` flags; GUI mode runs Bootstrap on AsyncRunner QThread, dashboard on main thread

**Why:** To provide a real-time "brain view" showing every internal event (LLM tokens, agent messages, ReAct reasoning, FSM transitions, perception events, memory ops) in a live desktop GUI synced with the main process.

**Affects:** `core/brain_hub.py`, `core/bootstrap.py`, `core/bus.py`, `llm/fleet.py`, `llm/react_loop.py`, `memory/manager.py`, `observability/logger.py`, `observability/brain_tap.py`, `ui/brain/`, `main.py`.

---

## 2026-02-21 — Dedicated Voice Mode Dashboard

**What changed:**

1. **`api/voice_dashboard.html`** (new) — Standalone full-page voice mode dashboard served at `/voice-dashboard`. Built with Alpine.js + Chart.js, same dark theme as the main dashboard. Features:
   - Hero section with animated FSM state orb, pipeline mode indicator, session timer
   - Status cards for TTS, STT, wake word, and speaker tracking
   - Canvas-based audio level waveform visualization (input + output)
   - Live transcript panel via SSE (`/chat/voice-transcript`) with auto-scroll
   - Pipeline modules grid showing per-module health (audio capture, AEC, noise suppression, streaming STT, speaker engine)
   - User emotion telemetry (valence, arousal, engagement, cognitive load bars) + radar chart
   - Turn detection signal with confidence breakdown
   - Latency budget table (P50/P95/P99) with red highlighting when P95 > 300ms
   - Rhythm synchronization panel with SVG entrainment gauge ring
   - Audio controls (mic/speaker device selectors, TTS provider/voice pickers, test/preview buttons)
   - Session stats sidebar (backchannels, interrupts, cache hit rate, system resources)
   - Polling: engine telemetry every 1.5s, system status every 5s, transcript via SSE

2. **`api/routes/voice_engine.py`** — Added two new endpoints:
   - `GET /voice-engine/pipeline-status` — per-module health and config for every voice pipeline component (audio capture, AEC, noise suppression, streaming STT, speaker engine)
   - `GET /voice-engine/speaker` — speaker identification/diarization data (active speakers, IDs, confidence, primary flag)

3. **`api/app.py`** — Added `GET /voice-dashboard` route that reads and serves `api/voice_dashboard.html`. Added "Open Dedicated Voice Dashboard" link to the existing Voice Mode panel in the main dashboard sidebar.

**Why:** The embedded Voice Mode panel in the main dashboard is compact and shares screen space with other panels. A dedicated full-page dashboard provides a richer monitoring experience during active voice conversations — larger transcript, more detailed pipeline health, and faster polling (1.5s vs 3s). No backend logic changes; all data comes from existing API routes plus two new read-only endpoints.

**Affects:** `api/voice_dashboard.html` (new), `api/routes/voice_engine.py`, `api/app.py`.

---

## 2026-02-20 — Voice Mode Through Full Agent Stack + First-Run Onboarding

### Voice Mode Fix

Rerouted voice mode so the ConversationFSM publishes transcripts to the AgentBus (targeting ConversationAgent) instead of using the lightweight `ConversationLLMOrchestrator` directly. The FSM now receives `tts.speak`/`tts.done` messages back from ConversationAgent and plays them through TTS. The orchestrator is kept as a fallback when the agent bus is unavailable.

**Changes:**
- `conversation/voice_engine.py` — accepts `agent_bus`, `fleet`, `memory` and passes them to the FSM
- `conversation/fsm.py` — new `_response_via_agent_bus()` publishes transcript, waits for TTS chunks; new `_handle_tts_message()` handler registered on the bus; extracted `_speak_sentence()` for reuse; added `ONBOARDING` state
- `agents/conversation.py` — sends `tts.done` after streaming completes; fixed `get_system_prompt()` to pass `user_profile` instead of misusing `persona`
- `core/bootstrap.py` — passes `agent_bus`, `fleet`, `memory` to `VoiceEngine` constructor

### User Profile Injection

Added `user_profile` parameter to `PromptBuilder.get_system_prompt()`. New `_format_user_profile_injection()` formats name, facts, preferences, goals, relationships, and recurring topics as a `USER CONTEXT` block in the system prompt so Emily always knows who she's talking to.

**Changes:**
- `llm/prompt_builder.py` — new `user_profile` param, `_format_user_profile_injection()`, `build_onboarding_prompt()`

### First-Run Onboarding

On first start (when `procedural.is_new_user` is True), the voice engine runs a multi-turn interview before entering the normal conversation loop. Emily asks 10 questions (name, interests, work, communication style, relationships, etc.) and saves all extracted facts to procedural memory.

**Changes:**
- `agents/onboarding.py` (new) — `run_onboarding()` drives the interview loop with TTS/STT callbacks
- `memory/procedural.py` — added `is_new_user` property
- `conversation/voice_engine.py` — checks `is_new_user` and calls `fsm.start_onboarding()` before `fsm.run()`
- `conversation/fsm.py` — `start_onboarding()`, `_onboarding_speak()`, `_onboarding_listen()` methods

**Affects:** Voice mode, ConversationAgent, PromptBuilder, ProceduralMemory, Bootstrap.

---

## 2026-02-20 — Desktop Voice Dashboard (PySide6)

Replaced the web-based voice dashboard with a standalone PySide6 desktop window that runs in-process alongside the Brain Dashboard. Instead of HTTP polling, it reads directly from the VoiceEngine's attributes via a QTimer-driven poller (500ms interval).

**New files:**
- `ui/voice/__init__.py` — package init
- `ui/voice/poller.py` — `VoiceEnginePoller(QObject)` with `data_updated` and `transcript_received` signals; reads FSM state, emotion, turn signal, rhythm, pipeline modules, speakers, and stats
- `ui/voice/widgets.py` — 12 widgets: HeroWidget, StatusCardsWidget, AudioLevelsWidget, TranscriptWidget, PipelineWidget, EmotionWidget, TurnDetectionWidget, RhythmWidget, SessionStatsWidget, SpeakersWidget, SystemWidget, plus _StateOrb, _WaveformCanvas, _EntrainmentGauge
- `ui/voice/dashboard.py` — `VoiceDashboard(QMainWindow)` with two-column layout (main area + 300px sidebar)

**Modified files:**
- `main.py` — launches VoiceDashboard alongside BrainDashboard in `--gui` mode; uses a QTimer to wire the poller to the engine once bootstrap is ready
- `core/bootstrap.py` — removed the `_start_embedded_web_server` background task (no longer needed)

**Affects:** main.py, core/bootstrap.py, new ui/voice/ package.

---

## 2026-02-21 — Voice Mode Fixes (TTS/STT/Audio Pipeline)

**What changed:**

1. **Edge TTS MP3-vs-PCM mismatch**: Edge TTS yields MP3 bytes, but the FSM treated all TTS output as raw int16 PCM. Added `_decode_mp3_to_pcm()` in `voice/tts.py` using ffmpeg so Edge TTS now yields int16 PCM like all other engines.

2. **bytes-vs-ndarray type mismatch**: FSM's `_speak_sentence()` and `_onboarding_speak()` passed `bytes` to `AudioCaptureEngine.write_output()` which expects `float32 ndarray`. Fixed both methods to pass the float32 array directly.

3. **AudioCaptureEngine device fallback**: `_start_input_stream()` / `_start_output_stream()` had no error handling — any missing audio device crashed the entire voice engine. Wrapped in try/except with graceful `_silence_generator()` fallback.

4. **TTSManager config-driven engine order**: Engine priority was hardcoded (XTTS→Kokoro→Edge) ignoring `tts.primary`/`tts.fallback` from config. Refactored to build engine list from config so `primary: "kokoro"` actually takes effect.

5. **KokoroEngine espeak-only fallback**: Since spacy is incompatible with Python 3.14, added a fallback path in `KokoroEngine.load()` that tries to build the pipeline with espeak-only G2P (requires espeak-ng system package).

6. **Optimal config applied**: Kokoro voice `af_sky` (Grade C-) → `af_heart` (Grade A); STT language `null` → `"en"` for faster English recognition; enabled `vad_filter=True` in streaming STT for cleaner transcription.

7. **Bootstrap hardening** (from prior session): Signal handler wrapped in try/except for QThread compatibility; screen capture disabled on Wayland; voice engine cleanup on failure prevents double-free crashes.

**Why:** Runtime logs analysis (3-minute run) revealed 116 consecutive 3-second silence clips being transcribed by Whisper, 5 hallucinated-text fallback triggers, and repeated 30-second watchdog fires — all with no real LLM backing any response.

**Affects:** `voice/tts.py`, `config.py`, `config.yaml`, `conversation/fsm.py`, `perception/audio/capture.py`.

---

## 2026-02-21 — Psychoacoustics Gap Fixes

**What changed:** Closed all gaps between the PSYCHOACOUSTICS_MODEL.md spec and the actual implementation across five areas.

1. **Graceful trail-off wired into FSM** (`conversation/fsm.py`): `_speak_sentence()` now buffers TTS chunks so that on interrupt, the remaining audio is passed to `InterruptHandler.find_graceful_stop_point()` and `apply_fade_out()` — Emily never stops mid-word. After the 20ms fade, the classified acknowledgment vocalization (e.g. "oh sure", "you're right") is synthesized and played. `_response_via_agent_bus()` and `_response_via_orchestrator()` both delegate to the new `_apply_graceful_trailoff()` helper, which extracts partial user text and energy from the current perception state for accurate interrupt classification.

2. **COMPLETION backchannels implemented** (`conversation/backchannel.py`): The previously empty `_TOKEN_POOLS[COMPLETION]` now contains 10 stub tokens ("right", "exactly", "of course", etc.). `_select_type()` accepts a `completion_prediction_score` parameter; when > 0.90 it selects COMPLETION. The FSM's `_backchannel_loop` extracts `syntactic_completeness` from the turn signal and passes it through. Full LLM-predicted sentence finishing is deferred to a future iteration.

3. **Phrase-boundary and stress-overlap safety** (`conversation/backchannel.py`): New `is_safe_to_insert(prosody)` method checks `ProsodyFeatures.pause_type` (must be "breath", "filled", or "silence") and `stress_pattern` (last value must be <= 0.7). `should_backchannel()` now accepts a `prosody` parameter and calls this guard before emitting any event, per the spec rule "never overlap stressed syllables" and "insert at inter-pausal unit boundaries."

4. **Breathing rhythm in entrainment targets** (`conversation/rhythm_sync.py`, `voice/breath_injector.py`): Added `breath_interval_s` field to `RhythmTargets`, blended in `get_targets()` with the same entrainment formula (clipped 10-30s). `BreathInjector` gained `set_breath_interval()` and uses it for micro-breath timing instead of the former hardcoded 15-25s range.

5. **New unit tests**: `tests/unit/test_backchannel.py` (18 tests covering type selection, COMPLETION, cooldown, token diversity, phrase-boundary safety) and `tests/unit/test_rhythm_sync.py` (19 tests covering blending, breath interval, EMA updates, export/import, clipping, convenience accessors). All 37 new tests pass alongside the 63 existing voice-related tests.

**Why:** The psychoacoustics spec in PSYCHOACOUSTICS_MODEL.md defined six subsystems but two were partially implemented: interrupt trail-off logic existed but was never called from the FSM, and the backchannel engine lacked COMPLETION type, phrase-boundary guards, and stress-overlap prevention. Rhythm entrainment tracked breathing but didn't use it.

**Affects:** `conversation/fsm.py`, `conversation/backchannel.py`, `conversation/rhythm_sync.py`, `voice/breath_injector.py`, `tests/unit/test_backchannel.py` (new), `tests/unit/test_rhythm_sync.py` (new).

---

## 2026-02-21 — llama-cpp-python Backend Integration

**What changed:** Added llama-cpp-python as a secondary LLM backend for latency-critical model tiers, configurable per tier alongside Ollama.

1. **LLMClientProtocol** (`llm/base.py`, new): Runtime-checkable `Protocol` defining the interface both backends implement: `chat_stream`, `chat`, `embed`, `keep_alive`, `health_check`, `close`.

2. **LlamaCppClient** (`llm/llamacpp_client.py`, new): In-process inference via llama-cpp-python. Async streaming bridged via `asyncio.Queue` + `run_in_executor`. Model deduplication (nano/voice_fast share one `Llama` instance). No-op `keep_alive`. Graceful fallback if GGUF missing or library not installed.

3. **Per-tier backend config** (`config.py`, `config.yaml`): `LlamaCppModelConfig`, `LlamaCppConfig`, `TierBackend` models added. Each tier (nano, voice_fast, fast, smart, reasoning, vision, embedding) maps to either `"ollama"` or `"llamacpp"`. Default: nano/voice_fast use llamacpp, all others use Ollama.

4. **Fleet dispatch** (`llm/fleet.py`): `LLMFleet` creates both `OllamaClient` and `LlamaCppClient` at startup. `_client_for_tier()` routes each tier to the configured backend; falls back to Ollama if the llamacpp model isn't loaded.

5. **Orchestrator decoupling** (`llm/orchestrator.py`): `ConversationLLMOrchestrator` now accepts an optional pre-built `client` via constructor injection. Fixed the `buffer += token` bug — `chat_stream` yields `CompletionChunk` objects, not strings; now extracts `chunk.content`.

6. **Dependency** (`pyproject.toml`): `llama-cpp-python>=0.3.0` added to `gpu-cuda` optional deps.

7. **DECISIONS.md**: LLM Backend entry updated — llama-cpp-python promoted from "rejected/fallback" to "secondary backend for latency-critical tiers".

**Why:** Ollama's HTTP/JSON overhead is a significant fraction of total latency for the always-resident 3B nano model. In-process inference eliminates ~60-70ms of serialization overhead per request, helping meet the <1s first-token latency target for the voice pipeline.

**Affects:** `llm/base.py` (new), `llm/llamacpp_client.py` (new), `llm/client.py`, `llm/fleet.py`, `llm/orchestrator.py`, `config.py`, `config.yaml`, `pyproject.toml`, `DECISIONS.md`, `tests/unit/test_llamacpp_client.py` (new).

---

## 2026-02-21 — STT Speed Fix + Desktop Device Selection

### STT Pre-Downsampling (performance)

Replaced the per-transcribe `np.interp` resampling in `StreamingSTTEngine._transcribe_buffer` with per-chunk `scipy.signal.decimate` in `process_chunk()`. Audio is now stored in the buffer at 16kHz, so transcription runs on pre-downsampled data with no resampling overhead. The sliding window was reduced from 5s to 3s, cutting per-call transcription time by ~40%.

**Why:** Every 150ms the engine was concatenating up to 240k samples (5s at 48kHz), resampling with linear interpolation (no anti-aliasing), and feeding it all to Faster-Whisper. This caused noticeable latency and aliasing artifacts that degraded transcription quality.

### Mic/Speaker Selection in Desktop Voice Dashboard

Added `DeviceSelectorWidget` to the PySide6 voice dashboard sidebar with two dark-themed `QComboBox` dropdowns for microphone and speaker selection. A Refresh button re-scans devices via `sounddevice.query_devices()`. On selection change, `VoiceEnginePoller.change_device()` stops the `AudioCaptureEngine`, reconfigures the device, and restarts it. The poller snapshot now includes `current_input_device` and `current_output_device` so the widget reflects the active selection.

**Affects:** `perception/audio/streaming_stt.py`, `ui/voice/widgets.py`, `ui/voice/poller.py`, `ui/voice/dashboard.py`.

---

## 2026-02-21 — Voice Fast Path in ConversationAgent

**Changed:** Added a voice fast path to the ConversationAgent so simple voice queries skip the heavyweight pipeline stages (RAG retrieval, web search, CriticAgent) and route to the voice_fast tier (Qwen2.5:3b via llama-cpp-python) instead of Phi-4 14B.

1. **`llm/router.py`** — Added `voice_mode: bool` parameter to `ModelRouter.route()`. When `voice_mode=True` and complexity is below the configured threshold (default 5), routes to `VOICE_FAST` instead of `FAST`. Math/reasoning queries always escalate regardless of voice mode.

2. **`llm/fleet.py`** — Propagated `voice_mode` parameter through `LLMFleet.route()`.

3. **`config.py`** — Added three new fields to `LLMRouting`: `voice_fast_complexity_threshold` (default 5), `voice_skip_rag_below` (default 5), `voice_skip_critic` (default True).

4. **`config.yaml`** — Added matching config entries under `llm.routing`.

5. **`llm/recency_detector.py`** — Added `needs_web_search_voice()` — a stricter variant that only triggers on explicit search intent ("search for", "look up", "google"), ignoring passive recency and news keywords that would add 500ms-2s of latency to casual voice turns.

6. **`agents/conversation.py`** — Refactored `_generate_response()` with a `voice_mode` parameter. When `voice_mode=True` and complexity < threshold: skips RAG retrieval, uses `needs_web_search_voice()` instead of `needs_web_search()`, forces `VOICE_FAST` tier, and skips the CriticAgent. Complex voice queries (complexity >= threshold) still get the full pipeline but skip the critic if `voice_skip_critic` is enabled.

7. **`tests/unit/test_recency_detector.py`** — Added 13 parametrised tests for `needs_web_search_voice()`.

8. **`tests/unit/test_conversation_rag.py`** — Updated test helper with voice fast path config mocks.

**Why:** The full pipeline (RAG + web search + Phi-4 14B + CriticAgent) was running for every voice turn, causing ~3-6s end-to-end latency even for simple greetings and casual chat. The voice_fast tier (Qwen2.5:3b) was already configured but never used. This change reduces simple voice turn latency to ~500ms-1s while preserving the full pipeline for complex queries.

**Affects:** `llm/router.py`, `llm/fleet.py`, `llm/recency_detector.py`, `agents/conversation.py`, `config.py`, `config.yaml`, `tests/unit/test_recency_detector.py`, `tests/unit/test_conversation_rag.py`.

---

### 2026-02-21 — Force VOICE_FAST for all voice turns (eliminate Phi-4 from voice pipeline)

**What changed:** Unified `_generate_response()` in ConversationAgent so that ALL voice-mode turns use `force_tier=ModelTier.VOICE_FAST` (Qwen2.5:3b), regardless of query complexity. Previously, voice queries with complexity >= 5 still fell through to the full pipeline and used Phi-4 14B, which was extremely slow on CPU. Also fixed onboarding to use VOICE_FAST.

1. **`agents/conversation.py`** — Removed the two-path split (voice fast path vs full pipeline). Now a single unified path: when `voice_mode=True`, `force_tier` is always set to `ModelTier.VOICE_FAST`. RAG is still conditionally skipped for simple voice queries (complexity < `voice_skip_rag_below`), web search uses the stricter `needs_web_search_voice()` instead of `needs_web_search()`, and the CriticAgent is skipped — but the model is always VOICE_FAST.

2. **`agents/onboarding.py`** — Added `force_tier=ModelTier.VOICE_FAST` to the `fleet.chat()` call so onboarding turns use the fast model instead of defaulting to Phi-4.

**Why:** Phi-4 14B running on CPU (100% CPU, no GPU offload) was producing 20-30 second response times for voice turns that hit the full pipeline. The original voice fast path only covered queries with complexity < 5, but many voice queries (especially those with complex keywords like "explain", "remember", etc.) were still routing to Phi-4. The user reported voice mode was "still using Phi-4." Now ALL voice turns use Qwen2.5:3b (either via llama-cpp in-process or Ollama) for consistent sub-second latency.

**Affects:** `agents/conversation.py`, `agents/onboarding.py`.

---

### 2026-02-21 — Wire voice mode events into Brain Dashboard

**What changed:** Added BrainEventHub integration to the voice pipeline so the Brain Dashboard shows real-time voice events.

1. **`conversation/fsm.py`** — Added `_brain_hub` attribute. Emits brain events for: FSM state transitions (`fsm.state_change`), STT committed utterances (`perception.stt_committed`), LLM request routing (`llm.request` with path=orchestrator or agent_bus), TTS sentence playback (`perception.tts_speaking`), and silence watchdog triggers (`fsm.silence_watchdog`).

2. **`conversation/voice_engine.py`** — Added `brain_hub` parameter to `__init__()` and passes it through to `ConversationFSM.configure()`.

3. **`core/bootstrap.py`** — Passes `brain_hub` to `VoiceEngine` constructor so the full chain is wired: Bootstrap → VoiceEngine → ConversationFSM.

**Why:** The Brain Dashboard had no visibility into the voice pipeline. LLM events from the fleet were showing, but STT transcriptions, FSM state changes, TTS playback, and routing decisions were invisible. Now all voice events appear in the dashboard panels.

**Affects:** `conversation/fsm.py`, `conversation/voice_engine.py`, `core/bootstrap.py`.

---

### 2026-02-21 — Voice Debug Mode: full STT/TTS/conversation logs, mic test, real levels

**What changed:**

1. **`core/brain_hub.py`** — `BrainEventHub.attach_signals()` now supports multiple signal listeners via `_extra_signals` list. Both Brain Dashboard and Voice Dashboard can receive events simultaneously.

2. **`ui/voice/dashboard.py`** — `VoiceDashboard` now accepts an optional `brain_hub` parameter. Creates `_VoiceBrainSignals` bridge and attaches it to the hub. Wires perception/LLM/FSM events to the new `VoiceDebugWidget`. Connects "Test TTS" button to speak a test phrase via the engine's TTS pipeline. Connects "Test Mic" button to record 3s of audio, playback, and show pass/fail. Feeds `emily_spoke` perception events into the existing `TranscriptWidget` so both sides of the conversation are visible.

3. **`ui/voice/widgets.py`** — Added `VoiceDebugWidget`: tabbed panel (STT / TTS / Conversation) showing real-time BrainEventHub events. STT tab shows committed utterances with word count and latency. TTS tab shows speaking events plus LLM request/response latencies. Conversation tab shows full user+Emily transcript with color-coded borders. All tabs support clear and auto-trim to 500 lines. `AudioLevelsWidget` replaced synthetic sine waveform with real mic RMS level bar (green/yellow/red by dB). Added "Test Mic" button with recording indicator and pass/fail result display.

4. **`ui/voice/poller.py`** — Added `_read_mic_level()` method that computes RMS energy from the capture engine's current audio chunk. Includes `mic_level` in every poller snapshot.

5. **`main.py`** — Passes `brain_hub=hub` to `VoiceDashboard` constructor.

6. **`conversation/fsm.py`** — Emits `perception.emily_spoke` event after each sentence finishes playing via TTS, so the Voice Dashboard transcript shows Emily's responses.

**Why:** The Voice Dashboard lacked full debugging visibility — no STT logs, no TTS logs, no Emily-side transcript, synthetic waveform, unwired buttons. This adds a comprehensive debug mode with real-time event streams from the BrainEventHub plus functional mic/TTS testing.

**Affects:** `core/brain_hub.py`, `ui/voice/dashboard.py`, `ui/voice/widgets.py`, `ui/voice/poller.py`, `main.py`, `conversation/fsm.py`.

---

### 2026-02-21 — Fix emily_chat controller-to-streaming-engine wiring

**What changed:**

1. **`emily_chat/models/provider_factory.py`** (NEW) — Provider factory that resolves a `ModelSpec` to a concrete `BaseProvider` instance. Maps provider names to classes, reads API keys from environment variables, caches instances by provider name. Ollama always available (no key needed). Raises `ProviderUnavailableError` with a clear message naming the missing env var when a cloud provider's key is absent.

2. **`emily_chat/models/streaming_engine.py`** — Added lightweight async-generator `StreamingEngine` class and `_PROVIDERS` cache to `emily_chat/models/streaming_engine.py`. Fixed circular import by making `providers.base.BaseProvider` import TYPE_CHECKING-only.
3. **`identity.py`** — Added `user_profile` parameter to `PromptBuilder.get_system_prompt()`. New `_format_user_profile_injection()` formats name, facts, preferences, goals, relationships, and recurring topics as a `USER CONTEXT` block in the system prompt so Emily always knows who she's talking to.
4. **`agents/onboarding.py`** — Converted from bare function to `OnboardingAgent(BaseAgent)` class. Registered in `agents/registry.py`. Kept `run_onboarding()` function for FSM callback compatibility.
5. **`agents/research.py`** — Fleshed out with `_retrieve_rag_context()` (hybrid retriever) and `_web_search()` (plugin-based). Both run in parallel via `asyncio.gather`, results fed to LLM synthesis.
6. **`agents/code_agent.py`** — Added `_extract_code_blocks()` and `_run_sandboxed()` using `plugins.sandbox.run_python_sandboxed`. Generated code is now executed and output appended to results.
7. **`perception/system/telemetry.py`** — Created new module with `SystemTelemetry` class providing CPU/RAM/GPU/disk/network metrics via `psutil` and `nvidia-smi`, all offloaded via `asyncio.to_thread`.

**Modified files:**
- `core/bootstrap.py` — Wired `LLMFleet`, `MemoryManager`, `AgentRegistry`, and `HybridRetriever` (with `CrossEncoderReranker`) into Bootstrap startup/shutdown. System now initializes the full multi-agent + pentagonal-memory + RAG stack. Qdrant/BM25/reranker failures degrade gracefully. Agent bus dispatch loop started as background task.
- `memory/semantic/retriever.py` — Added optional `reranker` parameter to `HybridRetriever.__init__()`. Integrated cross-encoder reranking after parent promotion in `retrieve()` — previously documented but never called.
- `core/bus.py` — `AgentBus._receive_loop()` now tracks handler tasks in a `_handler_tasks` set with a `_on_handler_done` callback that logs exceptions. Replaces silent fire-and-forget `create_task`.
- `agents/planner.py` — Replaced non-existent `SummaryAgent` reference with `ToolBuilderAgent` in available agents prompt.
- `agents/registry.py` — Added `("agents.tool_builder", "ToolBuilderAgent")` to specialist agent imports.
- `security/encryption.py` — Added `ensure_key_async()`, `encrypt_bytes_async()`, `decrypt_bytes_async()` wrappers using `asyncio.to_thread`.
- `security/pii_scrubber.py` — Added `"DATE": "<DATE>"` to NER replacements. Made `scrub_dict()` recursive (handles nested dicts and lists). Added `scrub_async()` and `scrub_dict_async()` wrappers.
- `api/app.py` — Replaced ~14 `except Exception: pass` blocks with logged warnings. Wrapped blocking `Path.read_text()` and `subprocess.run` calls in `asyncio.to_thread`. Replaced hardcoded debug log path with `settings.logs_dir / "debug.log"`. Added `_get_system_resources_async()` wrapper.
- `tests/unit/test_memory_manager.py` — 8 tests: startup, user/assistant turns, retrieve_context with/without retriever, error handling, push_perception, get_context_for_llm.
- `tests/unit/test_registry.py` — 5 tests: start_all, get by name, nonexistent agent, stop_all, graceful import failure.
- `tests/unit/test_retriever.py` — 5 tests: RRF fusion basic/single/empty, retrieve with/without reranker.
- `tests/unit/test_pii_scrubber.py` — 14 tests: regex scrub (email, phone, SSN, IP, credit card), no-PII passthrough, flat/recursive/list scrub_dict, fields filter, async wrappers.

**Why:** Proactive codebase health scan identified crash bugs, data loss paths, and code quality issues that would impact reliability.

**Affects:** All files listed above, plus 4 new test files.

---

## 2026-02-28 — Abliterated Model Full Integration (QwQ-32B Reasoning)

**What changed:**

1. **`config.yaml`** — Per-tier inference overrides:
   - `nano`: temp=0.3, max_tokens=512, thinking=false
   - `voice_fast`: temp=0.7, max_tokens=1024, thinking=false (saves latency)
   - `fast`: temp=0.7, max_tokens=4096, thinking=true
   - `smart`: temp=0.6, max_tokens=8192, thinking=true
   - `reasoning`: temp=0.6, max_tokens=16384, thinking=true (QwQ-32B gets full room)

2. **`config.py`** — Added `TierInferenceOverride` and `TierInferenceConfig` Pydantic models;
   wired `tier_inference` field into `LLMConfig`.

3. **`llm/fleet.py`** — Major upgrades:
   - Added `extract_thinking(text) -> (thinking, clean)` helper to strip `<think>…</think>`
   - `chat_stream`: per-tier temp/max_tokens/enable_thinking; streaming think-block interceptor
     routes thinking tokens to brain-hub `"thinking_token"` events, yields only clean text
   - `chat`: per-tier settings; uses `extract_thinking` on full response; stores thinking
     in `result.thinking_content` and emits brain-hub `"thinking"` event

4. **`llm/router.py`** — Smarter routing for abliterated models:
   - Added `_REASONING_PATTERNS` (18 patterns: "think through", "tradeoffs", "first principles", etc.)
   - Added `_reasoning_re` to `__init__`
   - `_estimate_complexity`: reasoning patterns add +3 to score (routes to QwQ-32B)
   - `_infer_task_type`: detects `TaskType.REASONING` from text patterns

5. **`llm/prompt_builder.py`** — Added `get_reasoning_system_prompt()`:
   - Dedicated system prompt for QwQ-32B thinking mode
   - Instructs 5-step thinking: Understand → Decompose → Analyse → Critique → Conclude
   - Tells model to keep final answer clean after `</think>`

6. **`agents/conversation.py`** — Wire-up:
   - Imports `TaskType` from router
   - `_generate_response`: selects `get_reasoning_system_prompt()` when `effective_tier == REASONING`
   - Passes `task_type=routing.task_type` to `fleet.chat_stream`
   - Logs `task_type` in routing decision

**Why:** User requested full abliterated model integration. QwQ-32B is a dedicated reasoning
model — it needs: (a) thinking enabled, (b) more max_tokens, (c) a reasoning-specific prompt,
(d) thinking tokens stripped before TTS, (e) smart routing to only invoke it for genuinely
complex queries.

**Affects:**
- `config.yaml` — tier_inference section added
- `config.py` — TierInferenceOverride, TierInferenceConfig, LLMConfig.tier_inference
- `llm/fleet.py` — extract_thinking, per-tier settings, streaming think-block interceptor
- `llm/router.py` — reasoning patterns, REASONING task type detection
- `llm/prompt_builder.py` — get_reasoning_system_prompt()
- `agents/conversation.py` — reasoning prompt selection, task_type routing

---
