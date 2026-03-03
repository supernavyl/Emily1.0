"""
Unit tests for conversation.fsm — ConversationFSM, VoiceState, ResponseContext.

All external dependencies (observability, perception, numpy) are mocked so
tests run without GPU, audio hardware, or PySide6.
"""

from __future__ import annotations

import time
import types
from dataclasses import fields
from typing import ClassVar
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy / hardware-dependent imports before the module is loaded
# ---------------------------------------------------------------------------
# perception.audio.stream only requires numpy — no hardware deps — so we let
# the real module import. Stubbing it here would leak a MagicMock AudioChunk
# into sys.modules and break any test collected after this file.
from conversation.fsm import ConversationFSM, ResponseContext, VoiceState  # noqa: E402

# ===================================================================
# TestVoiceState
# ===================================================================


class TestVoiceState:
    """Validate that all expected VoiceState enum members exist."""

    _EXPECTED_NAMES: ClassVar[list[str]] = [
        "IDLE",
        "LISTENING",
        "BACKCHANNELING",
        "PROCESSING",
        "FILLING",
        "SPEAKING",
        "INTERRUPTED",
        "ONBOARDING",
    ]

    def test_all_members_present(self) -> None:
        """Every documented state must be a member of VoiceState."""
        member_names = [m.name for m in VoiceState]
        for name in self._EXPECTED_NAMES:
            assert name in member_names, f"Missing VoiceState.{name}"

    def test_member_count(self) -> None:
        """No unexpected states have been silently added."""
        assert len(VoiceState) == len(self._EXPECTED_NAMES)

    @pytest.mark.parametrize("name", _EXPECTED_NAMES)
    def test_members_are_unique(self, name: str) -> None:
        """Each member's value is unique (auto() guarantees it, but verify)."""
        values = [m.value for m in VoiceState]
        assert values.count(VoiceState[name].value) == 1

    def test_enum_identity(self) -> None:
        """Members accessed by name and by value are the same object."""
        for member in VoiceState:
            assert VoiceState(member.value) is member


# ===================================================================
# TestResponseContext
# ===================================================================


class TestResponseContext:
    """Validate the ResponseContext dataclass defaults and custom construction."""

    def test_default_values(self) -> None:
        """A bare ResponseContext() should have documented defaults."""
        ctx = ResponseContext()
        assert ctx.text_spoken == ""
        assert ctx.text_remaining == ""
        assert ctx.topic == ""
        assert ctx.importance == 0.5
        assert ctx.can_resume is False

    def test_custom_values(self) -> None:
        """All fields can be overridden at construction time."""
        ctx = ResponseContext(
            text_spoken="Hello there",
            text_remaining="How are you?",
            topic="greeting",
            importance=0.9,
            can_resume=True,
        )
        assert ctx.text_spoken == "Hello there"
        assert ctx.text_remaining == "How are you?"
        assert ctx.topic == "greeting"
        assert ctx.importance == 0.9
        assert ctx.can_resume is True

    def test_field_names(self) -> None:
        """Ensure the field set hasn't drifted."""
        expected = {"text_spoken", "text_remaining", "topic", "importance", "can_resume"}
        actual = {f.name for f in fields(ResponseContext)}
        assert actual == expected

    def test_equality(self) -> None:
        """Two ResponseContexts with identical values compare equal."""
        a = ResponseContext(text_spoken="hi", importance=0.7)
        b = ResponseContext(text_spoken="hi", importance=0.7)
        assert a == b

    def test_inequality(self) -> None:
        """Different field values produce inequality."""
        a = ResponseContext(topic="weather")
        b = ResponseContext(topic="music")
        assert a != b


# ===================================================================
# TestConversationFSMInit
# ===================================================================


