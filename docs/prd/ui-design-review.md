# UI Design Review

The supplied Cadence file holds 24 boards (11 screens in light and dark, plus *Dependencies (parked)* and *Hover & Tooltip Spec*). Nine screens map directly to V1.0 modules, two (Team, Dependencies) fall outside V1.0, and 15 screens or dialogs needed for a complete app are missing. This tab records what exists, where it conflicts with the PRD, and which decisions resolve each conflict.

**Method and limits.** I unpacked all 24 boards and read their markup, labels, copy, placeholders and CSS tokens. I did not view rendered pixels, so spacing, exact component sizes and animation are for the frontend developer to take from the file itself. The file is the visual source of truth; where this PRD changes copy or scope, the change is listed here.

## A. Screen inventory and mapping

| Board (light + dark unless noted) | What the design shows | PRD module | Main APIs | V1.0 status |
| --- | --- | --- | --- | --- |
| 1 Sign in | Pitch panel with example "Becomes" card; Google, Apple, email + password, Forgot, keep-signed-in, create-account link, team invite link | M1 Auth | `/auth/*` | In, with changes (I-10) |
| 2 Journal | Dictate / Type toggle, "This entry covers" window, live transcript with timer, word count, "~N tasks found so far", time covered vs not mentioned, tag chip preview, Save draft, Create tasks, recent entries, today's 24h bar, yesterday-is-short nudge, "Cadence listens for" keyword rules, journal-habit stats | M2 Journal, M3 AI | `/journal-entries`, `/transcriptions`, `/journal-entries/{id}/process` | In |
| 3 Review extracted tasks | Header counters (tasks, time covered, not mentioned, to double-check, tags applied), 24h strip with gaps, task rows with tags + reason, per-row include checkbox, "What you said" panel with source highlights, Add task, Mark as transition, Today vs Ideal day panel | M3 Review | `/journal-entries/{id}/review`, `/review/commit` | In (+ clarification UI, I-16) |
| 4 Task detail | Time, Split, Duplicate, Delete, description + notes, tags with kind and reason, suggested tags, source sentence + Open entry, "#p0 this week vs Ideal week", history timeline, details (project, priority, where, logged via, linked deadline), "also tagged" list | M4 Activities, M5 Tasks | `/activities/{id}`, `/activities/{id}/events`, `/split` | In, with D-01, D-13 |
| 5 Tags | Chip style guide, groups with hours vs ideal bars, tag detail (colour, budget kind, keywords, per-day chart, recent tasks), New tag | M6 Taxonomy | `/tags`, `/categories`, `/analytics/breakdown` | In (+ category tree, I-02) |
| 6 Overview · Week | Banners, coverage, deep work, adherence trend, sleep, deadlines, actual vs ideal bars, work vs personal donut, 24h coverage columns, sleep bars, focus heatmap (26 wks), treemap, top tasks, deadlines, blocked & waiting, today's rhythm | M8 Analytics | `/analytics/overview?scope=week`, `/trends`, `/breakdown` | In: baseline Phase 4, advanced charts Phase 4B; cuts in I-07, I-08 |
| 7 Overview · Day | Coverage banner, KPI row, 24h clock (outer logged, inner ideal), hour-by-hour log with Fill buttons, shape of day vs Ideal, planned list, coming up | M8 Analytics | `/analytics/overview?scope=day` | In |
| 8 Calendar · Week (24h) | 24-hour grid, ideal overlay, unlogged hatching, coverage row, agenda, mini month, tag totals, Log time | M4 Activities | `/timeline`, `/activities` | In |
| 9 Ideal Day & Week | Hours per tag in 30-min steps, running total vs 24h, weekly table with per-day pace, tag caps outside the 168h, presets ("Fill from Ideal day × 7", "Weekdays + lighter weekends") | M7 Ideal | `/ideal/day`, `/ideal/week` | In |
| 10 Team Summary | Member table, team KPIs, bubble chart | none | none | **Out of V1.0** (D-09) |
| 11 Mobile | Greeting, day/week toggle, coverage nudge, KPIs, week strip, timeline, next deadline, bottom tab bar | all | same as desktop | In, nav changed (I-11) |
| 12 Dependencies (parked) | Gantt, dependency graph, burndown, blocked list | none | none | **Out of V1.0**; the design itself marks it parked |
| 13 Hover & Tooltip Spec | Nine chart-interaction patterns, timing, placement, keyboard and touch rules, theming | all charts | none | Adopted verbatim as the frontend interaction spec (Section 8) |

## B. Design system facts to reuse

