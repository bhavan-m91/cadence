# 9 · Repository & Folder Structure

One monorepo, two deployable apps. Layering is strict: **api (routers) → services → repositories → models**, with `ai/` and `analytics/` as pure-logic packages that services call. Routers never contain business rules; repositories never decide outcomes; `ai/` and `analytics/` never touch HTTP.

## 9.1 Top level

```text
cadence/
├── backend/                  FastAPI app, worker, migrations, tests
├── frontend/                 React SPA
├── infra/                    Dockerfiles for local compose, backup script, runbooks
│   ├── docker-compose.yml        local Postgres + api + worker + frontend dev
│   ├── backup/pg_backup.sh       nightly pg_dump → age encryption → R2
│   └── runbooks/                 restore.md, incident.md, release.md
├── docs/                     this PRD (exported), ADRs, OpenAPI snapshot
├── .github/workflows/        ci-backend.yml, ci-frontend.yml, deploy.yml, eval.yml
├── Makefile                  make dev, test, lint, migrate, gen-api
└── README.md
```

## 9.2 Backend tree

```text
backend/
├── pyproject.toml            dependencies (uv), ruff, mypy, pytest config
├── Dockerfile                one image, two commands (api, worker)
├── alembic.ini
├── .env.example              every setting with a safe placeholder
├── migrations/
│   ├── env.py
│   └── versions/
│       ├── 0001_extensions_enums.py      btree_gist, pg_trgm, citext, pgcrypto, enum types
│       ├── 0002_identity.py              users, user_preferences, refresh_tokens, email_tokens, auth_events
│       ├── 0003_taxonomy_tasks.py        categories, tags, tag_aliases, keyword_rules, projects, tasks
│       ├── 0004_journal_ai_activities.py journal_entries, revisions, ai_processing_jobs, activities, activity_tags, slices, events
│       ├── 0005_ideal_support.py         ideal_templates, ideal_allocations, export_jobs, idempotency_keys
│       └── 0006_row_level_security.py    Phase 5: RLS policies and FORCE ROW LEVEL SECURITY
├── app/
│   ├── main.py
│   ├── core/       config.py database.py security.py errors.py logging.py middleware.py rate_limit.py idempotency.py time.py
│   ├── api/
│   │   ├── deps.py
│   │   └── v1/     router.py auth.py users.py journal.py review.py transcriptions.py activities.py timeline.py
│   │               tasks.py projects.py categories.py tags.py keyword_rules.py ideal.py analytics.py exports.py health.py
│   ├── models/     base.py user.py journal.py ai_job.py activity.py taxonomy.py task.py ideal.py support.py
│   ├── schemas/    common.py auth.py user.py journal.py review.py activity.py timeline.py task.py taxonomy.py ideal.py analytics.py
│   ├── repositories/ base.py users.py journal.py ai_jobs.py activities.py slices.py events.py taxonomy.py tasks.py ideal.py analytics_queries.py idempotency.py
│   ├── services/   auth_service.py user_service.py onboarding_service.py journal_service.py review_service.py
│   │               activity_service.py slice_service.py timeline_service.py task_service.py category_service.py tag_service.py
│   │               ideal_service.py export_service.py email_service.py transcription_service.py
│   ├── ai/
│   │   ├── providers/  base.py anthropic_provider.py fake_provider.py stt_openai.py
│   │   ├── prompts/extract_activities/v1.0.0/  system.md user.md.j2 schema.json CHANGELOG.md
│   │   ├── output_models.py context_builder.py extraction_pipeline.py quote_verifier.py time_resolver.py
│   │   ├── tag_matcher.py task_matcher.py detectors.py confidence.py clarifications.py
│   │   └── eval/       dataset/*.jsonl run_eval.py metrics.py
│   ├── analytics/  metrics.py day_analytics.py week_analytics.py overview.py breakdown.py trends.py insights.py sleep.py
│   ├── workers/    app.py tasks_ai.py tasks_export.py tasks_email.py tasks_maintenance.py
│   └── utils/      text.py similarity.py
└── tests/          conftest.py factories.py unit/ integration/ api/ ai/ analytics/ security/
```

