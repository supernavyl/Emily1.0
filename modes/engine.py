"""Operational-mode engine for Emily's multi-model orchestration.

Each mode is a frozen configuration object that controls the entire execution
pipeline — tier preference, reasoning strategy, feature gates, memory scope,
and rules.  The :class:`ModeEngine` singleton provides O(1) mode lookup and
manages custom-mode persistence.

Modes are NOT skills: a mode configures *how* Emily thinks; a skill configures
*what* Emily thinks about.  The combination ``(mode, skill)`` fully determines
runtime behaviour.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class OperationalMode:
    """Immutable configuration object that controls the execution pipeline."""

    name: str
    display: str
    icon: str
    description: str

    # ── Execution config ──────────────────────────────────────────
    tier_preference: list[str] = field(default_factory=list)
    reasoning_strategy: str = "direct"
    reasoning_depth: int = 1
    temperature_override: float | None = None
    max_tokens_override: int | None = None

    # ── Feature gates ─────────────────────────────────────────────
    enable_rag: bool = True
    enable_web_search: bool = False
    enable_tools: bool = True
    enable_critic: bool = False
    enable_thinking: bool = False

    # ── Memory scope ──────────────────────────────────────────────
    memory_tiers: list[str] = field(
        default_factory=lambda: ["episodic", "semantic"],
    )
    rag_top_k_override: int | None = None

    # ── Agent activation ──────────────────────────────────────────
    active_agents: list[str] = field(default_factory=list)

    # ── Rules ─────────────────────────────────────────────────────
    rules: list[str] = field(default_factory=list)

    # ── Consensus (for consensus/debate strategies) ───────────────
    consensus_models: list[str] = field(default_factory=list)


# ── Singleton ─────────────────────────────────────────────────────

_engine: ModeEngine | None = None
_lock = threading.Lock()


def get_mode_engine() -> ModeEngine:
    """Return (and lazily create) the global ModeEngine singleton."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = ModeEngine()
    return _engine


class ModeEngine:
    """Central registry and lookup for operational modes.

    Built-in modes are immutable; custom modes persist to
    ``~/.emily-chat/custom_modes.json``.
    """

    _CUSTOM_PATH = Path.home() / ".emily-chat" / "custom_modes.json"

    def __init__(self, custom_path: Path | None = None) -> None:
        self._custom_path = custom_path or self._CUSTOM_PATH
        self._builtin: dict[str, OperationalMode] = _builtin_modes()
        self._custom: dict[str, OperationalMode] = self._load_custom()
        log.info(
            "mode_engine_init",
            builtin=len(self._builtin),
            custom=len(self._custom),
        )

    # ── Public API ────────────────────────────────────────────────

    def get(self, mode_id: str) -> OperationalMode:
        """Look up a mode by ID.  Returns 'normal' if not found."""
        return self._builtin.get(mode_id) or self._custom.get(mode_id) or self._builtin["normal"]

    def list_all(self) -> dict[str, OperationalMode]:
        """Return merged dict (custom overridden by built-in on collision)."""
        merged = dict(self._custom)
        merged.update(self._builtin)
        return merged

    def create_custom(self, mode_id: str, mode: OperationalMode) -> None:
        """Create or update a custom mode and persist."""
        if mode_id in self._builtin:
            raise ValueError(f"Cannot override built-in mode '{mode_id}'")
        self._custom[mode_id] = mode
        self._save_custom()

    def delete_custom(self, mode_id: str) -> bool:
        """Remove a custom mode.  Returns True if it existed."""
        if mode_id not in self._custom:
            return False
        del self._custom[mode_id]
        self._save_custom()
        return True

    def is_builtin(self, mode_id: str) -> bool:
        return mode_id in self._builtin

    # ── Persistence ───────────────────────────────────────────────

    def _load_custom(self) -> dict[str, OperationalMode]:
        if not self._custom_path.exists():
            return {}
        try:
            data = json.loads(self._custom_path.read_text("utf-8"))
            return {mid: OperationalMode(**obj) for mid, obj in data.items()}
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            log.warning("custom_modes_load_failed", error=str(exc))
            return {}

    def _save_custom(self) -> None:
        self._custom_path.parent.mkdir(parents=True, exist_ok=True)
        data = {mid: asdict(m) for mid, m in self._custom.items()}
        self._custom_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Serialisation helpers ─────────────────────────────────────

    @staticmethod
    def mode_to_dict(mode: OperationalMode) -> dict[str, Any]:
        return asdict(mode)