- **Type:** Inter for UI, Space Grotesk for display numerals and headings.
- **Tokens (light / dark):** paper `#F6F6F2` / `#0E0F12`, ink `#17181C` / `#ECEDEF`, card `#FFFFFF` / `#16181C`, line `#ECECE6` / `#272A30`, muted `#5B6068` / `#B2B7BE`, faint `#8F959D` / `#6F747C`, good `#2E9E6B` / `#3DBB7E`, bad `#D4564F` / `#EE7570`, warn `#C27C22` / `#E3A043`, accent hues sky, teal, violet, rose, sleep `#5E6582` / `#8D95B8`, heatmap greens `h0`–`h4`, tooltip background stays dark in both themes. The frontend must ship these as CSS custom properties, not hard-coded colours.
- **Chips:** parent category = filled; tag = outlined with colour dot; auto-tagged = sparkle icon, hover shows the triggering words; needs-check = dashed amber with `?`; over-cap = red ring; tag path shown as `Work › #product-b`.
- **Navigation:** left sidebar (Workspace group) with user chip at the bottom; mobile uses a bottom tab bar.

## C. Inconsistencies between the designs and the recommended architecture

| ID | Observation in the design | Conflict | Resolution |
| --- | --- | --- | --- |
| I-01 | "Tasks" on Journal, Review and Task detail are time-bound records with start, end and duration | The brief requires journal entry, task and time record to be separate; a real Task must exist without time | UI says **Activity**; **Task** is a separate optional work item (D-01) |
| I-02 | Tags page: "every task has exactly one parent: Work, Personal or Sleep" and "3 parent tags"; Overview uses categories (Deep work, Meetings, Sales, Admin, Learning, Health) and a 3-level path (Work › Clients › Acme) | Two taxonomies on different screens | One **category tree** with three system roots; Tags screen gains a Categories tab (D-14) |
| I-03 | Ideal Day rows are "hours per tag" that must total 24h, yet the Ideal Week lists #social-media max 5h "not part of the 168h" | A tag that overlaps others cannot be in a 24h partition | Partition rows are **categories**; overlapping limits are **tag goals** (D-02, D-06) |
| I-04 | Task detail shows Project, Priority (P0), Where (Office), Linked deadline | No matching entities in the brief | `projects` table; priority and due date on Task; `location_type` on Activity (D-13) |
| I-05 | "Not mentioned" (Journal/Review), "Unlogged" (Overview/Calendar), "gap" | Three words for related ideas | **Unlogged** = no activity covers the time. **Not mentioned** = unlogged time *inside one entry's coverage window* (D-05) |
| I-06 | Calendar, Overview Day and Mobile show *Planned* blocks, "Planned for this day 3 of 5 done", "Fri–Sun shows your plan" | Planning is not in the brief; actual vs planned must never mix in analytics | Minimal `kind = planned` activities, excluded from actuals (D-12) |
| I-07 | Banner: "Moving Friday's 11:00 review protects a 4h focus block — projected adherence 81% → 88%" | Needs calendar integration and forecasting | Removed from V1.0; banners come from deterministic rules (D-09) |
| I-08 | Deadline cards: "at risk", "blocked", "Critical path", "Nudge" | Depend on the parked dependency model | V1.0 shows due date, status, days left, overdue only |
| I-09 | Journal says "Audio is deleted after transcription" while live interim text is shown | Live text implies in-browser recognition; deletion implies upload | Primary path never uploads audio; fallback uploads then discards; copy adjusted (D-08) |
| I-10 | Sign in: "Work email", "Joining a team? Use an invite link", "Only tags and totals are shared with your team", Apple button | Team and Apple are out of scope | Label "Email"; hide team link and sharing sentence; hide Apple (A-08, D-09) |
| I-11 | Mobile tab bar: Overview, Calendar, Chains, Ideal, Team | Omits Journal, the core capture flow, and Tags | Tabs: Overview, Journal (centre, mic emphasis), Calendar, Ideal, More (Tags, Tasks, Settings) (D-11) |
| I-12 | Mobile shows "Adherence 80%" for an unfinished day; Overview says actual vs ideal uses "completed days" | Partial days distort adherence | Today's adherence is **provisional**, prorated by elapsed time and labelled (D-07) |
| I-13 | Sidebar chip shows "Founder & CEO" | No field for it | Optional `users.role_title` |
| I-14 | "Sleep · last 7 nights" draws bed and wake times | Needs placed start and end; a duration-only sleep entry cannot be drawn | Sleep entries are prompted for times; unplaced sleep counts toward averages but not the bed/wake chart |
| I-15 | Journal shows "~N tasks found so far" and "15h 40m covered" while text is being entered | Running an LLM per keystroke is slow and costly | Live counters are client-side heuristics labelled "~"; exact values appear after extraction (D-21) |
| I-16 | Review shows flagged rows but has no place to *answer* the AI's questions | Clarification is required by the brief | New clarification strip and conflict dialog (D-17) |

## D. Missing screens (to be designed in the same visual language)

