"""Unit tests for the Message bus system."""

from __future__ import annotations

import json

from core.bus import Message, Priority


def test_message_to_bytes_and_back() -> None:
    """Message serializes to bytes and deserializes correctly."""
    msg = Message(
        type="test.event",
        payload={"key": "value", "count": 42},
        sender="TestAgent",
        recipient="TargetAgent",
        priority=Priority.REALTIME,
    )
    data = msg.to_bytes()
    assert isinstance(data, bytes)

    restored = Message.from_bytes(data)
    assert restored.type == "test.event"
    assert restored.payload["key"] == "value"
    assert restored.payload["count"] == 42
    assert restored.sender == "TestAgent"
    assert restored.recipient == "TargetAgent"
    assert restored.priority == Priority.REALTIME


def test_message_default_priority() -> None:
    """Message defaults to ACTIVE priority."""
    msg = Message(type="ping", payload={})
    assert msg.priority == Priority.ACTIVE


def test_message_ids_are_unique() -> None:
    """Two Messages have different IDs and task_ids."""
    m1 = Message(type="a", payload={})
    m2 = Message(type="b", payload={})
    assert m1.id != m2.id
    assert m1.task_id != m2.task_id


def test_message_json_is_valid() -> None:
    """Message bytes parse as valid JSON."""
    msg = Message(type="test", payload={"nested": {"x": 1}})
    raw = json.loads(msg.to_bytes().decode())
    assert raw["type"] == "test"
    assert raw["payload"]["nested"]["x"] == 1


def test_priority_ordering() -> None:
    """Priority enum values maintain correct ordering (lower = more urgent)."""
    assert Priority.EMERGENCY < Priority.REALTIME < Priority.ACTIVE < Priority.BACKGROUND < Priority.IDLE