class TestConversationFSMInit:
    """Verify the initial state of a freshly constructed ConversationFSM."""

    def test_initial_state_is_idle(self) -> None:
        """FSM starts in IDLE."""
        fsm = ConversationFSM()
        assert fsm.state is VoiceState.IDLE

    def test_not_running(self) -> None:
        """FSM starts in a non-running state."""
        fsm = ConversationFSM()
        assert fsm.is_running is False

    def test_module_slots_are_none(self) -> None:
        """All pluggable module slots should be None after construction."""
        fsm = ConversationFSM()
        module_attrs = [
            "_audio_capture",
            "_aec",
            "_noise_suppress",
            "_speaker_engine",
            "_streaming_stt",
            "_prosody_analyzer",
            "_emotion_detector",
            "_turn_detector",
            "_interrupt_handler",
            "_backchannel_engine",
            "_rhythm_sync",
            "_emotion_sync",
            "_llm_orchestrator",
            "_tts_engine",
            "_filler_engine",
            "_breath_injector",
            "_latency_budget",
            "_agent_bus",
            "_fleet",
            "_memory",
            "_brain_hub",
            "_onboarding_handler",
        ]
        for attr in module_attrs:
            assert getattr(fsm, attr) is None, f"{attr} should be None"

    def test_current_frame_slots_none(self) -> None:
        """Per-frame state should be None at init."""
        fsm = ConversationFSM()
        assert fsm._current_chunk is None
        assert fsm._current_stt_frame is None
        assert fsm._current_prosody is None
        assert fsm._current_emotion is None

    def test_fast_mode_off(self) -> None:
        """Fast mode defaults to disabled."""
        fsm = ConversationFSM()
        assert fsm._fast_mode is False

    def test_interrupt_config_keys(self) -> None:
        """All documented interrupt config keys are present."""
        fsm = ConversationFSM()
        expected_keys = {
            "energy_threshold",
            "cooldown_s",
            "fade_ms",
            "lookahead_ms",
            "ack_enabled",
            "resume_enabled",
            "resume_expiry_s",
            "adaptive_threshold",
        }
        assert set(fsm._interrupt_config.keys()) == expected_keys

    def test_listeners_list_empty(self) -> None:
        """No transition listeners registered at init."""
        fsm = ConversationFSM()
        assert fsm._listeners == []

    def test_silence_counters(self) -> None:
        """Silence watchdog counters start at zero."""
        fsm = ConversationFSM()
        assert fsm._silence_prompt_count == 0
        assert fsm._last_user_speech_time == 0.0

    def test_state_enter_time_set(self) -> None:
        """State enter time should be roughly 'now'."""
        before = time.monotonic()
        fsm = ConversationFSM()
        after = time.monotonic()
        assert before <= fsm._state_enter_time <= after


# ===================================================================
# TestTransition
# ===================================================================


class TestTransition:
    """Verify ConversationFSM.transition() behaviour."""

    def test_simple_transition(self) -> None:
        """State changes to the requested value."""
        fsm = ConversationFSM()
        fsm.transition(VoiceState.LISTENING)
        assert fsm.state is VoiceState.LISTENING

    def test_previous_state_tracked(self) -> None:
        """_prev_state records the state before transition."""
        fsm = ConversationFSM()
        fsm.transition(VoiceState.LISTENING)
        assert fsm._prev_state is VoiceState.IDLE

    def test_noop_on_same_state(self) -> None:
        """Transitioning to the current state is a no-op."""
        fsm = ConversationFSM()
        original_enter = fsm._state_enter_time
        fsm.transition(VoiceState.IDLE)
        assert fsm._state_enter_time == original_enter

    def test_state_enter_time_updated(self) -> None:
        """Enter time refreshes on a real transition."""
        fsm = ConversationFSM()
        old_time = fsm._state_enter_time
        time.sleep(0.01)
        fsm.transition(VoiceState.PROCESSING)
        assert fsm._state_enter_time > old_time

    def test_listener_called(self) -> None:
        """Registered listeners receive (old, new) on transition."""
        fsm = ConversationFSM()
        calls: list[tuple[VoiceState, VoiceState]] = []
        fsm.on_transition(lambda old, new: calls.append((old, new)))

        fsm.transition(VoiceState.SPEAKING)
        assert len(calls) == 1
        assert calls[0] == (VoiceState.IDLE, VoiceState.SPEAKING)

    def test_multiple_listeners(self) -> None:
        """All listeners are notified."""
        fsm = ConversationFSM()
        a: list[VoiceState] = []
        b: list[VoiceState] = []
        fsm.on_transition(lambda _old, new: a.append(new))
        fsm.on_transition(lambda _old, new: b.append(new))

        fsm.transition(VoiceState.LISTENING)
        assert a == [VoiceState.LISTENING]
        assert b == [VoiceState.LISTENING]

    def test_listener_exception_does_not_propagate(self) -> None:
        """A failing listener must not crash the FSM."""
        fsm = ConversationFSM()
        fsm.on_transition(lambda _o, _n: (_ for _ in ()).throw(ValueError("boom")))

        fsm.transition(VoiceState.PROCESSING)
        assert fsm.state is VoiceState.PROCESSING

    def test_brain_hub_emit_sync_called(self) -> None:
        """When brain_hub is wired, emit_sync is called on transition."""
        fsm = ConversationFSM()
        hub = MagicMock()
        fsm._brain_hub = hub

        fsm.transition(VoiceState.SPEAKING)
        hub.emit_sync.assert_called_once_with(
            "fsm",
            "state_change",
            {"old": "IDLE", "new": "SPEAKING"},
        )

    def test_brain_hub_none_no_error(self) -> None:
        """Transition works fine when brain_hub is None."""
        fsm = ConversationFSM()
        fsm.transition(VoiceState.LISTENING)
        assert fsm.state is VoiceState.LISTENING

    def test_chained_transitions(self) -> None:
        """Multiple sequential transitions update state correctly."""
        fsm = ConversationFSM()
        for s in (VoiceState.LISTENING, VoiceState.PROCESSING, VoiceState.SPEAKING):
            fsm.transition(s)
        assert fsm.state is VoiceState.SPEAKING
        assert fsm._prev_state is VoiceState.PROCESSING