| ID | Screen / dialog | Why V1.0 needs it | Built from existing patterns |
| --- | --- | --- | --- |
| M-01 | Create account + verify email | Auth is incomplete without it | Sign-in card layout |
| M-02 | Forgot / reset password | Required for recovery | Sign-in card layout |
| M-03 | Onboarding wizard (timezone, seed taxonomy, Ideal Day preset, optional first entry) | Empty accounts have no categories or ideals | Ideal Day editor rows |
| M-04 | Journal history list + entry detail with revisions | Brief requires edit and view history | Recent-entries cards |
| M-05 | Clarification strip and overlap / duplicate conflict dialog in Review | I-16 | Amber needs-check chips, Review rows |
| M-06 | Log time / Edit activity dialog (exact, about, "some time between"; planned toggle) | Manual correction and the Calendar "Log time" button | Task detail form fields |
| M-07 | Split and Merge dialogs | Brief requires split and merge | Calendar block + time inputs |
| M-08 | Tasks list and Task detail (rollups, linked activities, due date, status); Projects manager | Task is its own entity (D-01) | Tags page list + detail layout |
| M-09 | Tag merge, archive, delete dialogs; category tree manager | Brief requires merge and archive | Tags page detail panel |
| M-10 | Ideal version history and "apply from" dialog | Template edits must not rewrite history silently | Ideal Day editor |
| M-11 | Settings (profile, timezone, preferences, AI and privacy, export, delete account, theme) | Privacy requirements | Tags page two-pane layout |
| M-12 | Global empty, error, offline and AI-failed states ("Retry" or "Enter manually") | Reliability | Existing banner style |
| M-13 | Search and filter bar for activities | Brief requires search and tag filtering | Calendar header |
| M-14 | Mobile Journal (full-screen dictation), Review (stacked cards), Tags, Settings | Mobile covers only Overview today | Mobile board components |
| M-15 | Task picker / link-to-task popover | Linking activities to tasks | Tag picker popover |

## E. Decisions register

| ID | Decision | Rationale | Impact if changed |
| --- | --- | --- | --- |
| D-01 | Entities: Journal Entry → Activity (time record) → optional Task; UI copy "task" becomes "activity" | Brief demands separation; a Task can have zero or many time records | Merging Task into Activity loses multi-day rollups |
| D-02 | Every activity has exactly **one category** (partition) and **many tags** (overlay) | Prevents double counting; keeps flexible slicing | Multi-category needs fractional allocation rules |
| D-03 | Confirmed actual activities cannot overlap (DB exclusion constraint) | Exact 24h math; trivial coverage | Allow overlap = weighted minutes |
| D-04 | Time model: `placement` (placed / unplaced) and `time_certainty` (stated / inferred / estimated) | Honest representation of vague input | — |
| D-05 | Entries declare a coverage window; gaps are computed, never stored | Distinguishes "did nothing" from "not logged" | — |
| D-06 | One Ideal Day and one Ideal Week, versioned by `effective_from`; totals must equal 24h / 168h; tag goals are overlays outside the total | Matches design; keeps history honest | Named templates in V1.1 |
| D-07 | Adherence = Σ min(actual, ideal) ÷ Σ ideal over non-sleep categories; today is provisional | Simple, explainable, bounded 0–100% | Different formula changes every historical number |
| D-08 | Dictation: Web Speech API live; server transcription fallback; audio never stored | Matches live-transcript design; low cost | Server-only loses live text |
| D-09 | Team, Dependencies, forecasting insights, blocked / at-risk are out of V1.0 | Brief excludes social and peer features; design parks dependencies | Adds workspace and graph models |
| D-10 | Auth: email + password and Google; Apple deferred | Apple needs paid programme | Add provider later |
| D-11 | Mobile tab bar: Overview, Journal, Calendar, Ideal, More | Journal is the product's core action | — |
| D-12 | `kind = planned` activities exist but never count as actual | Design shows plans; analytics integrity | Drop planned = remove 3 UI areas |
| D-13 | Project is a table; priority and due date live on Task; location is `location_type` on Activity | Maps design fields to data | — |
| D-14 | Overview categories and treemap use the single category tree | One taxonomy everywhere | — |
| D-15 | Analytics read `activity_day_slices` (activity clipped to local days) | Correct midnight and DST handling | Direct interval math per query is slower and error-prone |
| D-16 | Re-extraction creates new drafts; on commit the user chooses replace or keep; user-edited activities are never replaced silently | Protects manual work | — |
| D-17 | Clarification questions are answered in Review and applied by deterministic code, not another LLM call | Cheap, predictable | — |
| D-18 | No Redis; background jobs use a Postgres-backed queue | One fewer moving part | Revisit if job volume grows |
| D-19 | Self-managed auth in the API (argon2id, JWT + rotating refresh cookie) | Data stays in one DB; no vendor lock-in | Managed auth reduces code, adds a vendor |
| D-20 | Hosting: Cloudflare Pages + Railway + Postgres + R2 backups (Section 13) | Low cost, simple deploys | Portable via Docker |
| D-21 | Journal live counters are client-side heuristics, not AI | Cost and latency | — |

