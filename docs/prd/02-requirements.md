# 2 · Functional Requirements

V1.0 has nine modules and 156 numbered requirements. Priority **M** = must ship in V1.0, **S** = should ship, may slip one release without breaking the core loop. Durations are in minutes in the API; "local" means the user's IANA timezone. Each module lists purpose, stories, requirements, inputs/outputs, rules, edge cases, dependencies and acceptance criteria.

| Module | FR range | Main tables | Phase |
| --- | --- | --- | --- |
| M1 Auth & Account | FR-001–012 | users, refresh_tokens, auth_events | 0 |
| M2 Journal | FR-013–028 | journal_entries, journal_entry_revisions | 1 |
| M3 AI Extraction & Review | FR-029–057 | ai_processing_jobs, activities (draft) | 2 |
| M4 Activities & Timeline | FR-058–075 | activities, activity_day_slices, activity_events | 1 |
| M5 Tasks & Projects | FR-076–084 | tasks, projects | 1 |
| M6 Taxonomy | FR-085–104 | categories, tags, activity_tags, tag_aliases, keyword_rules | 1 |
| M7 Ideal Day & Week | FR-105–120 | ideal_templates, ideal_allocations (tag goals live on tags) | 3 |
| M8 Analytics & Dashboard APIs | FR-121–144 | reads slices + above | 4 |
| M9 Settings, Privacy & Platform | FR-145–156 | user_preferences, export_jobs | 0/5 |

## M1 · Auth & Account

**Purpose.** Let one person own a private account and guarantee that no other account can read it.

**Features.** Email + password, Google sign-in, verification, password reset, session refresh, profile, account deletion.

**User stories.**

- As a new user I register with email and password so my journal is private.
- As a returning user I stay signed in on my own device so I can dictate quickly.
- As a user I delete my account and all data so I stay in control.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-001 | Register with email + password (≥ 10 characters, rejected if in a common-password list). Creates `users` and `user_preferences` rows, sends a verification email, returns tokens. | M |
| FR-002 | Verification link is single-use and expires in 24 h. Unverified users can sign in and use the app; export and account deletion by password require a verified email. | M |
| FR-003 | Email + password login. After 5 failed attempts per account+IP in 15 min return 429 with `Retry-After`. Failure message never reveals whether the email exists. | M |
| FR-004 | Google sign-in via OpenID Connect. Links to an existing account only when Google reports the email as verified; otherwise creates a new account. | M |
| FR-005 | Access token = JWT, 15 min, held in memory. Refresh token = opaque random value in an `HttpOnly; Secure; SameSite=Lax` cookie, rotated on every use; "keep me signed in" = 30 days, otherwise a session cookie. Only the SHA-256 hash is stored. | M |
| FR-006 | Reuse of a rotated refresh token revokes the whole token family and returns 401. Logout revokes the current family; "sign out everywhere" revokes all. | M |
| FR-007 | Forgot password sends a 1 h single-use link; the response is identical for known and unknown emails. | M |
| FR-008 | Completing a reset revokes every refresh token of the user. | M |
| FR-009 | Changing password or email requires current password (or fresh Google login). | S |
| FR-010 | Profile fields: display name, optional role title, IANA timezone, theme (system / light / dark). | M |
| FR-011 | Every data query is filtered by the authenticated `user_id`; a resource owned by someone else returns 404, never 403. | M |
| FR-012 | Account deletion (re-authentication + typed confirmation) hard-deletes the user and all owned rows in one transaction, revokes tokens, sends a confirmation email. | M |

**Inputs / outputs.** In: credentials, OAuth code, tokens. Out: `{access_token, expires_in, user}` and a refresh cookie.

**Business rules.** Passwords hashed with argon2id. Email unique case-insensitively. A Google-only account has no password until it sets one. Security events (login success/failure, password change, reset) go to `auth_events`.

**Edge cases.** Same email via password and Google; refresh cookie from another device after sign-out-everywhere; clock skew on JWT (30 s leeway); verification link clicked twice; deleting an account while an AI job is running (job cancelled, results discarded).

**Dependencies.** Email provider (verification, reset, deletion notice), Google OAuth client.

**Acceptance criteria.**

- AC-001 Given a registered email, when 6 wrong passwords are sent within 15 min, then the 6th returns 429 and a correct password within the window is also refused until it ends.
- AC-002 Given user A's activity id, when user B requests it, then the response is 404 with no body hint that it exists.
- AC-003 Given a used refresh token, when it is sent again, then 401 is returned and the family's newer token also stops working.
- AC-004 Given a reset link, when it is used twice, then the second use fails with a generic invalid-link error.
- AC-005 Given a confirmed deletion, when the user's id is queried in every user-owned table, then zero rows remain.
- AC-006 Given a Google account whose email is unverified, when it signs in, then no link to an existing account is made.

## M2 · Journal

**Purpose.** Capture the user's words, by typing or dictation, for any period, and preserve them forever.

**Features.** Dictate / type editor, coverage window, drafts and autosave, retro entries, multiple entries per day, history, revisions, habit stats.

**User stories.**