# ===================================================================
# TestConfigure
# ===================================================================


class TestConfigure:
    """Verify ConversationFSM.configure() dependency injection."""

    def test_inject_known_module(self) -> None:
        """Known module names are stored as _<name> attributes."""
        fsm = ConversationFSM()
        mock_fleet = MagicMock()
        fsm.configure(fleet=mock_fleet)
        assert fsm._fleet is mock_fleet

    def test_inject_multiple_modules(self) -> None:
        """Multiple modules can be injected in one call."""
        fsm = ConversationFSM()
        mock_memory = MagicMock()
        mock_hub = MagicMock()
        fsm.configure(memory=mock_memory, brain_hub=mock_hub)
        assert fsm._memory is mock_memory
        assert fsm._brain_hub is mock_hub

    def test_unknown_module_ignored(self) -> None:
        """An unrecognised module name does not create a new attribute."""
        fsm = ConversationFSM()
        fsm.configure(nonexistent_module=MagicMock())
        assert not hasattr(fsm, "_nonexistent_module")

    def test_agent_bus_registers_handler(self) -> None:
        """When agent_bus is provided, register_handler is called for 'tts'."""
        fsm = ConversationFSM()
        mock_bus = MagicMock()
        fsm.configure(agent_bus=mock_bus)
        mock_bus.register_handler.assert_called_once_with("tts", fsm._handle_tts_message)

    def test_agent_bus_none_skips_registration(self) -> None:
        """No handler registration when agent_bus is not among the kwargs."""
        fsm = ConversationFSM()
        mock_fleet = MagicMock()
        fsm.configure(fleet=mock_fleet)
        # No error raised — agent_bus is still None

    def test_configure_overwrites_previous(self) -> None:
        """Calling configure a second time overwrites earlier injections."""
        fsm = ConversationFSM()
        first = MagicMock(name="first")
        second = MagicMock(name="second")
        fsm.configure(fleet=first)
        fsm.configure(fleet=second)
        assert fsm._fleet is second


# ===================================================================
# TestSetFastMode
# ===================================================================


class TestSetFastMode:
    """Verify fast_mode toggle."""

    def test_enable(self) -> None:
        """set_fast_mode(True) enables fast mode."""
        fsm = ConversationFSM()
        fsm.set_fast_mode(True)
        assert fsm._fast_mode is True

    def test_disable(self) -> None:
        """set_fast_mode(False) disables fast mode."""
        fsm = ConversationFSM()
        fsm.set_fast_mode(True)
        fsm.set_fast_mode(False)
        assert fsm._fast_mode is False

    def test_toggle_roundtrip(self) -> None:
        """Toggling on then off returns to the initial state."""
        fsm = ConversationFSM()
        fsm.set_fast_mode(True)
        fsm.set_fast_mode(False)
        assert fsm._fast_mode is False


# ===================================================================
# TestIsSimpleTurn
# ===================================================================