## 9.3 Backend files and what each contains

### Core

| File | Contains | Why it exists |
| --- | --- | --- |
| `app/main.py` | `create_app()`: FastAPI instance, middleware, exception handlers, router mount, Sentry init | One place that assembles the service |
| `core/config.py` | `Settings` (pydantic-settings) for database URL, JWT secret, cookie settings, CORS origin, LLM and STT keys and models, limits | Typed, validated configuration; fails fast on missing secrets |
| `core/database.py` | async engine, session factory, `get_session`, `session_scope`, RLS session variable helper | Transaction and connection management |
| `core/security.py` | argon2 hashing, JWT create / decode, opaque token generation and hashing | Security primitives isolated and unit-tested |
| `core/errors.py` | `AppError` hierarchy with `code`, `status`, `details`; handler registration | One mapping from exceptions to the error envelope |
| `core/logging.py` | structlog setup, field scrubber for `raw_text`, `description`, `title`, `transcript` | Guarantees NFR-05 |
| `core/middleware.py` | request id, access log, body-size limit, security headers | Cross-cutting HTTP behaviour |
| `core/rate_limit.py` | `rate_limit()` dependency with sliding window per key | Auth, processing, transcription limits (FR-150) |
| `core/idempotency.py` | `run_idempotent()` wrapper over `idempotency_keys` | Safe retries on process and commit |
| `core/time.py` | local-date and DST-safe helpers | One implementation of time rules used everywhere |

### API routers (`app/api/v1/`)

| File | Endpoints | Notes |
| --- | --- | --- |
| `deps.py` (in `api/`) | `get_current_user`, `get_db`, `pagination_params`, `idempotency_key` | Shared dependencies |
| `router.py` | mounts all routers under `/api/v1` |  |
| `auth.py` | E-01–E-10 | thin; calls `auth_service` |
| `users.py` | E-11–E-19 | profile, preferences, exports, deletion, onboarding |
| `journal.py` | E-20–E-26, E-28, E-29 | entries, stats, process, job polling |
| `review.py` | E-30–E-32 | review, answers, commit |
| `transcriptions.py` | E-27 | multipart upload |
| `activities.py` | E-33–E-45 |  |
| `timeline.py` | E-46 |  |
| `tasks.py`, `projects.py` | E-47–E-54 |  |
| `categories.py`, `tags.py`, `keyword_rules.py` | E-55–E-69 |  |
| `ideal.py` | E-70–E-73 |  |
| `analytics.py` | E-74–E-78 | ETag handling |
| `exports.py` | E-17 | export status |
| `health.py` | E-79, E-80 |  |

### Models, schemas, repositories

| Folder | Contains | Why |
| --- | --- | --- |
| `models/` | SQLAlchemy classes exactly matching Section 5 tables; `base.py` has the declarative base, `TimestampMixin`, `UserOwnedMixin` | Single source of truth for the schema in code |
| `schemas/` | Pydantic request and response models per resource; `common.py` has `Envelope`, `Page`, `ErrorBody` | API contract; drives OpenAPI |
| `repositories/base.py` | `UserScopedRepository`: every query adds `user_id` | Tenant isolation by construction |
| `repositories/activities.py` | filtered search, overlap lookup, locking, bulk update | All activity SQL |
| `repositories/slices.py` | replace and read slices, range totals | Derived data persistence |
| `repositories/analytics_queries.py` | named aggregate queries used by `analytics/` | Keeps SQL out of formulas |
| other repositories | one per aggregate (users, journal, ai_jobs, taxonomy, tasks, ideal, events, idempotency) |  |

### Services