- As a user I talk for two minutes and see the words appear so I trust the capture.
- As a user I say "this covers 12am to 5pm" so Cadence knows what I did *not* mention.
- As a user I edit an old entry without losing what I originally said.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-013 | Create an entry with `raw_text` (1–10,000 characters), `covers_start_at`, `covers_end_at`, `timezone`, `input_method` (typed / dictated). Status `draft` or `processing`. | M |
| FR-014 | Drafts persist server-side. The client autosaves 5 s after the last keystroke; a local copy survives offline and reloads. | M |
| FR-015 | Dictation uses the Web Speech API: live interim text, pause / resume, elapsed timer, final text appended to the editor and editable before submit. | M |
| FR-016 | If the Web Speech API is missing or errors, the client records audio (MediaRecorder, ≤ 10 min, ≤ 10 MB) and calls `/transcriptions`. The server returns text and discards the audio; audio is never stored. | M |
| FR-017 | Coverage window presets: Whole day so far (default for today), Last N hours, Since last entry, Custom. Rules: `start < end`, length ≤ 24 h, `end ≤ now + 5 min`. | M |
| FR-018 | Entries may be created for any past date. The date defaults from the window start in the entry's timezone. | M |
| FR-019 | Several entries per day are allowed. Overlapping windows produce a warning naming the other entry; they are not blocked. | M |
| FR-020 | Submit validates input, sets `processing`, enqueues an AI job (or, with AI disabled, sets `manual` and opens the activity editor). | M |
| FR-021 | Editing `raw_text` or the window is allowed in any status. Every text change inserts a `journal_entry_revisions` row; revision 1 is the original and is never altered or deleted. | M |
| FR-022 | History list: filter by date range and status, search text, cursor pagination (20 per page), newest first. | M |
| FR-023 | Entry detail shows the current text with source highlights for linked activities, the revision list and a link to Review. | S |
| FR-024 | Deleting an entry soft-deletes it and requires `activities=keep\|delete`; "keep" detaches nothing but marks activities as manually owned. | M |
| FR-025 | Live counters (word count, "~N activities", "~covered") are client-side heuristics shown with a tilde; exact values arrive after extraction. | S |
| FR-026 | Recent entries panel shows the last 5 entries: title (AI summary, else first 60 characters), meta, activity count, covered time. | S |
| FR-027 | Habit stats: journal streak (consecutive local days ending today or yesterday with ≥ 1 confirmed entry), entries per day (30-day mean), share of completed days at 24 h (30 days). | S |
| FR-028 | Short-yesterday nudge: when the last completed day has unlogged time above the tolerance, show the gap and an **Add** action that opens Journal with the gap as the window. | S |

**Inputs / outputs.** In: text, window, timezone. Out: entry with `status`, `latest_job_id`, `revision`.

**Business rules.** The original text is immutable history. A window never crosses more than 24 h. Timezone is captured per entry so later timezone changes do not move history.

**Edge cases.** Dictation stops on mic permission loss (text kept); entry pasted from another app with 5,000 words (accepted, warned about AI cost); two tabs editing the same draft (`version` check, last-write conflict dialog); window ending in the future; midnight crossing; DST change inside a window.

**Dependencies.** M1; M3 for processing; M9 for preferences.

**Acceptance criteria.**

- AC-007 Given an edit to a confirmed entry's text, when it is saved, then revision 1 still equals the first submitted text byte for byte.
- AC-008 Given a window of 25 h, when submitted, then 422 `WINDOW_TOO_LONG`.
- AC-009 Given the Web Speech API is unavailable, when the user taps the mic, then the recorder path runs and the audio file is absent from storage after the response.
- AC-010 Given two entries whose windows overlap, when the second is saved, then a warning names the first and the save still succeeds.
- AC-011 Given a draft typed offline, when the app reloads, then the text is restored.
- AC-012 Given an entry with activities, when it is deleted with `activities=delete`, then those activities are soft-deleted and absent from analytics.
- AC-013 Given completed yesterday with 4 h 30 m unlogged, when Journal opens, then the nudge shows 4 h 30 m and Add prefills that window.
- AC-014 Given a streak of 23 days ending yesterday, when today has no entry yet, then the streak still reads 23.

## M3 · AI Extraction & Review

**Purpose.** Turn free text into proposed activities that a human approves, with every proposal traceable and uncertainty shown honestly.

**Features.** Async extraction, deterministic time resolution, tag and task matching, confidence, clarification questions, gap / overlap / duplicate detection, review UI, commit, regenerate.

**User stories.**

