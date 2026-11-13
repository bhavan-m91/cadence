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
