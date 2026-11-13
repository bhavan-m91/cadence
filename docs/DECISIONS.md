# Implementation decisions

Choices made while building where the PRD/design left room. The PRD's own decision register (D-01..D-21) is in `docs/prd/ui-design-review.md` and is followed as written.

| # | Decision | Why |
|---|---|---|
| 1 | Scope of the first pass is PRD Phases 0+1 as a vertical slice. | Agreed with the product owner; the full plan is ~14.5 weeks. |
| 2 | All 22 tables ship in the first migrations (journal and AI tables included, unused). | PRD 11.2: the slice model, exclusion constraint and timezone rule must land in Phase 1; later phases then add no breaking schema. |
| 3 | Migrations are raw SQL DDL, one statement per `op.execute`. | Reads like the data dictionary; exclusion constraint, triggers and partial indexes are explicit. asyncpg cannot prepare multi-statement strings. |
| 4 | Services commit; a decorator rolls back on any error. | Keeps a half-applied edit from lingering and makes error paths testable with a shared transaction. |
| 5 | Event and task timestamps use `clock_timestamp()`. | `now()` is frozen per transaction, which made same-request events and tasks tie and sort randomly. |
| 6 | Timeline reads `activity_day_slices` for blocks and coverage; today is prorated and never "complete"; future days show no gaps. | One source of truth for every number (D-15). |
| 7 | Coverage `logged` includes unplaced (duration-only) time; gaps are computed from placed time only. | Unplaced time counts toward the 24h rule (D-04) but has no position to draw. |
| 8 | Tag goal status values: `none`, `ok`, `over` (max) and `under`, `met` (min). Range defaults to the current week in the user's timezone. | AC-046 needs `over`; the PRD does not name the others. |
| 9 | Category archive is refused while the latest Ideal version allocates it (`CATEGORY_ALLOCATED`); delete is refused for any allocation. | FR-088. |
| 10 | Category merge leaves the archived source where it was and moves its children to the target. | FR-089; avoids path churn on an archived row. |
| 11 | Tag merge adds the old name as an alias of the target even though the archived source still holds the name. | AC-041; alias-equals-tag-name is only refused for non-merged tags. |
| 12 | Google-only accounts cannot delete their account or change a password until they set one via "Forgot password". | FR-009/FR-012 require re-auth; a fresh-Google-login token flow is deferred. |
| 13 | Export is built in a background task and stored on local disk (`EXPORT_DIR`), downloadable for 24 h. | R2 and the worker arrive later; the API contract (E-16/E-17) is unchanged. |
| 14 | The onboarding Ideal Day is "balanced" (sleep 7h30, deep work 4h30, ...), effective from the day of onboarding. | The PRD names a preset without defining it; it must total exactly 1,440 minutes. |
| 15 | Dev server proxies `/api`; refresh cookie is `Path=/api/v1/auth`, `HttpOnly`, `SameSite=Lax`. | Same-site in dev and with `app.`/`api.` subdomains in production. |
| 16 | "Yesterday is short" nudges only appear once something has been logged. | A new account has nothing to be short of (found while testing in the browser). |
| 17 | Frontend uses npm (not pnpm) and Vite 6 / Vitest 3 pins. | pnpm is not installed here; `@vitejs/plugin-react` 6 needs Vite 8. |