- As a user I see each proposed activity next to the sentence it came from so I can verify it quickly.
- As a user I am asked, not guessed at, when I said "some time in the afternoon".
- As a user I accept everything with one click when the AI got it right.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-029 | `POST /journal-entries/{id}/process` creates an `ai_processing_jobs` row (`queued`), returns 202 with the job id; the client polls every 1.5 s. | M |
| FR-030 | The worker builds the LLM context: entry text, window in local time, current local time, timezone, category tree (id, path, description), tags with aliases, keyword rules, up to 30 open tasks, optional user hint. | M |
| FR-031 | The LLM must return JSON matching schema v1 (Section 6). Invalid JSON gets one repair attempt that includes the validation errors; a second failure fails the job. | M |
| FR-032 | Each proposed activity carries title, description, verbatim `source_quote`, one category, tags with reasons, task proposal, `time_ref`, confidences and flags. | M |
| FR-033 | Code, not the LLM, converts `time_ref` into UTC instants, computes durations, assigns missing am/pm so the day moves forward in time, and handles midnight crossing. | M |
| FR-034 | Vague times ("some time in the afternoon") become `unplaced` activities with a window and no start. If no duration was stated the activity is blocked and a clarification question is raised; no duration is invented. | M |
| FR-035 | Derived times are allowed only from neighbours: a start with no end may end at the next activity's start; a duration after a known end may start at that end. Such values are `time_certainty = inferred`. | M |
| FR-036 | A `placed` activity must have time evidence in its `source_quote` or neighbours; otherwise the validator downgrades it to `unplaced` and flags it. | M |
| FR-037 | Category: exactly one id from the user's tree. Uncertain results keep the best guess with low confidence. The AI never creates categories. | M |
| FR-038 | Tag matching order: keyword rules → exact or alias match → LLM-chosen existing tag id → new-tag suggestion (`new=true`). A new tag is created only if the user keeps it at commit. | M |
| FR-039 | Each AI tag stores `reason` (the triggering phrase) and `confidence`; the UI shows "from …" on hover. | M |
| FR-040 | Confidence bands: high ≥ 0.80, medium 0.50–0.79 ("double-check"), low < 0.50 (highlighted; AI tags below 0.50 are shown dashed amber and are not applied until accepted). | M |
| FR-041 | At most 5 clarification questions per run, raised only for: unresolvable am/pm, missing duration for a vague activity, date outside the window, tag ambiguity below 0.50, unplaceable sleep. Answers are applied by deterministic code. | M |
| FR-042 | Gap detection runs after resolution inside the coverage window. Gaps shorter than `gap_min_minutes` (default 10) are ignored. Each gap offers **Add activity** and **Mark as transition**. | M |
| FR-043 | Overlaps inside the batch or against confirmed activities are flagged. Resolution choices: trim new, trim existing, replace existing, keep as unplaced. Commit is blocked until resolved. | M |
| FR-044 | Duplicate detection against confirmed activities: time overlap ≥ 80% and title similarity ≥ 0.85 (rapidfuzz) or the same `source_quote`. Default action: skip the proposal. | M |
| FR-045 | The model resolves relative dates ("yesterday", "Monday"). A date outside the coverage window ± 12 h raises a warning and a clarification. | M |
| FR-046 | Review screen: per-row include checkbox (default on), edit title, description, time, category, tags, task link and location; add a missing activity; discard a row; accept all; **Save N activities**. | M |
| FR-047 | Hovering a row highlights its source quote in the "What you said" panel and the reverse. Highlights use stored character offsets. | M |
| FR-048 | Commit is one transaction: validate (no overlaps, durations present, no unresolved blocking questions), insert activities as `confirmed`, tags, approved new tags and tasks, day slices, events, then mark the entry `confirmed`. Idempotent via `Idempotency-Key`. | M |
| FR-049 | Rows the user excludes are stored in the job output as `rejected` for quality metrics and never become activities. | M |
| FR-050 | Regenerate creates a new job and keeps older jobs; an optional user hint (≤ 500 chars) is added to the prompt. Limit 5 regenerations per entry per day. | M |
| FR-051 | On re-extraction commit the user chooses **Replace** (soft-delete the earlier AI activities of this entry) or **Keep both**. Activities with `user_edited = true` are listed and never replaced silently. | M |
| FR-052 | Job states: `queued`, `running`, `succeeded`, `failed`, `cancelled`. Transient errors retry 3 times (2 s, 8 s, 30 s). Permanent failure shows **Retry** and **Enter manually**; the entry text is never lost. | M |
| FR-053 | With AI disabled in preferences the entry is saved as `manual` and no job is created. | M |
| FR-054 | Each job stores prompt version, provider, model, token counts, latency, raw response and parsed response. | M |
| FR-055 | The same entry text hash, window and prompt version within 10 min returns the existing job unless `regenerate=true`. | S |
| FR-056 | The LLM payload contains no email, name or account id. Logs never contain journal text. | M |
| FR-057 | Per-user cap of 30 extraction jobs per day returns 429 `AI_DAILY_LIMIT` with the reset time. | S |

**Inputs / outputs.** In: entry, taxonomy, tasks, hint. Out: job result with activities, gaps, conflicts, duplicates, clarifications; after commit, confirmed activities.

**Business rules.** Nothing the AI proposes is counted in analytics until committed. Draft rows live in `activities` with `status = draft` and are excluded from every aggregate. A user edit sets `user_edited`. The first AI proposal is snapshotted in `ai_proposed` so correction rate can be measured.

**Edge cases.** Entry mentions only feelings and no activity (empty result with explanation); "10 to 1" read as 10:00–13:00 not 10:00–01:00; activity ending after the window end; two activities with the same quote; sleep spanning midnight; LLM returns a category id that was archived since; user edits the text while a job runs (job result marked stale, re-run offered); provider outage.

**Dependencies.** M2, M4, M5, M6, LLM provider, queue worker.

**Acceptance criteria.**

- AC-015 Given "I worked on Product A for some time in the afternoon", when extracted, then the activity is `unplaced`, has no start time, and a duration question is asked.
- AC-016 Given "10 to 1 fixing the sync bug" with a window 12am–5pm, when resolved, then start 10:00 and end 13:00 local.
- AC-017 Given a job with an invalid JSON response, when it is retried once and fails again, then the job is `failed` and the entry text is unchanged.
- AC-018 Given a proposal that overlaps a confirmed activity, when the user presses Save without resolving it, then commit is refused with 409 listing the conflict.
- AC-019 Given 3 excluded rows, when committed, then no activities exist for them and the job output lists 3 `rejected` items.
- AC-020 Given an activity whose quote is not found in the text, when validated, then the quote is cleared, the confidence drops and the flag `quote_unverified` is set.
- AC-021 Given the same commit request sent twice with one Idempotency-Key, when processed, then activities are created once.
- AC-022 Given a keyword rule "Twitter → #social-media", when the text contains "Twitter", then the tag is applied with source `rule` regardless of the LLM output.
- AC-023 Given regeneration with Replace, when committed, then earlier AI activities with `user_edited = false` are soft-deleted and edited ones are kept and listed.
- AC-024 Given AI disabled, when an entry is submitted, then no job row exists and the activity editor opens.
- AC-025 Given a window of 12am–5pm and activities covering 15 h 40 m, when shown, then "1 h 20 m not mentioned" and its gaps are displayed.
- AC-026 Given a likely duplicate, when the review opens, then the row is unchecked with a link to the existing activity.
- AC-027 Given an LLM payload captured in a test, when inspected, then it contains no email address and the log output contains no journal words.

