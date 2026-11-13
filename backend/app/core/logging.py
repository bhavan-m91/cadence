"""structlog JSON logging with a scrubber so journal content never reaches logs (NFR-05)."""

import logging
import sys

import structlog

SCRUBBED_KEYS = {"raw_text", "description", "title", "transcript", "password", "new_password", "token", "access_token"}


def _scrub(_, __, event_dict: dict) -> dict:
    for key in list(event_dict):
        if key in SCRUBBED_KEYS:
            event_dict[key] = "[scrubbed]"
    return event_dict


def configure_logging(env: str = "development") -> None:
    renderer = structlog.dev.ConsoleRenderer() if env == "development" else structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _scrub,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
