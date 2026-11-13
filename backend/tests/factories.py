"""Helpers that build state through the public API, so tests exercise the same paths as the frontend."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

PASSWORD = "correct horse battery"


@dataclass
class Person:
    email: str
    headers: dict
    id: str
    refresh_cookie: str | None = None
    cats: dict[str, str] = field(default_factory=dict)  # category name -> id
    tags: dict[str, str] = field(default_factory=dict)


async def signup(client, *, email: str | None = None, tz: str = "Asia/Kolkata", onboard: bool = True, seed: str = "default") -> Person:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Test User", "timezone": tz})
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    person = Person(email=email, headers={"Authorization": f"Bearer {data['access_token']}"}, id=data["user"]["id"],
                    refresh_cookie=r.cookies.get("refresh_token"))
    if onboard:
        r = await client.post("/api/v1/users/me/onboarding", headers=person.headers, json={"timezone": tz, "seed": seed, "ideal_day_preset": "balanced"})
        assert r.status_code == 200, r.text
    await load_taxonomy(client, person)
    return person


async def load_taxonomy(client, person: Person) -> None:
    r = await client.get("/api/v1/categories", headers=person.headers)

    def walk(nodes):
        for n in nodes:
            person.cats[n["name"]] = n["id"]
            walk(n["children"])

    walk(r.json()["data"])
    r = await client.get("/api/v1/tags", headers=person.headers)
    person.tags = {t["name"]: t["id"] for t in r.json()["data"]}


def at(day: str, hhmm: str, offset: str = "+05:30") -> str:
    """ISO instant for a local wall-clock time, e.g. at('2025-06-02', '09:30')."""
    return f"{day}T{hhmm}:00{offset}"


async def log(client, person: Person, title: str, day: str, start: str, end: str, category: str = "Deep work", **extra):
    body = {"title": title, "category_id": person.cats[category], "start_at": at(day, start), "end_at": at(day, end), **extra}
    return await client.post("/api/v1/activities", headers=person.headers, json=body)


def utc(y, m, d, hh=0, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


__all__ = ["PASSWORD", "Person", "signup", "load_taxonomy", "log", "at", "utc", "timedelta"]


async def create_entry(client, person, text: str, *, day: str = "2025-06-02", start: str = "09:00", end: str = "18:00", tz: str = "Asia/Kolkata", method: str = "typed"):
    offset = "+05:30" if tz == "Asia/Kolkata" else "+00:00"
    return await client.post("/api/v1/journal-entries", headers=person.headers, json={
        "raw_text": text, "covers_start_at": at(day, start, offset), "covers_end_at": at(day, end, offset), "timezone": tz, "input_method": method})


def idem(key: str | None = None) -> dict:
    return {"Idempotency-Key": key or uuid.uuid4().hex}


async def submit(client, db, person, entry_id: str, provider, *, regenerate: bool = False, hint: str | None = None) -> str:
    """POST /process, then run the queued job exactly as the worker would, using the given provider."""
    from app.workers.tasks_ai import run_job

    body = {"regenerate": regenerate, **({"user_hint": hint} if hint else {})}
    r = await client.post(f"/api/v1/journal-entries/{entry_id}/process", headers={**person.headers, **idem()}, json=body)
    assert r.status_code == 202, r.text
    job_id = r.json()["data"]["job_id"]
    await run_job(db, uuid.UUID(job_id), provider)
    return job_id