## M4 · Activities & Timeline

**Purpose.** Make "what happened on a day" easy to see, correct and trust.

**Features.** Manual logging, edit, split, merge, duplicate, bulk retag, day and week timeline, search, detail view with history, planned blocks.

**User stories.**

- As a user I drag the edge of a block to fix its end time in seconds.
- As a user I split a 3-hour block when I realise it was two different things.
- As a user I open any block and read the sentence it came from.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-058 | Manual create: title (1–120 chars), description (≤ 2,000), one category, tags, `kind` (actual / planned), either start + end or duration + window, optional task, project, `location_type`. | M |
| FR-059 | Edit any field. Updates use the optimistic-lock `version`; a stale write returns 409. Any user edit sets `user_edited = true` and rebuilds the day slices. | M |
| FR-060 | Delete is soft (`deleted_at`) with a 10 s Undo toast; soft-deleted rows are purged after 30 days. | M |
| FR-061 | Split at time *t* inside a placed activity: the original keeps `[start, t)`, a new activity gets `[t, end)`; category, tags, task and location are copied; each part ≥ 5 min; lineage recorded. | M |
| FR-062 | Merge 2 or more activities of one user: allowed when they are contiguous placed blocks (gap ≤ `gap_min_minutes`, the gap is absorbed) or all unplaced. Tags are unioned; category must match or be chosen. Otherwise 422 `MERGE_NOT_CONTIGUOUS`. | M |
| FR-063 | Duplicate copies an activity into a chosen slot (default: immediately after the original) and applies the overlap rule. | S |
| FR-064 | Replace the tag set of an activity; bulk add / remove tags and bulk change category for up to 100 activities in one request. | M |
| FR-065 | Assign or clear task / project for one activity or up to 100 in bulk. | M |
| FR-066 | Overlap rule: two confirmed actual placed activities of one user may not overlap. Enforced by a database exclusion constraint; the service pre-checks and returns 409 `ACTIVITY_OVERLAP` with the conflicting ids. | M |
| FR-067 | Timeline API returns, for a date range, per-day blocks, gaps, coverage and optional Ideal overlay. Blocks are coloured by category; gaps are hatched; planned blocks are visually distinct. | M |
| FR-068 | Calendar supports drag-move and drag-resize with 5-minute snap. A rejected overlap reverts the block and shows a toast. | M |
| FR-069 | Clicking a gap opens the Log time dialog with that slot pre-filled. | M |
| FR-070 | Search and filter: text over title, description and source quote; category (with subtree); tags (any / all); task; project; status; kind; certainty (stated / estimated); needs-check; date range. | M |
| FR-071 | Activity detail shows every field, the source sentence with surrounding context and **Open entry**, history events, other activities with the same tag this week, and the tag's weekly context against the Ideal week. | M |
| FR-072 | Planned activities can be created and edited; **Mark done** converts one to actual after the overlap check. Planned time never counts in actual analytics. | S |
| FR-073 | An activity may cross midnight (typically sleep) and is stored once; views and analytics clip it to local days through slices. | M |
| FR-074 | Every change writes an `activity_events` row (created, field changes, tagged, split, merged, approved) with actor `user`, `ai` or `system`. | M |
| FR-075 | `location_type` is one of office, home, remote, travel, other, or empty. The AI proposes it only when the text states a place. | S |

**Inputs / outputs.** In: field values, bulk id lists, filters. Out: activity objects, timeline payloads, event lists.

**Business rules.** Placed activities need `start < end`, duration ≤ 24 h, and 5-minute granularity in the UI (API accepts any whole minute). `duration_minutes` always equals the interval length for placed rows. Planned rows may overlap each other but not confirmed actuals.

**Edge cases.** DST transitions (a 2 am–3 am block that does not exist or repeats); activity edited so it now overlaps a different one; merge of activities with different categories; deleting an activity that is the only one in an entry; resizing across midnight; two browsers editing one block.

**Dependencies.** M6 (category, tags), M5 (tasks), database exclusion constraint.

**Acceptance criteria.**

- AC-028 Given a block 10:00–13:00, when split at 11:30, then two blocks exist, 90 min each, with identical tags and a lineage record.
- AC-029 Given blocks 09:00–10:00 and 10:00–11:00 of the same category, when merged, then one 09:00–11:00 block exists with unioned tags.
- AC-030 Given a block resized to overlap its neighbour, when saved, then 409 `ACTIVITY_OVERLAP` and the UI restores the original size.
- AC-031 Given sleep 23:00–07:00, when the timeline for the second day is requested, then it shows 00:00–07:00 of that block.
- AC-032 Given two clients with the same `version`, when both save, then one succeeds and one gets 409.
- AC-033 Given a planned block, when Mark done succeeds, then it appears in actual analytics and no longer in planned lists.
- AC-034 Given a search for tag `#p0` AND category Work, when run, then only activities with both are returned.
- AC-035 Given a deleted activity, when Undo is pressed within 10 s, then it returns with its tags and task.
- AC-036 Given a 2 am–4 am block on a DST fall-back night, when stored, then its duration equals real elapsed minutes.

## M5 · Tasks & Projects

**Purpose.** Let work items persist across days so "how long did the sync fix really take?" has an answer.

