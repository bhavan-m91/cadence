import pytest
from sqlalchemy import text

from app.services import auth_service, email_service
from tests.factories import PASSWORD, signup

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def test_register_sets_refresh_cookie_and_sends_verification(client):
    r = await client.post(f"{API}/auth/register", json={"email": "Ana@Example.com", "password": PASSWORD, "display_name": "Ana", "timezone": "Asia/Kolkata"})
    assert r.status_code == 201
    body = r.json()["data"]
    assert body["user"]["email_verified"] is False and body["user"]["onboarding_completed"] is False
    cookie = r.headers["set-cookie"].lower()
    assert "refresh_token=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "path=/api/v1/auth" in cookie
    assert [m.kind for m in email_service.OUTBOX] == ["verify_email"]
    assert r.headers["x-request-id"] and r.headers["x-content-type-options"] == "nosniff"


async def test_register_rejects_duplicates_case_insensitively_and_weak_passwords(client):
    await signup(client, email="dup@example.com", onboard=False)
    r = await client.post(f"{API}/auth/register", json={"email": "DUP@example.com", "password": PASSWORD, "display_name": "X", "timezone": "Asia/Kolkata"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"
    r = await client.post(f"{API}/auth/register", json={"email": "new@example.com", "password": "password1234", "display_name": "X", "timezone": "Asia/Kolkata"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"
    r = await client.post(f"{API}/auth/register", json={"email": "new@example.com", "password": PASSWORD, "display_name": "X", "timezone": "Mars/Base"})
    assert r.status_code == 422 and r.json()["error"]["details"]["fields"][0]["path"] == "timezone"


async def test_register_creates_three_system_roots(client):
    p = await signup(client, onboard=False)
    r = await client.get(f"{API}/categories", headers=p.headers)
    roots = r.json()["data"]
    assert sorted(n["name"] for n in roots) == ["Personal", "Sleep", "Work"]
    assert all(n["is_system"] and n["depth"] == 1 for n in roots)


async def test_login_never_reveals_whether_email_exists(client):
    p = await signup(client, onboard=False)
    bad_pw = await client.post(f"{API}/auth/login", json={"email": p.email, "password": "wrong-password-1"})
    no_user = await client.post(f"{API}/auth/login", json={"email": "ghost@example.com", "password": "wrong-password-1"})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json()["error"]["code"] == no_user.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert bad_pw.json()["error"]["message"] == no_user.json()["error"]["message"]
    ok = await client.post(f"{API}/auth/login", json={"email": p.email, "password": PASSWORD, "remember": True})
    assert ok.status_code == 200 and "max-age=2592000" in ok.headers["set-cookie"].lower()
    session = await client.post(f"{API}/auth/login", json={"email": p.email, "password": PASSWORD, "remember": False})
    assert "max-age" not in session.headers["set-cookie"].lower()


async def test_ac001_login_rate_limit_blocks_even_the_correct_password(client):
    p = await signup(client, onboard=False)
    for _ in range(5):
        r = await client.post(f"{API}/auth/login", json={"email": p.email, "password": "wrong-password-1"})
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json={"email": p.email, "password": "wrong-password-1"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    r = await client.post(f"{API}/auth/login", json={"email": p.email, "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"


async def test_ac003_refresh_rotation_and_reuse_revokes_the_family(client):
    p = await signup(client, onboard=False)
    first = p.refresh_cookie
    client.cookies.clear()
    r1 = await client.post(f"{API}/auth/refresh", cookies={"refresh_token": first})
    assert r1.status_code == 200 and r1.json()["data"]["access_token"]
    second = r1.cookies.get("refresh_token")
    assert second and second != first
    client.cookies.clear()
    reuse = await client.post(f"{API}/auth/refresh", cookies={"refresh_token": first})
    assert reuse.status_code == 401 and reuse.json()["error"]["code"] == "INVALID_TOKEN"
    client.cookies.clear()
    newer = await client.post(f"{API}/auth/refresh", cookies={"refresh_token": second})
    assert newer.status_code == 401  # the newer token of the family also stopped working


async def test_logout_revokes_session_and_everywhere_revokes_all(client):
    p = await signup(client, onboard=False)
    other = await client.post(f"{API}/auth/login", json={"email": p.email, "password": PASSWORD, "remember": True})
    other_cookie = other.cookies.get("refresh_token")
    client.cookies.clear()
    r = await client.post(f"{API}/auth/logout", json={"all": False}, cookies={"refresh_token": p.refresh_cookie})
    assert r.status_code == 200
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/refresh", cookies={"refresh_token": p.refresh_cookie})).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", cookies={"refresh_token": other_cookie})).status_code == 200  # untouched
    client.cookies.clear()
    third = await client.post(f"{API}/auth/login", json={"email": p.email, "password": PASSWORD, "remember": True})
    await client.post(f"{API}/auth/logout", json={"all": True}, cookies={"refresh_token": third.cookies.get("refresh_token")})
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/refresh", cookies={"refresh_token": other_cookie})).status_code == 401


async def test_protected_routes_need_a_valid_bearer(client):
    assert (await client.get(f"{API}/users/me")).status_code == 401
    r = await client.get(f"{API}/users/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_verify_email_is_single_use(client):
    p = await signup(client, onboard=False)
    token = email_service.OUTBOX[-1].link.split("token=")[1]
    assert (await client.post(f"{API}/auth/verify-email", json={"token": token})).status_code == 200
    me = await client.get(f"{API}/users/me", headers=p.headers)
    assert me.json()["data"]["email_verified"] is True
    again = await client.post(f"{API}/auth/verify-email", json={"token": token})
    assert again.status_code == 400 and again.json()["error"]["code"] == "INVALID_TOKEN"


async def test_ac004_password_reset_link_works_once_and_revokes_sessions(client):
    p = await signup(client, onboard=False)
    unknown = await client.post(f"{API}/auth/password/forgot", json={"email": "nobody@example.com"})
    known = await client.post(f"{API}/auth/password/forgot", json={"email": p.email})
    assert unknown.status_code == known.status_code == 200 and unknown.json() == known.json()
    assert [m.kind for m in email_service.OUTBOX if m.kind == "reset_password"] == ["reset_password"]
    token = email_service.OUTBOX[-1].link.split("token=")[1]
    new_pw = "a brand new passphrase"
    assert (await client.post(f"{API}/auth/password/reset", json={"token": token, "password": new_pw})).status_code == 200
    second = await client.post(f"{API}/auth/password/reset", json={"token": token, "password": "another passphrase 2"})
    assert second.status_code == 400 and second.json()["error"]["code"] == "INVALID_TOKEN"
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/refresh", cookies={"refresh_token": p.refresh_cookie})).status_code == 401  # FR-008
    assert (await client.post(f"{API}/auth/login", json={"email": p.email, "password": PASSWORD})).status_code == 401
    assert (await client.post(f"{API}/auth/login", json={"email": p.email, "password": new_pw})).status_code == 200


async def test_change_password_requires_current_password(client):
    p = await signup(client, onboard=False)
    bad = await client.post(f"{API}/auth/password/change", headers=p.headers, json={"current_password": "nope-nope-nope", "new_password": "a brand new passphrase"})
    assert bad.status_code == 401
    ok = await client.post(f"{API}/auth/password/change", headers=p.headers, json={"current_password": PASSWORD, "new_password": "a brand new passphrase"})
    assert ok.status_code == 200 and "refresh_token=" in ok.headers["set-cookie"]


async def test_profile_and_preferences(client):
    p = await signup(client, onboard=False)
    r = await client.patch(f"{API}/users/me", headers=p.headers, json={"display_name": "  Bhavan  ", "role_title": "Founder", "theme": "dark", "timezone": "Europe/London"})
    assert r.status_code == 200 and r.json()["data"]["display_name"] == "Bhavan" and r.json()["data"]["theme"] == "dark"
    bad = await client.patch(f"{API}/users/me", headers=p.headers, json={"timezone": "Nope/Zone"})
    assert bad.status_code == 422
    prefs = (await client.get(f"{API}/users/me/preferences", headers=p.headers)).json()["data"]
    assert prefs["week_start"] == 1 and prefs["gap_min_minutes"] == 10 and prefs["office_start_minute"] == 540
    r = await client.patch(f"{API}/users/me/preferences", headers=p.headers, json={"week_start": 7, "time_format": "24h"})
    assert r.json()["data"]["week_start"] == 7 and r.json()["data"]["time_format"] == "24h"
    assert (await client.patch(f"{API}/users/me/preferences", headers=p.headers, json={"office_start_minute": 1000, "office_end_minute": 900})).status_code == 422
    events = (await client.get(f"{API}/users/me/auth-events", headers=p.headers)).json()["data"]
    assert isinstance(events, list)


async def test_google_sign_in_links_only_verified_emails(client, monkeypatch):
    await signup(client, email="linked@example.com", onboard=False)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "google_client_id", "cid")
    start = await client.get(f"{API}/auth/google/start?redirect=/calendar", follow_redirects=False)
    assert start.status_code == 302 and "accounts.google.com" in start.headers["location"]
    state = start.headers["location"].split("state=")[1].split("&")[0]

    async def verified(code):
        return {"sub": "g-1", "email": "linked@example.com", "email_verified": True, "name": "Linked"}

    monkeypatch.setattr(auth_service, "fetch_google_profile", verified)
    r = await client.get(f"{API}/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith("/calendar") and "refresh_token=" in r.headers["set-cookie"]

    async def unverified(code):
        return {"sub": "g-2", "email": "linked@example.com", "email_verified": False}

    monkeypatch.setattr(auth_service, "fetch_google_profile", unverified)
    r = await client.get(f"{API}/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 400 and r.json()["error"]["code"] == "OAUTH_FAILED"  # AC-006


async def test_google_not_configured_and_open_redirect_guard(client, monkeypatch):
    r = await client.get(f"{API}/auth/google/start", follow_redirects=False)
    assert r.status_code == 501 and r.json()["error"]["code"] == "OAUTH_NOT_CONFIGURED"
    assert auth_service.safe_redirect("//evil.com") == "/" and auth_service.safe_redirect("https://evil.com") == "/"
    assert auth_service.safe_redirect("/tasks?x=1") == "/tasks?x=1"


async def test_ac005_account_deletion_removes_every_row(client, db):
    p = await signup(client)
    token = email_service.OUTBOX[-1].link.split("token=")[1]
    await client.post(f"{API}/auth/verify-email", json={"token": token})
    from tests.factories import log

    r = await log(client, p, "Work block", "2025-06-02", "09:00", "11:00", tag_ids=[p.tags["research"]])
    assert r.status_code == 201
    await client.post(f"{API}/tasks", headers=p.headers, json={"title": "A task"})
    await client.post(f"{API}/projects", headers=p.headers, json={"name": "Proj"})

    wrong = await client.request("DELETE", f"{API}/users/me", headers=p.headers, json={"password": PASSWORD, "confirm": "nope"})
    assert wrong.status_code == 422
    bad_pw = await client.request("DELETE", f"{API}/users/me", headers=p.headers, json={"password": "wrong-password-1", "confirm": "DELETE"})
    assert bad_pw.status_code == 401
    done = await client.request("DELETE", f"{API}/users/me", headers=p.headers, json={"password": PASSWORD, "confirm": "DELETE"})
    assert done.status_code == 204

    tables = (await db.execute(text("SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='user_id'"))).scalars().all()
    assert len(tables) >= 20
    for t in tables:
        n = (await db.execute(text(f"SELECT count(*) FROM {t} WHERE user_id = :u"), {"u": p.id})).scalar_one()
        assert n == 0, f"{t} still has rows"
    assert (await db.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": p.id})).scalar_one() == 0
    assert [m.kind for m in email_service.OUTBOX][-1] == "account_deleted"
    assert (await client.get(f"{API}/users/me", headers=p.headers)).status_code == 401


async def test_deletion_and_export_need_a_verified_email(client):
    p = await signup(client)
    r = await client.request("DELETE", f"{API}/users/me", headers=p.headers, json={"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert (await client.post(f"{API}/users/me/exports", headers=p.headers)).status_code == 403


async def test_error_envelope_for_unknown_route_and_validation(client):
    r = await client.get(f"{API}/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND" and r.json()["error"]["request_id"]
    r = await client.post(f"{API}/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR" and r.json()["error"]["details"]["fields"]


async def test_health_endpoints(client):
    assert (await client.get(f"{API}/healthz")).json() == {"ok": True}
    r = await client.get(f"{API}/readyz")
    assert r.status_code == 200 and r.json()["db"] == "ok"