class TestIsSimpleTurn:
    """Verify ConversationFSM._is_simple_turn() heuristic."""

    def _make_fsm(self, fast: bool = True) -> ConversationFSM:
        """Create a ConversationFSM with fast_mode set."""
        fsm = ConversationFSM()
        fsm.set_fast_mode(fast)
        return fsm

    def test_short_greeting(self) -> None:
        """A simple short greeting should be classified as simple."""
        fsm = self._make_fsm()
        assert fsm._is_simple_turn("Hello, how are you?") is True

    def test_empty_string(self) -> None:
        """Empty input is simple (nothing complex)."""
        fsm = self._make_fsm()
        assert fsm._is_simple_turn("") is True

    def test_fast_mode_off_always_false(self) -> None:
        """With fast mode disabled, every turn is non-simple."""
        fsm = self._make_fsm(fast=False)
        assert fsm._is_simple_turn("Hi") is False

    def test_long_text_not_simple(self) -> None:
        """Text over 50 words is not simple."""
        fsm = self._make_fsm()
        long_text = " ".join(["word"] * 51)
        assert fsm._is_simple_turn(long_text) is False

    def test_exactly_50_words_is_simple(self) -> None:
        """Exactly 50 words should still count as simple (boundary)."""
        fsm = self._make_fsm()
        text = " ".join(["word"] * 50)
        assert fsm._is_simple_turn(text) is True

    @pytest.mark.parametrize(
        "keyword",
        [
            "search",
            "find",
            "look up",
            "calculate",
            "code",
            "write",
            "analyze",
            "compare",
            "explain in detail",
            "step by step",
            "debug",
            "refactor",
            "file",
            "open",
            "run",
            "execute",
            "remember",
            "remind",
            "schedule",
            "email",
            "summarize",
            "home assistant",
            "turn on",
            "turn off",
            "set timer",
        ],
    )
    def test_complex_keyword_makes_turn_complex(self, keyword: str) -> None:
        """Any complex keyword anywhere in the text → not simple."""
        fsm = self._make_fsm()
        assert fsm._is_simple_turn(f"Please {keyword} something") is False

    def test_keyword_case_insensitive(self) -> None:
        """Complex keyword detection is case-insensitive."""
        fsm = self._make_fsm()
        assert fsm._is_simple_turn("SEARCH for cats") is False
        assert fsm._is_simple_turn("Search For Cats") is False

    def test_keyword_as_substring(self) -> None:
        """A keyword embedded as a substring still triggers complexity."""
        fsm = self._make_fsm()
        assert fsm._is_simple_turn("I need to refactor this") is False

    def test_no_keyword_short(self) -> None:
        """Short text without complex keywords is simple."""
        fsm = self._make_fsm()
        assert fsm._is_simple_turn("What's the weather like?") is True

    def test_complex_keywords_frozenset(self) -> None:
        """_COMPLEX_KEYWORDS is a frozenset (immutable)."""
        assert isinstance(ConversationFSM._COMPLEX_KEYWORDS, frozenset)
        assert len(ConversationFSM._COMPLEX_KEYWORDS) > 0


# ===================================================================
# TestTranscriptUsability
# ===================================================================


class TestTranscriptUsability:
    """Verify defensive transcript quality checks before LLM response."""

    def test_rejects_repetitive_low_quality_transcript(self) -> None:
        fsm = ConversationFSM()
        fsm._streaming_stt = types.SimpleNamespace(
            config=types.SimpleNamespace(
                streaming_min_final_words=3,
                streaming_min_unique_ratio=0.45,
                streaming_max_repeat_ratio=0.6,
                streaming_short_utterance_confidence=0.8,
            )
        )
        transcript = types.SimpleNamespace(
            words=[
                types.SimpleNamespace(text="we'll"),
                types.SimpleNamespace(text="we'll"),
                types.SimpleNamespace(text="we'll"),
                types.SimpleNamespace(text="we'll"),
                types.SimpleNamespace(text="back"),
                types.SimpleNamespace(text="back"),
            ],
            confidence=0.62,
        )

        ok, reason = fsm._is_transcript_usable(
            transcript,
            "we'll we'll we'll we'll back back",
        )
        assert ok is False
        assert reason in {"low_unique_ratio", "repetitive_tokens"}

    def test_accepts_short_high_confidence_clear_transcript(self) -> None:
        fsm = ConversationFSM()
        fsm._streaming_stt = types.SimpleNamespace(
            config=types.SimpleNamespace(
                streaming_min_final_words=3,
                streaming_min_unique_ratio=0.45,
                streaming_max_repeat_ratio=0.6,
                streaming_short_utterance_confidence=0.8,
            )
        )
        transcript = types.SimpleNamespace(
            words=[
                types.SimpleNamespace(text="hi"),
                types.SimpleNamespace(text="emily"),
            ],
            confidence=0.93,
        )

        ok, reason = fsm._is_transcript_usable(transcript, "hi emily")
        assert ok is True
        assert reason == ""