| File | Responsibility |
| --- | --- |
| `auth_service.py` | registration, login, refresh rotation, Google, verification, reset, deletion |
| `user_service.py` (via `onboarding_service.py` for first run) | profile, preferences, auth events; onboarding seeding |
| `journal_service.py` | entry lifecycle, revisions, processing submission, stats |
| `review_service.py` | review payload assembly, clarification answers, commit transaction |
| `activity_service.py` | create, edit, split, merge, duplicate, bulk, planned → actual, overlap checks |
| `slice_service.py` | slice computation and rebuild, invariant check |
| `timeline_service.py` | blocks, gaps, coverage, ideal overlay |
| `task_service.py` | tasks and projects |
| `category_service.py`, `tag_service.py` | taxonomy rules (move, merge, archive, aliases, rules, goals) |
| `ideal_service.py` | validation, versioning, expected-to-date |
| `export_service.py` | export request and archive build |
| `email_service.py`, `transcription_service.py` | provider wrappers |

### AI package (`app/ai/`)

| File | Contains |
| --- | --- |
| `providers/base.py` | `LLMProvider`, `SpeechToTextProvider` protocols, request / response dataclasses, error types |
| `providers/anthropic_provider.py` | forced-tool-call structured generation, error mapping |
| `providers/fake_provider.py` | fixture-driven provider for tests and offline dev |
| `providers/stt_openai.py` | transcription adapter |
| `prompts/extract_activities/v1.0.0/` | versioned prompt files (Section 6.3) |
| `output_models.py` | Pydantic models equal to schema v1; parse and repair hints |
| `context_builder.py` | assembles the LLM context (Section 6.4) |
| `extraction_pipeline.py` | orchestrates the steps of Section 4.6 and returns a `PipelineResult` |
| `quote_verifier.py` | verifies quotes and computes offsets |
| `time_resolver.py` | meridiem, anchors, midnight, durations (Section 6.6) |
| `tag_matcher.py`, `task_matcher.py` | rule, alias, AI and task matching |
| `detectors.py` | gap, overlap, duplicate detection |
| `confidence.py` | scoring and bands |
| `clarifications.py` | question generation and deterministic answer application |
| `eval/` | dataset and runner (Section 12) |

### Analytics, workers, utilities

| File | Contains |
| --- | --- |
| `analytics/metrics.py` | pure formulas: `coverage`, `adherence`, `row_status`, `bedtime_drift`, `pace_expected` |
| `analytics/day_analytics.py`, `week_analytics.py` | assemble E-74 and E-75 |
| `analytics/overview.py` | composes E-76 |
| `analytics/breakdown.py`, `trends.py` | E-77 and E-78 |
| `analytics/insights.py` | deterministic banners |
| `analytics/sleep.py` | night attribution and drift |
| `workers/app.py` | Procrastinate app, queues, periodic schedule |
| `workers/tasks_ai.py` | `run_extraction_job` |
| `workers/tasks_export.py`, `tasks_email.py`, `tasks_maintenance.py` | export, email, purge, expiry, stuck-job requeue, invariant and backup checks |
| `utils/text.py`, `similarity.py` | normalisation, hashing, `rapidfuzz` helpers |

### Tests

`tests/unit` (pure logic: resolver, metrics, validators), `tests/integration` (services with a real Postgres), `tests/api` (HTTP contract), `tests/ai` (golden and evaluation), `tests/analytics` (formulas on seeded data), `tests/security` (cross-user access, token rotation). `factories.py` builds users, taxonomy and activities; `conftest.py` provides a transactional Postgres fixture.

## 9.4 Frontend tree

