"""
Structured logging setup for Emily using structlog.

All modules should call `get_logger(__name__)` to obtain a bound logger.
Log output is JSON in production and colored console output in development.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    brain_tap: bool = False,
) -> None:
    """
    Configure structlog and stdlib logging to work together.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        log_format: "json" for production, "console" for human-readable dev output.
        brain_tap: If True, install the brain_tap_processor that mirrors
                   log events to the BrainEventHub for the Brain Dashboard.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if brain_tap:
        from observability.brain_tap import brain_tap_processor
        shared_processors.append(brain_tap_processor)

    if log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a structlog bound logger for the given module name.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        A structlog BoundLogger instance.
    """
    return structlog.get_logger(name)  # type: ignore[return-value]


def bind_request_context(request_id: str, user_id: str | None = None) -> None:
    """
    Bind request-scoped context variables for the current async context.

    Args:
        request_id: Unique identifier for the current request/task.
        user_id: Optional user identifier for multi-user logging.
    """
    ctx: dict[str, Any] = {"request_id": request_id}
    if user_id:
        ctx["user_id"] = user_id
    structlog.contextvars.bind_contextvars(**ctx)


def clear_request_context() -> None:
    """Clear all bound context variables for the current async context."""
    structlog.contextvars.clear_contextvars()