**Features.** Task and project CRUD, linking, rollups, due dates, priority, status.

**User stories.**

- As a user I see all time spent on "Product B sync fix" across the week.
- As a user I mark a task done without touching its time records.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-076 | Task fields: title (1–160), description, project, priority (P0–P3 or none), due date, status (open / done / dropped), optional estimate in minutes. | M |
| FR-077 | An activity links to at most one task. Deleting a task unlinks its activities and keeps them. | M |
| FR-078 | Task detail shows total logged minutes, minutes by week and by day, first and last logged date, and the linked activities. | M |
| FR-079 | Project fields: name (unique per user), colour, archived flag. Project rollups mirror task rollups. | M |
| FR-080 | An activity's project is its task's project unless set directly. Changing the task updates the project only when it was inherited. | M |
| FR-081 | Extraction proposes linking an existing open task when similarity ≥ 0.80, otherwise proposes a new task title that needs approval at commit. | M |
| FR-082 | Tasks with a due date appear in the Overview deadline list: next 7 days and overdue. | S |
| FR-083 | Setting status `done` or `dropped` never alters linked activities or analytics. | M |
| FR-084 | Task search and filter: status, project, priority, due range, has-time. | S |

**Inputs / outputs.** In: task and project fields, activity link ids. Out: task with rollups.

**Business rules.** Tasks exist with zero activities. Deadline status is derived from `due_date` and today's local date only (no dependency logic in V1.0).

**Edge cases.** Two tasks with similar titles; linking an activity that already has a task (replace); archived project with open tasks; due date in the past at creation.

**Dependencies.** M4, M6.

**Acceptance criteria.**

- AC-037 Given a task with activities on 3 days, when its detail is read, then by-day minutes sum to the total.
- AC-038 Given a deleted task, when its former activities are listed, then they exist with no task.
- AC-039 Given an extraction naming "the sync bug" and an open task "Fix sync bug", when similarity ≥ 0.80, then the proposal links that task id.
- AC-040 Given a task marked done, when weekly analytics run, then totals are unchanged.

## M6 · Taxonomy (Categories and Tags)

**Purpose.** Provide the two classification axes behind every chart: one category per activity for a clean 24-hour partition, and many tags for flexible slicing.

**Features.** Category tree, tags, aliases, keyword rules, goals, colours, rename, archive, merge, bulk assign, usage history.

**Core rule (D-02).** Category totals add up to the logged time exactly once. Tag totals overlap: an activity with three tags adds its full duration to each of the three, and every chart that shows tags says so.

**User stories.**

- As a user I merge #prod-b into #product-b and my history keeps adding up.
- As a user I say "scrolled Instagram" and Cadence tags #social-media because I told it to.
- As a user I set #social-media to max 5 h a week and see a red ring when I pass it.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-085 | Three system root categories exist for every user: **Work**, **Personal**, **Sleep**. They cannot be deleted or re-rooted. Onboarding offers a seed set of children. | M |
| FR-086 | Category fields: name (unique among siblings, case-insensitive), colour, description (sent to the LLM), `counts_as_focus` flag. Maximum depth 3 including the root. | M |
| FR-087 | Moving a category is allowed within its root. Moving across roots is allowed only when the category and its descendants have no activities. | M |
| FR-088 | Archiving a category hides it from pickers but keeps history. Blocked while an active Ideal allocation uses it. | M |
| FR-089 | Merge category A into B (same root, B not a descendant of A): repoint activities, allocations (summed), keyword rules and aliases, then archive A. Irreversible; previews the affected counts. | M |
| FR-090 | A category with activities cannot be deleted; the user must merge or reassign first. | M |
| FR-091 | Tag fields: name (lowercase letters, digits, `-`, `_`, optional `namespace:` prefix), colour, description. Unique per user, case-insensitive. | M |
| FR-092 | Tags have aliases; AI matching and keyword rules resolve aliases to the tag. | M |
| FR-093 | Keyword rules map a phrase to a tag or category (case-insensitive, whole-word) and run before LLM matching ("Auto-tag when I say…"). | M |
| FR-094 | Tag goals: `tracked` (no target), `min` or `max` with weekly minutes. A `max` tag over its limit is flagged with the red-ring state. | M |
| FR-095 | Rename changes the name only; the id is stable so history and analytics are unaffected. The old name can be kept as an alias. | M |
| FR-096 | Archive and unarchive tags. Archived tags are not suggested and not offered in pickers but remain on history and in charts. | M |
| FR-097 | Merge tag A into B: repoint `activity_tags` (de-duplicating), move aliases, keyword rules and goal, add A's name as an alias of B, then archive A. Shows the affected count first. | M |
| FR-098 | A tag can be deleted only when unused. | S |
| FR-099 | Bulk add or remove a tag on up to 100 activities. | M |
| FR-100 | Tag detail shows hours this week against its goal, a per-day chart, recent activities and the all-time or ranged total. | M |
| FR-101 | Every analytics response labels each series as `partition` (categories) or `overlay` (tags). | M |
| FR-102 | Colours are auto-assigned from the design hue palette and editable. | S |
| FR-103 | Usage counts are computed by query, not stored counters, so merges cannot drift. | M |
| FR-104 | An AI-suggested new tag is created only if the user keeps it in Review. | M |

**Inputs / outputs.** In: names, colours, rules, goals, merge targets. Out: category tree, tag list with usage and goal status.

**Business rules.** Historical analytics never depend on names, only ids. Archived items stay resolvable. Cross-root category moves with data are refused so Work vs Personal history cannot change silently.