# ── Built-in mode definitions ────────────────────────────────────


def _builtin_modes() -> dict[str, OperationalMode]:
    return {
        "normal": OperationalMode(
            name="normal",
            display="Normal",
            icon="\U0001f7e2",  # green circle
            description="Balanced auto-routing with all defaults",
            tier_preference=["smart", "fast"],
            reasoning_strategy="direct",
            reasoning_depth=1,
        ),
        "research": OperationalMode(
            name="research",
            display="Research Mode",
            icon="\U0001f52c",  # microscope
            description="Deep research with CoT, web search, and deep RAG",
            tier_preference=["reasoning", "smart", "cloud_best"],
            reasoning_strategy="chain_of_thought",
            reasoning_depth=3,
            temperature_override=0.2,
            enable_rag=True,
            enable_web_search=True,
            enable_critic=True,
            enable_thinking=True,
            memory_tiers=["episodic", "semantic", "procedural"],
            rag_top_k_override=10,
            consensus_models=["smart", "cloud_fast"],
            rules=["research_citation"],
        ),
        "creative": OperationalMode(
            name="creative",
            display="Creative Mode",
            icon="\U0001f3a8",  # palette
            description="High-temperature creative generation without critic",
            tier_preference=["smart", "fast"],
            reasoning_strategy="direct",
            reasoning_depth=1,
            temperature_override=0.9,
            enable_critic=False,
            enable_thinking=False,
        ),
        "analytical": OperationalMode(
            name="analytical",
            display="Analytical Mode",
            icon="\U0001f4ca",  # bar chart
            description="Tree-of-thought reasoning with critic loops",
            tier_preference=["reasoning", "cloud_best"],
            reasoning_strategy="tree_of_thought",
            reasoning_depth=3,
            temperature_override=0.15,
            enable_critic=True,
            enable_thinking=True,
            memory_tiers=["episodic", "semantic", "procedural", "working"],
        ),
        "code": OperationalMode(
            name="code",
            display="Code Mode",
            icon="\U0001f4bb",  # laptop
            description="Code tools with tree-of-thought for design, direct for impl",
            tier_preference=["code", "smart", "reasoning"],
            reasoning_strategy="tree_of_thought",
            reasoning_depth=2,
            temperature_override=0.1,
            enable_tools=True,
            enable_thinking=True,
            rules=["code_security_review"],
        ),
        "voice": OperationalMode(
            name="voice",
            display="Voice Mode",
            icon="\U0001f3a4",  # microphone
            description="Fast direct path for live voice conversation",
            tier_preference=["voice_fast", "nano"],
            reasoning_strategy="direct",
            reasoning_depth=1,
            enable_rag=False,
            enable_critic=False,
            enable_thinking=False,
            enable_tools=False,
            memory_tiers=["episodic"],
            rules=["voice_brevity"],
        ),
        "debate": OperationalMode(
            name="debate",
            display="Debate Mode",
            icon="\u2696\ufe0f",  # balance scale
            description="Run multiple models and synthesize consensus",
            tier_preference=["smart", "reasoning"],
            reasoning_strategy="consensus",
            reasoning_depth=2,
            enable_critic=True,
            enable_thinking=True,
            consensus_models=["smart", "reasoning"],
        ),
        "deep_think": OperationalMode(
            name="deep_think",
            display="Deep Think",
            icon="\U0001f9e0",  # brain
            description="Extended thinking with escalation strategy",
            tier_preference=["deep_think", "cloud_best", "reasoning"],
            reasoning_strategy="escalation",
            reasoning_depth=5,
            temperature_override=0.3,
            enable_critic=True,
            enable_thinking=True,
            max_tokens_override=8192,
            memory_tiers=["episodic", "semantic", "procedural", "working"],
        ),
        "stealth": OperationalMode(
            name="stealth",
            display="Stealth Mode",
            icon="\U0001f575\ufe0f",  # detective
            description="Privacy-max: local-only models, no cloud, no web",
            tier_preference=["smart", "fast", "reasoning"],
            reasoning_strategy="direct",
            reasoning_depth=1,
            enable_web_search=False,
            memory_tiers=["episodic"],
            rules=["privacy_local_only"],
        ),
        "custom": OperationalMode(
            name="custom",
            display="Custom Mode",
            icon="\u2699\ufe0f",  # gear
            description="User-defined mode (configure via settings)",
            tier_preference=["smart"],
            reasoning_strategy="direct",
            reasoning_depth=1,
        ),
    }
