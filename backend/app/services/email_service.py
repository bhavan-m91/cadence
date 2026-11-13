"""Transactional email behind one interface. Console backend in development, Resend in production, memory in tests."""

import os
from dataclasses import dataclass

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()


@dataclass
class Message:
    to: str
    subject: str
    text: str
    kind: str
    link: str | None = None


OUTBOX: list[Message] = []


async def send(message: Message) -> None:
    s = get_settings()
    backend = os.environ.get("EMAIL_BACKEND") or ("resend" if s.resend_api_key else "console")
    if backend == "memory":
        OUTBOX.append(message)
    elif backend == "resend":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {s.resend_api_key}"},
                    json={"from": s.email_from, "to": [message.to], "subject": message.subject, "text": message.text},
                )
                res.raise_for_status()
        except Exception:  # noqa: BLE001 - email failure must never break a request
            log.exception("email_send_failed", kind=message.kind)
    else:
        log.info("email_console", kind=message.kind, to=message.to, link=message.link)


def verification_email(to: str, token: str) -> Message:
    link = f"{get_settings().app_base_url}/verify-email?token={token}"
    return Message(to, "Verify your Cadence email", f"Welcome to Cadence. Verify your email: {link}\nThe link works once and expires in 24 hours.", "verify_email", link)


def reset_email(to: str, token: str) -> Message:
    link = f"{get_settings().app_base_url}/reset-password?token={token}"
    return Message(to, "Reset your Cadence password", f"Reset your password: {link}\nThe link works once and expires in 1 hour. If you did not ask for this, ignore this email.", "reset_password", link)


def deletion_email(to: str) -> Message:
    return Message(to, "Your Cadence account was deleted", "Your Cadence account and all its data were deleted. This cannot be undone.", "account_deleted")