**Edge cases.** Merge into an archived tag; two tags differing only by case; a keyword rule that matches inside another word ("art" in "party"); alias equal to another tag's name (rejected); category with children merged (children move to the target).

**Dependencies.** M4 for assignment, M7 for allocations.

**Acceptance criteria.**

- AC-041 Given tags A (3 h) and B (2 h) on disjoint activities, when A is merged into B, then B shows 5 h and A's old name resolves to B.
- AC-042 Given an activity tagged both A and B, when A merges into B, then B appears once on it.
- AC-043 Given a renamed category, when last month's chart loads, then totals are unchanged and show the new name.
- AC-044 Given a category with activities, when delete is requested, then 409 `CATEGORY_IN_USE`.
- AC-045 Given a Work category holding activities, when moved under Personal, then 422 `CROSS_ROOT_MOVE`.
- AC-046 Given #social-media max 300 min and 370 min logged this week, when the tag list loads, then `goal_status = over`.
- AC-047 Given the keyword "art", when the text says "party", then no tag is applied.
- AC-048 Given a day with one activity tagged three ways, when the daily analytics read, then category totals equal the activity duration once and each tag shows the full duration.
- AC-049 Given an archived tag, when the AI proposes tags, then it is never among the candidates sent to the model.

## M7 · Ideal Day & Ideal Week

**Purpose.** Store how the user wants to spend time, as a complete 24-hour and 168-hour allocation, so every analytic can answer "versus what?".

**Features.** Ideal Day editor, Ideal Week editor, overlay tag goals, presets, versions, validation, actual-vs-ideal computation.