```text
frontend/
├── package.json  vite.config.ts  tsconfig.json  tailwind.config.ts  index.html  .env.example
├── vitest.config.ts  playwright.config.ts  orval-or-openapi-ts.config.ts
├── public/        manifest.webmanifest  icons/
└── src/
    ├── main.tsx  App.tsx  routes.tsx
    ├── styles/       tokens.css  globals.css
    ├── api/
    │   ├── client.ts  queryKeys.ts  errors.ts
    │   ├── generated/            TypeScript types from OpenAPI (do not edit)
    │   └── hooks/                useAuth.ts useCurrentUser.ts useJournal.ts useReview.ts useActivities.ts useTimeline.ts
    │                             useTasks.ts useTaxonomy.ts useIdeal.ts useAnalytics.ts useSettings.ts
    ├── stores/       authStore.ts themeStore.ts journalDraftStore.ts reviewDraftStore.ts dialogStore.ts
    ├── lib/          time.ts format.ts colors.ts dictation.ts recorder.ts heuristics.ts idb.ts a11y.ts schemas.ts
    ├── components/
    │   ├── ui/         Button Input Select Dialog Popover Tooltip Tabs Toast Skeleton EmptyState ErrorState Chip
    │   ├── domain/     TagChip CategoryChip ConfidenceBadge TimeRangeInput DurationStepper CoverageStrip24h ActivityCard StatCard
    │   ├── charts/     ChartTooltip ActualVsIdealBars WorkPersonalDonut CoverageByDay SleepBars Clock24 FocusHeatmap TagTreemap LineTrend
    │   └── layout/     AppShell Sidebar BottomTabs TopBar RouteGuard
    ├── features/
    │   ├── auth/ onboarding/ journal/ review/ calendar/ activity/ tasks/ tags/ ideal/ overview/ settings/
    │   └── (each: pages, components, hooks, tests)
    └── tests/        msw handlers, fixtures, e2e/ (Playwright)
```

## 9.5 Frontend files and what each contains

| File / folder | Contains | Why |
| --- | --- | --- |
| `main.tsx`, `App.tsx`, `routes.tsx` | providers (QueryClient, theme, router), route table with lazy-loaded pages | Entry and routing |
| `styles/tokens.css` | CSS custom properties for light and dark from the design file (paper, ink, card, line, muted, faint, good, bad, warn, sky, teal, violet, rose, sleep, heatmap greens, tooltip) | Theming without hard-coded colours |
| `api/client.ts` | `apiFetch` with bearer token, silent refresh on 401, request id capture, `ApiError` | One HTTP path |
| `api/queryKeys.ts` | key factory per resource | Predictable invalidation |
| `api/errors.ts` | maps error codes to user messages and field errors | Consistent error UX |
| `api/hooks/*.ts` | TanStack Query hooks per resource (list in Section 10b) | Only code that calls the client |
| `stores/*.ts` | Zustand stores listed in Section 8.4 | Small client-only state |
| `lib/time.ts` | timezone-aware conversion and formatting, snapping | Time display rules |
| `lib/dictation.ts` | Web Speech wrapper (start, pause, results, errors) | Isolates browser API |
| `lib/recorder.ts` | MediaRecorder wrapper with size and duration limits | Fallback path |
| `lib/heuristics.ts` | live counters and keyword hints (FR-025) | Pure, testable |
| `lib/idb.ts` | IndexedDB draft persistence | Offline draft (FR-014) |
| `lib/schemas.ts` | Zod schemas mirroring API validation | Form validation |
| `components/charts/*` | one SVG component per chart plus `ChartTooltip` | Hover spec implemented once |
| `features/journal` | `JournalPage`, `JournalHistoryPage`, `EntryDetailPage`, composer pieces, `useDictation`, `useCoverageWindow`, `useAutosaveDraft` | Capture flow |
| `features/review` | `ReviewPage`, `DraftRow`, `GapRow`, `ClarificationStrip`, `ConflictDialog`, `useReviewEditor` | Review flow |
| `features/calendar` | `CalendarPage`, `HourGrid`, `ActivityBlock`, `useCalendarDrag` | Timeline editing |
| `features/activity` | `ActivityDetailPanel`, `SplitDialog`, `MergeDialog`, `TimeDialog` | Activity editing |
| `features/tasks`, `tags`, `ideal`, `overview`, `settings`, `auth`, `onboarding` | pages and components per Section 8.3 | Feature isolation |
| `tests/` | MSW handlers generated from the OpenAPI examples; Playwright journeys | Frontend independence from the backend |