# ===================================================================
# TestProperties
# ===================================================================


class TestProperties:
    """Verify read-only properties on ConversationFSM."""

    def test_state_property(self) -> None:
        """state returns the current VoiceState."""
        fsm = ConversationFSM()
        assert fsm.state is VoiceState.IDLE
        fsm.transition(VoiceState.LISTENING)
        assert fsm.state is VoiceState.LISTENING

    def test_state_duration_positive(self) -> None:
        """state_duration_s returns a non-negative float."""
        fsm = ConversationFSM()
        assert fsm.state_duration_s >= 0.0

    def test_state_duration_increases(self) -> None:
        """Duration grows over time within the same state."""
        fsm = ConversationFSM()
        d1 = fsm.state_duration_s
        time.sleep(0.02)
        d2 = fsm.state_duration_s
        assert d2 > d1

    def test_state_duration_resets_on_transition(self) -> None:
        """Duration resets to near-zero after a state change."""
        fsm = ConversationFSM()
        time.sleep(0.02)
        fsm.transition(VoiceState.PROCESSING)
        assert fsm.state_duration_s < 0.1

    def test_is_running_false_by_default(self) -> None:
        """is_running is False before run() is called."""
        fsm = ConversationFSM()
        assert fsm.is_running is False

    def test_is_running_reflects_internal_flag(self) -> None:
        """is_running directly reflects _running."""
        fsm = ConversationFSM()
        fsm._running = True
        assert fsm.is_running is True
        fsm._running = False
        assert fsm.is_running is False


# ===================================================================
# TestBackchannelCooldown
# ===================================================================


class TestBackchannelCooldown:
    """Verify cooldown gating for backchannel state transitions."""

    def test_backchannel_allowed_initially(self) -> None:
        fsm = ConversationFSM()
        assert fsm._can_enter_backchanneling(now=10.0) is True

    def test_backchannel_retry_cooldown_after_non_emit(self) -> None:
        fsm = ConversationFSM()
        fsm._mark_backchannel_attempt(emitted=False, now=10.0)
        assert fsm._can_enter_backchanneling(now=10.59) is False
        assert fsm._can_enter_backchanneling(now=10.61) is True

    def test_backchannel_emit_sets_longer_cooldown(self) -> None:
        fsm = ConversationFSM()
        fsm._mark_backchannel_attempt(emitted=True, now=10.0)
        assert fsm._can_enter_backchanneling(now=11.19) is False
        assert fsm._can_enter_backchanneling(now=11.21) is True


# ===================================================================
# TestOnTransition
# ===================================================================


class TestOnTransition:
    """Verify on_transition() listener registration."""

    def test_register_callback(self) -> None:
        """on_transition adds the callback to _listeners."""
        fsm = ConversationFSM()
        cb = MagicMock()
        fsm.on_transition(cb)
        assert cb in fsm._listeners

    def test_callback_receives_correct_args(self) -> None:
        """Callback is invoked with (old_state, new_state)."""
        fsm = ConversationFSM()
        cb = MagicMock()
        fsm.on_transition(cb)
        fsm.transition(VoiceState.SPEAKING)
        cb.assert_called_once_with(VoiceState.IDLE, VoiceState.SPEAKING)

    def test_not_called_on_noop(self) -> None:
        """Callback is NOT invoked when transitioning to the same state."""
        fsm = ConversationFSM()
        cb = MagicMock()
        fsm.on_transition(cb)
        fsm.transition(VoiceState.IDLE)
        cb.assert_not_called()


# ===================================================================
# TestStop
# ===================================================================


class TestStop:
    """Verify the async stop() method."""

    @pytest.mark.asyncio
    async def test_stop_sets_not_running(self) -> None:
        """stop() clears the _running flag."""
        fsm = ConversationFSM()
        fsm._running = True
        await fsm.stop()
        assert fsm.is_running is False

    @pytest.mark.asyncio
    async def test_stop_transitions_to_idle(self) -> None:
        """stop() transitions state back to IDLE."""
        fsm = ConversationFSM()
        fsm._running = True
        fsm._state = VoiceState.SPEAKING
        await fsm.stop()
        assert fsm.state is VoiceState.IDLE