**Design rules (D-06).** Allocations are on **categories**, never on overlapping tags, so totals can equal exactly 24 h or 168 h. Tag goals (for example #social-media max 5 h a week) are overlays and are *not* part of the total. An Ideal Week is weekly totals plus a **distribution** per row (`all_days`, `weekdays`, `weekend`), so "Deep work 20 h, weekdays only" is expressible and weekends can differ without storing 7 daily templates.

**User stories.**

- As a user I assign hours to categories in 30-minute steps and see the remainder until it reaches zero.
- As a user I change my Ideal Week this Monday without rewriting how last month compared.
- As a user I cap #wasted at 3 h a week and see when I pass it.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-105 | Ideal Day = set of allocations `(category, minutes)`; minutes are multiples of 5 (UI step 30); total must equal exactly 1,440. | M |
| FR-106 | Ideal Week = set of `(category, weekly minutes, distribution)`; total must equal exactly 10,080. | M |
| FR-107 | Allocated categories form an antichain: no allocated node may be an ancestor or descendant of another, and no category appears twice. | M |
| FR-108 | Tag goals (`min`, `max`, `tracked`) are edited on the Ideal screen and the Tags screen (same data, FR-094) and never counted in the 24 h / 168 h totals. | M |
| FR-109 | The editor shows a live total, remaining time and an over / under message. Save is disabled until the total is exact; **Assign remainder to…** fills the gap. | M |
| FR-110 | Presets: **Fill week from Ideal Day × 7**, and **Weekdays + lighter weekends** (work categories get `weekdays`, others `all_days`, then totals are rebalanced to 10,080 through a category the user chooses). | S |
| FR-111 | Saving creates a new version with `effective_from` (this week, today, or a chosen date). Older versions are retained and listed. Comparisons for a date use the version effective on that date. | M |
| FR-112 | Daily comparisons use the Ideal Day; weekly comparisons use the Ideal Week; the weekly pace line for a row uses its distribution. | M |
| FR-113 | Any time not covered by an allocation is shown as **Unallocated** in editors and comparisons; the server refuses to save templates that leave it non-zero. | M |
| FR-114 | Validation errors: `ALLOCATION_TOTAL_MISMATCH` (expected, actual, delta), `ALLOCATION_NOT_ANTICHAIN`, `DUPLICATE_ALLOCATION`, `INVALID_MINUTES`, `CATEGORY_ARCHIVED`. | M |
| FR-115 | **Reset** restores the last saved version in the editor without a server call. | S |
| FR-116 | Category merge sums allocations; archiving an allocated category is blocked until the allocation is moved (FR-088, FR-089). | M |
| FR-117 | New accounts get a suggested Ideal Day (Sleep 8 h, Work 8 h, Personal remainder across seeded children) that the user must confirm. | S |
| FR-118 | A deterministic service returns, per allocation row, `actual`, `target`, `delta`, `status` and the unallocated remainder for a date or week. | M |
| FR-119 | Row status: `on_target` when \|delta\| ≤ max(15 min, 10% of target); otherwise `under` or `over`. | M |
| FR-120 | Tag goal breaches are reported in the weekly analytics and drive the red-ring state. | M |

**Inputs / outputs.** In: allocations, distributions, `effective_from`. Out: template version with computed totals and `unallocated_minutes`.

**Edge cases.** Allocation to a category later archived by merge; two versions with the same `effective_from` (second replaces first); week crossing a version change (uses the version in force on the week's Monday); editing when no categories exist; today's partial day.

**Dependencies.** M6, M8.

**Acceptance criteria.**

- AC-050 Given allocations totalling 1,380 min, when saved, then 422 `ALLOCATION_TOTAL_MISMATCH` with `delta = -60`.
- AC-051 Given allocations to Work and Work › Deep work, when saved, then 422 `ALLOCATION_NOT_ANTICHAIN`.
- AC-052 Given a weekly row of 1,200 min with `weekdays`, when the pace for Wednesday end is computed, then expected = 720 min.
- AC-053 Given a new version effective Monday, when last week is compared, then last week uses the older version.
- AC-054 Given a #social-media goal of max 300 min that is excluded from totals, when the week template is saved at 10,080 min, then it passes.
- AC-055 Given |delta| = 12 min on a 3 h target, when status is computed, then `on_target`.
- AC-056 Given categories merged, when the Ideal Day is read, then the two allocations appear as one with summed minutes.
- AC-057 Given "Assign remainder to Entertainment" with 90 min left, when pressed, then Entertainment gains exactly 90 min and the total is 1,440.
- AC-058 Given an archive attempt on an allocated category, when requested, then 409 `CATEGORY_ALLOCATED`.

## M8 · Analytics & Dashboard APIs

**Purpose.** Provide reliable, consistently defined numbers for the dashboards. The detailed dashboard UI is a separate frontend phase (Phase 4B); this module's APIs ship first.

**Metric definitions (single source of truth).** All metrics read `activity_day_slices` (confirmed, actual, not deleted). "Tracked" = placed + unplaced minutes.

| Metric | Definition |
| --- | --- |
| `placed_minutes` | Minutes of placed slices for a local date |
| `unplaced_minutes` | Minutes of activities with `placement = unplaced` attributed to the window's start date |
| `recorded_minutes` | Tracked minutes whose `time_certainty = stated` |
| `estimated_minutes` | Tracked minutes whose `time_certainty` is `inferred` or `estimated` |
| `elapsed_minutes` | 1,440 for a completed day; minutes since local midnight for today |
| `unlogged_minutes` | `max(0, elapsed_minutes − placed_minutes)` |
| `coverage_pct` | `placed_minutes ÷ elapsed_minutes` |
| `day_complete` | Completed day with `unlogged_minutes ≤ coverage_tolerance` (default 10 min) |
| `target_minutes` | Ideal Day or Ideal Week allocation in force on that date |
| `adherence` | Σ min(actual, target) ÷ Σ target over non-Sleep allocation nodes. Actual = tracked minutes rolled up to the allocation node. Week scope uses completed days only, with each row's target scaled by completed days in its distribution. Today in day scope is **provisional**: targets scaled by `elapsed_minutes ÷ 1440`. |
| `delta` / `status` | `actual − target`; status rule in FR-119 |
| `sleep_by_wake_date` | Each Sleep-root activity counts fully on the local date of its `end_at` |
| `bedtime_drift` | Population standard deviation of bedtime (minutes after 18:00 local) over the last 7 nights |
| `short_night` | `sleep_by_wake_date < short_night_minutes` (default 420) |
| `focus_minutes` | Tracked minutes in categories with `counts_as_focus` |
| `work_vs_personal` | Tracked minutes by root, excluding Sleep ("waking") |
| `work_outside_office` | Work-root minutes whose `location_type` is set and not `office` |
| `personal_in_office_hours` | Personal-root placed minutes on weekdays inside preference office hours |
| `goal_status` (tag) | `ok`, `over` (max exceeded), `under` (min not reached), `tracked` |

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-121 | `GET /analytics/day/{date}` returns for one local date: totals by category (partition), by tag (overlay), by task and project, certainty split, coverage, sleep, focus, adherence and Ideal comparison. | M |
| FR-122 | `GET /analytics/week/{weekStart}` returns the same for a week plus per-day columns, pace lines from the Ideal Week and tag goal status. Week start honours the preference (default Monday). | M |
| FR-123 | `GET /analytics/overview?scope=day\|week&anchor=` composes KPIs, banners, deadlines and chart payloads for the Overview screens in one call. | M |
| FR-124 | Coverage and unlogged time use the definitions above; a day is *complete* within the tolerance. | M |
| FR-125 | Four quantities are always distinct in payloads: recorded, estimated, target, unlogged. | M |
| FR-126 | Adherence uses the formula above; the payload carries `provisional: true` for today. | M |
| FR-127 | Actual vs Ideal by category uses completed days only in week scope and includes an `unallocated_actual` row for tracked time outside any allocation. | M |
| FR-128 | Work vs Personal excludes Sleep; payload also carries `work_outside_office` and `personal_in_office_hours`. | M |
| FR-129 | Sleep block: per night duration, bed time, wake time, average, target, drift, shortest, longest, short-night count for the last 7 nights. Duration-only sleep counts in averages but has no bed / wake. | M |
| FR-130 | Focus block: minutes per day against the focus target (sum of Ideal allocations on `counts_as_focus` categories). | M |
| FR-131 | `GET /analytics/breakdown?from&to&by=category\|tag\|task\|project` returns the category tree with roll-ups (partition) or flat overlay lists with share of waking time, honouring filters. | M |
| FR-132 | `GET /analytics/trends?metric&granularity&periods` serves adherence, coverage, sleep and focus series (8-week lines, 26-week heatmap). | M |
| FR-133 | Responses include comparison to the previous period ("vs last week") where meaningful. | S |
| FR-134 | Tag goal status is computed for the current week and returned with each tag series. | M |
| FR-135 | Banners (max 3) are produced by fixed rules: coverage shortfall, category ≥ 2 h over or under for the week or ≥ 30 min for the day, tag cap breach, ≥ 2 short nights in 7. Each has an action target. No LLM. | S |
| FR-136 | Day scope returns "today's rhythm": logged and planned blocks beside the Ideal Day. | S |
| FR-137 | Streaks: journal streak and consecutive days with focus minutes > 0. | S |
| FR-138 | Deadlines: open tasks due within 7 days plus overdue, with days left. | S |
| FR-139 | Every aggregate carries what the hover spec needs: actual, ideal, difference, share, tag path, entry counts. | M |
| FR-140 | Analytics exclude `draft`, `planned` and soft-deleted rows. | M |
| FR-141 | Dates are local dates computed with each activity's own timezone. | M |
| FR-142 | The 26-week trend endpoint answers in p95 < 400 ms for 7,000 activities. | M |
| FR-143 | Breakdown and timeline accept the same filter set so a chart click can open Calendar with equal filters. | M |
| FR-144 | Analytics responses carry `ETag` from the user's `data_revision` counter; unchanged data returns 304. | S |

**Edge cases.** No Ideal defined yet (comparison fields null and a setup prompt); week with 1 completed day; timezone change mid-week; activity crossing midnight; duration-only sleep; all activities unplaced.

**Dependencies.** M4, M6, M7.

**Acceptance criteria.**

- AC-059 Given a 3 h activity tagged #a, #b, #c in category X, when the day is read, then X = 180, and each tag = 180.
- AC-060 Given a completed day with 21 h 30 m placed, when read, then `unlogged = 150`, `day_complete = false`.
- AC-061 Given Ideal rows non-sleep totalling 960 min and actuals matching 780 min of them, when adherence is computed, then 81.25%.
- AC-062 Given today at 18:00, when adherence is read, then `provisional = true` and targets are scaled by 0.75.
- AC-063 Given sleep 23:00–07:00 ending on Tuesday, when sleep by wake date is read, then Tuesday shows 480 min.
- AC-064 Given a draft activity, when any aggregate runs, then it contributes 0.
- AC-065 Given a planned block, when weekly analytics run, then it contributes 0 to actuals.
- AC-066 Given no change since the last response, when the same URL is requested with `If-None-Match`, then 304.
- AC-067 Given breakdown filtered by tag `#p0`, when the matching Calendar filter is used, then the activity ids are identical.
- AC-068 Given 26 weeks of seeded data, when trends are requested 50 times, then p95 latency < 400 ms.

## M9 · Settings, Privacy & Platform

**Purpose.** Give the user control over preferences, data and AI use, and make the app safe to operate.

| ID | Requirement | Pri |
| --- | --- | --- |
| FR-145 | Preferences: timezone, week start, 12 / 24 h time, theme, coverage tolerance, gap minimum, short-night threshold, office hours, AI enabled, default coverage preset. | M |
| FR-146 | An AI & privacy panel states exactly what is sent to the provider and offers the AI on / off switch. | M |
| FR-147 | Export: an asynchronous job builds a ZIP (JSON of all tables plus activities CSV); a signed download link is valid 24 h. | M |
| FR-148 | Account deletion flow as FR-012, surfaced in Settings with the export offered first. | M |
| FR-149 | `auth_events` keeps login success, failure, password change and reset events for 90 days and is viewable by the user. | S |
| FR-150 | Rate limits: login 5 / 15 min, processing 10 / hour, transcription 20 / hour, general API 300 / min per user. | M |
| FR-151 | Frontend error tracking runs without user content; backend errors go to Sentry with scrubbed fields. | M |
| FR-152 | The app is an installable PWA with an offline shell and an offline journal draft (FR-014). | S |
| FR-153 | WCAG 2.1 AA contrast; every chart interaction works by keyboard focus as in the hover spec. | M |
| FR-154 | Responsive layouts at 1280, 768 and 360 px; mobile uses the bottom tab bar (D-11). | M |
| FR-155 | Scheduled jobs: purge soft-deleted rows after 30 days, expire tokens, expire export files, nightly backup check. | M |
| FR-156 | `GET /healthz` (process alive) and `GET /readyz` (database and queue reachable). | M |

**Acceptance criteria.**

- AC-069 Given AI turned off, when an entry is submitted, then no outbound LLM request is made.
- AC-070 Given an export request, when the job finishes, then the ZIP contains every entry, revision, activity, tag, task and ideal version of the user and nothing of any other user.
- AC-071 Given 11 processing requests in an hour, when the 11th arrives, then 429.
- AC-072 Given the database is down, when `/readyz` is called, then 503 while `/healthz` stays 200.
- AC-073 Given a Lighthouse run on Overview, when scored, then accessibility ≥ 95.

## Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-01 | Performance: CRUD p95 < 200 ms, analytics p95 < 400 ms, first contentful paint < 2 s on a mid-range phone over 4G. |
| NFR-02 | AI latency: submit → review-ready p50 < 12 s, p95 < 30 s for ≤ 800 words. |
| NFR-03 | Availability 99.5% monthly for the API; AI outage must not block manual logging. |
| NFR-04 | Security follows OWASP ASVS level 2 for authentication, session and access control (Section 14). |
| NFR-05 | Privacy: journal text never appears in logs, analytics tools or error reports. |
| NFR-06 | Accessibility: WCAG 2.1 AA. |
| NFR-07 | Browsers: last 2 versions of Chrome, Edge, Safari, Firefox; iOS Safari 16+. Dictation degrades to the recorder path where Web Speech is missing. |
| NFR-08 | Durability: RPO ≤ 24 h (target ≤ 5 min with point-in-time recovery), RTO ≤ 4 h. |
| NFR-09 | Observability: structured logs with request id, error tracking, uptime check, job failure alert. |
| NFR-10 | Maintainability: ≥ 80% line coverage on services and analytics; lint and type checks block merges. |
| NFR-11 | Time correctness: all stored instants are UTC `timestamptz`; all display and bucketing use the entry's IANA timezone. |
| NFR-12 | Limits: ≤ 10,000 characters per entry, ≤ 100 bulk ids, ≤ 366 days per range query. |

