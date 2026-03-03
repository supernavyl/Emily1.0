"""
Emily Perception & Agent Message Bus.

Two logical buses are implemented here:
1. PerceptionBus  — inbound sensory events flowing into the attention router
2. AgentBus       — inter-agent task delegation messages

Both buses are built on ZeroMQ PUB/SUB + PUSH/PULL patterns, bridged into
Python asyncio via zmq.asyncio. All messages are serialized as MessagePack
(fast, typed binary) with a JSON fallback.

Message envelope format (all buses):
{
    "id": str (UUID4),
    "sender": str,
    "recipient": str | "broadcast",
    "type": str,
    "payload": dict,
    "priority": int (0-4),
    "timestamp": float (UTC epoch),
    "task_id": str | None,
    "deadline_ms": int | None,
    "context_refs": list[str],
}
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import zmq
import zmq.asyncio

from observability.logger import get_logger
from observability.metrics import AGENT_QUEUE_DEPTH

log = get_logger(__name__)

_zmq_context: zmq.asyncio.Context | None = None


def get_zmq_context() -> zmq.asyncio.Context:
    """Return (and lazily create) the shared ZeroMQ asyncio context."""
    global _zmq_context
    if _zmq_context is None:
        _zmq_context = zmq.asyncio.Context()
    return _zmq_context


class Priority(IntEnum):
    """Priority levels for the agent task queue."""

    EMERGENCY = 0
    REALTIME = 1
    ACTIVE = 2
    BACKGROUND = 3
    IDLE = 4


@dataclass
class Message:
    """Typed message envelope for both perception events and agent tasks."""

    type: str
    payload: dict[str, Any]
    sender: str = "system"
    recipient: str = "broadcast"
    priority: Priority = Priority.ACTIVE
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    deadline_ms: int | None = None
    context_refs: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_bytes(self) -> bytes:
        """Serialize to JSON bytes for ZMQ transport."""
        return json.dumps(
            {
                "id": self.id,
                "sender": self.sender,
                "recipient": self.recipient,
                "type": self.type,
                "payload": self.payload,
                "priority": int(self.priority),
                "timestamp": self.timestamp,
                "task_id": self.task_id,
                "deadline_ms": self.deadline_ms,
                "context_refs": self.context_refs,
            }
        ).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> Message:
        """Deserialize a Message from JSON bytes."""
        raw = json.loads(data.decode())
        return cls(
            id=raw.get("id", str(uuid.uuid4())),
            sender=raw.get("sender", "unknown"),
            recipient=raw.get("recipient", "broadcast"),
            type=raw["type"],
            payload=raw.get("payload", {}),
            priority=Priority(raw.get("priority", Priority.ACTIVE)),
            task_id=raw.get("task_id") or str(uuid.uuid4()),
            deadline_ms=raw.get("deadline_ms"),
            context_refs=raw.get("context_refs", []),
            timestamp=raw.get("timestamp", time.time()),
        )


MessageHandler = Callable[[Message], Coroutine[Any, Any, None]]


class PerceptionBus:
    """
    ZeroMQ PUB/SUB bus for sensory perception events.

    Perception producers (audio, vision, telemetry) publish tagged events.
    The attention router subscribes to all events and dispatches them.
    """

    def __init__(self, pub_port: int = 5556, sub_port: int = 5557) -> None:
        """
        Args:
            pub_port: Port for perception producers to push events.
            sub_port: Port for subscribers (router) to receive events.
        """
        self._pub_port = pub_port
        self._sub_port = sub_port
        self._ctx = get_zmq_context()
        self._pub_socket: zmq.asyncio.Socket | None = None
        self._sub_socket: zmq.asyncio.Socket | None = None
        self._running = False
        self._brain_hub: Any | None = None

    def set_brain_hub(self, hub: Any) -> None:
        """Attach a BrainEventHub for live event mirroring."""
        self._brain_hub = hub

    async def start_publisher(self) -> None:
        """Initialize the publisher socket. Called by producers."""
        self._pub_socket = self._ctx.socket(zmq.PUSH)
        self._pub_socket.bind(f"tcp://127.0.0.1:{self._pub_port}")
        log.info("perception_bus_publisher_started", port=self._pub_port)

    async def start_subscriber(self) -> None:
        """Initialize the subscriber socket. Called by the router."""
        self._sub_socket = self._ctx.socket(zmq.PULL)
        self._sub_socket.connect(f"tcp://127.0.0.1:{self._pub_port}")
        log.info("perception_bus_subscriber_started", port=self._pub_port)
        self._running = True

    async def publish(
        self, event_type: str, payload: dict[str, Any], priority: Priority = Priority.ACTIVE
    ) -> None:
        """
        Publish a perception event.

        Args:
            event_type: Semantic type tag (e.g., "audio.speech_detected").
            payload: Event-specific data.
            priority: Priority level for the attention router.
        """
        if self._pub_socket is None:
            raise RuntimeError("PerceptionBus publisher not started")
        msg = Message(type=event_type, payload=payload, priority=priority)
        await self._pub_socket.send(msg.to_bytes())
        log.debug("perception_event_published", type=event_type, priority=int(priority))

        if self._brain_hub is not None:
            await self._brain_hub.emit("perception", event_type, payload)

    async def receive(self) -> Message:
        """
        Receive the next perception event. Blocks until one is available.

        Returns:
            The next Message from the perception bus.
        """
        if self._sub_socket is None:
            raise RuntimeError("PerceptionBus subscriber not started")
        raw = await self._sub_socket.recv()
        return Message.from_bytes(raw)

    async def iter_events(self) -> AsyncIterator[Message]:
        """Async generator that yields perception events indefinitely."""
        while self._running:
            try:
                yield await self.receive()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("perception_bus_receive_error", error=str(exc))
                await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Shut down the bus sockets."""
        self._running = False
        if self._pub_socket:
            self._pub_socket.close()
        if self._sub_socket:
            self._sub_socket.close()
        log.info("perception_bus_stopped")


