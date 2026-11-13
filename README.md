# Cadence

A personal time tracker and life-analytics app. Log what happened in a day, see it on a 24-hour calendar, and (in later phases) compare it with your Ideal Day and Week.

This repository implements the **Cadence PRD V1.0**. **Phases 0 to 4B are built** (foundation, core data and manual logging, the AI journal, Ideal Day & Week, analytics and the Overview dashboards). Deploy and hardening are next. See [Status](#status).

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
| 2 AI journal | Done. Voice input works in every browser: live dictation where the browser has speech recognition (Chrome, Edge, Safari), otherwise a recording the server transcribes (needs `OPENAI_API_KEY`; audio is never stored). Journal composer (dictate/type, autosave + offline draft), background worker, extraction pipeline with deterministic time/tag/task resolution, review screen, all-or-nothing idempotent commit, history and entry pages. Needs `ANTHROPIC_API_KEY`; without one a built-in offline reader runs in a labelled demo mode. |
| 3 Ideal Day & Week | Done. Day and week editors, 24h/168h validation, effective-dated versions, pace and status against the week so far (E-70..E-73). |
| 4 / 4B Analytics | Done. Day, week, overview, breakdown and trends endpoints (E-74..E-78) with ETag/304, deterministic banners, adherence, sleep by wake date, focus and streaks. Overview dashboards for day and week: KPIs, actual vs Ideal, work vs personal, 24h coverage, sleep, focus, 8-week trend, 26-week focus heatmap, treemap, top tasks, tag limits, deadlines. Every chart has a table view. `make seed-demo` fills an account with half a year of data. |
| 5 Hardening | Not started (RLS, backup drill, load test). The backup script and restore runbook are written but **never run**. |

Tests: 227 backend (real Postgres: tenant isolation, DST fixtures, time resolver, extraction pipeline, review/commit, Ideal) and 47 frontend. The labelled extraction set (`python -m app.ai.eval.run_eval`) has 16 cases; the PRD asks for 40.

### Known gaps in what exists

- `mypy` reports many errors (nullable `placed`/`unplaced` columns). CI runs it as advisory. Ruff, ESLint and `tsc` are clean and blocking.
- Docker and the Dockerfile were not built here (no Docker on the dev machine); the backend wheel installs and imports.
- Calendar side panels from the design (agenda, mini-month, tag totals) are not built. Dependencies and Team screens are out of V1.0 per the PRD.
- The AI worker is a small Postgres queue (see DECISIONS), not Procrastinate.
- The live Anthropic path has not been verified end to end (the key supplied during development was rejected with 401). The offline reader and recorded fixtures cover the code paths.
- Rate limiting is in-process (fine for one API instance; use a shared store if scaled out).

See [docs/DECISIONS.md](docs/DECISIONS.md) for the choices made where the PRD or design was silent or inconsistent.
