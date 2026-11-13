# Cadence

A personal time tracker and life-analytics app. Log what happened in a day, see it on a 24-hour calendar, and (in later phases) compare it with your Ideal Day and Week.

This repository implements the **Cadence PRD V1.0**. **Phases 0 and 1 are built** (foundation + core data and manual logging). Journal/AI, Ideal editors, analytics and hardening are the next phases. See [Status](#status).

| | |
|---|---|
| Frontend | React 18, TypeScript, Vite, React Router, TanStack Query, Zustand, React Hook Form + Zod, Tailwind (CSS-variable tokens from the design file), Radix primitives, PWA |
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + Alembic |
| Database | PostgreSQL 16 (`btree_gist`, `pg_trgm`, `citext`, `pgcrypto`) |
| Auth | Self-managed: argon2id, 15-min JWT access token in memory, rotating refresh cookie with reuse detection, Google OIDC |

## Quick start

Prerequisites: Python 3.12+, Node 22+, PostgreSQL 16 (Homebrew `postgresql@16`, or Docker).

```bash
make setup      # venv + npm install + backend/.env
make dev        # starts a local Postgres on :54329 and migrates it
make api        # terminal 1: API on http://localhost:8000  (docs at /docs)
make web        # terminal 2: app on http://localhost:5173
```

With Docker instead: `cd infra && docker compose up --build` (not exercised in this environment; see [Status](#status)).

Register an account in the app; onboarding seeds categories, example tags and a 24-hour Ideal Day. In development, verification and reset emails are **logged to the API console** unless `RESEND_API_KEY` is set.

```bash
make test       # backend (real Postgres) + frontend
make lint
make gen-api    # regenerate backend/openapi.json and the frontend TypeScript types
```

## What works today

- **Accounts:** register, sign in/out, sign out everywhere, refresh rotation with reuse detection, email verification, forgot/reset/change password, Google sign-in (needs `GOOGLE_CLIENT_ID/SECRET`), profile, preferences, security log, data export (ZIP), account deletion (verified email + password + typed confirmation).
- **Activities:** log exact or "some time between" activities, planned blocks, edit with optimistic locking, split, merge, duplicate, bulk edit, soft delete with Undo, restore, tags, task/project links, full history per activity.
- **Calendar:** 24-hour week/day grid, drag to move, drag edges to resize (5-minute snap), click a hatched gap to fill it, Ideal Day overlay, keyboard navigation, mobile single-day view.
- **Taxonomy:** a 3-level category tree under the built-in Work / Personal / Sleep roots (rename, move, archive, merge with preview, delete), tags with aliases, weekly min/max goals, keyword rules, merge with preview.
- **Tasks & projects:** CRUD, filters, due dates, time rollups by day and week.
- **Correctness guarantees, enforced in the database:** overlapping confirmed activities are impossible (exclusion constraint); every activity is stored once and clipped to local days in a derived `activity_day_slices` table, DST-correct (23h and 25h days sum to real elapsed time); a nightly-style invariant query checks slices against durations.

## Layout

```
backend/    FastAPI app (api -> services -> repositories -> models), migrations, tests
frontend/   React SPA
infra/      docker-compose, backup script, runbooks
docs/       the PRD as exported markdown (docs/prd) and DECISIONS.md
.github/    CI for both apps
```

Layering is strict: routers hold no business rules; services own transactions; repositories always filter by `user_id` (cross-user access returns 404, covered by `tests/security`).

## Status

| PRD phase | State |
|---|---|
| 0 Foundation | Repo, CI, config, error envelope, request ids, health endpoints, migrations, theme, PWA, OpenAPI -> TypeScript. **Not done:** Railway/Cloudflare deploy pipeline, Sentry project wiring (the code path exists, guarded by `SENTRY_DSN`) - both need accounts. |
| 1 Core data & manual logging | Done (E-01..E-19 except Apple, E-33..E-69, E-79/E-80). |
| 2 AI journal | Not started. Schema is in place (`journal_entries`, `ai_processing_jobs`, ...); the Journal screen is a placeholder. |
| 3 Ideal Day & Week | Read side only (seeded day template, calendar overlay). Editors, validation, versioning endpoints (E-70..E-73) are next. |
| 4 / 4B Analytics | Not started. Overview shows server-provided coverage numbers only. |
| 5 Hardening | Not started (RLS, backup drill, load test). The backup script and restore runbook are written but **never run**. |

Tests: 86 backend (real Postgres, covering AC-001..AC-006, AC-028..AC-049 where applicable to this phase, tenant isolation, DST fixtures) and 20 frontend.

### Known gaps in what exists

- `mypy` reports many errors (nullable `placed`/`unplaced` columns). CI runs it as advisory. Ruff, ESLint and `tsc` are clean and blocking.
- Docker and the Dockerfile were not built here (no Docker on the dev machine); the backend wheel installs and imports.
- Calendar side panels from the design (agenda, mini-month, tag totals) are not built. Dependencies and Team screens are out of V1.0 per the PRD.
- Idempotency keys, ETag caching and the Procrastinate worker land with the phases that need them.
- Rate limiting is in-process (fine for one API instance; use a shared store if scaled out).

See [docs/DECISIONS.md](docs/DECISIONS.md) for the choices made where the PRD or design was silent or inconsistent.