class AgentBus:
    """
    ZeroMQ PUSH/PULL bus for inter-agent task delegation.

    Agents send messages via push; each agent has a dedicated PULL socket
    registered under its name. A router task forwards messages to the correct
    agent queue.
    """

    def __init__(self, port: int = 5555) -> None:
        """
        Args:
            port: Base port for the agent bus router.
        """
        self._port = port
        self._ctx = get_zmq_context()
        self._push_socket: zmq.asyncio.Socket | None = None
        self._pull_socket: zmq.asyncio.Socket | None = None
        self._handlers: dict[str, MessageHandler] = {}
        self._running = False
        self._queue: asyncio.PriorityQueue[tuple[int, Message]] = asyncio.PriorityQueue()
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._brain_hub: Any | None = None
        self._event_recorder: Any | None = None  # EventRecorder for full payload capture

    def set_brain_hub(self, hub: Any) -> None:
        """Attach a BrainEventHub for live event mirroring."""
        self._brain_hub = hub

    def set_event_recorder(self, recorder: Any) -> None:
        """Attach an EventRecorder for full message payload capture."""
        self._event_recorder = recorder

    async def start(self) -> None:
        """Initialize both push and pull sockets."""
        self._push_socket = self._ctx.socket(zmq.PUSH)
        self._push_socket.bind(f"tcp://127.0.0.1:{self._port}")

        self._pull_socket = self._ctx.socket(zmq.PULL)
        self._pull_socket.connect(f"tcp://127.0.0.1:{self._port}")

        self._running = True
        log.info("agent_bus_started", port=self._port)

    def register_handler(self, agent_name: str, handler: MessageHandler) -> None:
        """
        Register an async message handler for a named agent.

        Args:
            agent_name: The agent's unique name (e.g., "ConversationAgent").
            handler: Async callable that processes a Message.
        """
        self._handlers[agent_name] = handler
        log.debug("agent_handler_registered", agent=agent_name)

    async def send(self, message: Message) -> None:
        """
        Send a message to the agent bus.

        Args:
            message: The Message to dispatch.
        """
        if self._push_socket is None:
            raise RuntimeError("AgentBus not started")
        await self._push_socket.send(message.to_bytes())
        AGENT_QUEUE_DEPTH.inc()

        # Record full payload for replay debugger
        if self._event_recorder is not None:
            with contextlib.suppress(Exception):
                self._event_recorder.record_bus_message(
                    "send",
                    {
                        "id": message.id,
                        "sender": message.sender,
                        "recipient": message.recipient,
                        "type": message.type,
                        "payload": message.payload,
                        "priority": int(message.priority),
                        "task_id": message.task_id,
                        "deadline_ms": message.deadline_ms,
                        "context_refs": message.context_refs,
                    },
                )

        log.debug(
            "agent_message_sent",
            sender=message.sender,
            recipient=message.recipient,
            type=message.type,
            task_id=message.task_id,
        )

    async def send_to(
        self,
        recipient: str,
        msg_type: str,
        payload: dict[str, Any],
        sender: str = "system",
        priority: Priority = Priority.ACTIVE,
        task_id: str | None = None,
        context_refs: list[str] | None = None,
        deadline_ms: int | None = None,
    ) -> str:
        """
        Convenience method to build and send a typed message.

        Returns:
            The generated task_id for tracking.
        """
        msg = Message(
            type=msg_type,
            payload=payload,
            sender=sender,
            recipient=recipient,
            priority=priority,
            task_id=task_id or str(uuid.uuid4()),
            deadline_ms=deadline_ms,
            context_refs=context_refs or [],
        )
        await self.send(msg)
        return msg.task_id

    async def _receive_loop(self) -> None:
        """Internal loop: pull from ZMQ and dispatch to registered handlers."""
        while self._running:
            try:
                raw = await self._pull_socket.recv()  # type: ignore[union-attr]
                msg = Message.from_bytes(raw)
                AGENT_QUEUE_DEPTH.dec()

                # Record full payload for replay debugger
                if self._event_recorder is not None:
                    with contextlib.suppress(Exception):
                        self._event_recorder.record_bus_message(
                            "recv",
                            {
                                "id": msg.id,
                                "sender": msg.sender,
                                "recipient": msg.recipient,
                                "type": msg.type,
                                "payload": msg.payload,
                                "priority": int(msg.priority),
                                "task_id": msg.task_id,
                                "deadline_ms": msg.deadline_ms,
                                "context_refs": msg.context_refs,
                            },
                        )

                handler = self._handlers.get(msg.recipient) or self._handlers.get("*")
                if handler is None:
                    log.warning("no_handler_for_agent", recipient=msg.recipient)
                    continue

                if self._brain_hub is not None:
                    await self._brain_hub.emit(
                        "agent",
                        "message",
                        {
                            "sender": msg.sender,
                            "recipient": msg.recipient,
                            "type": msg.type,
                            "task_id": msg.task_id,
                            "priority": int(msg.priority),
                        },
                    )

                task = asyncio.create_task(handler(msg))
                self._handler_tasks.add(task)
                task.add_done_callback(self._on_handler_done)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("agent_bus_dispatch_error", error=str(exc))

    def _on_handler_done(self, task: asyncio.Task[None]) -> None:
        """Callback: log exceptions from handler tasks and clean up."""
        self._handler_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error("agent_handler_exception", error=str(exc), exc_type=type(exc).__name__)

    async def run(self) -> None:
        """Start the message dispatch loop. Run as a background task."""
        await self._receive_loop()

    def stop(self) -> None:
        """Shut down the bus."""
        self._running = False
        if self._push_socket:
            self._push_socket.close()
        if self._pull_socket:
            self._pull_socket.close()
        log.info("agent_bus_stopped")
