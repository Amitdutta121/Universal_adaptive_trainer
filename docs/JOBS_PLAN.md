# Jobs — final plan (built on `dev`)

**Goal:** start a long task, leave the page or close the tab, and it keeps
running. A **Jobs** button in every page header shows what is running and what
finished. Clicking it opens a popover; **View all jobs** (or clicking a job)
opens the run-detail window.

Approved look: `docs/mockups/jobs-header-v3.html`

---

## 1. What shows up as a job

| Job | Started from | Today on `dev` | Change |
|---|---|---|---|
| **Question round** | Questions → **Set up questions** → Approve (round 1); Review → **Next round** | Already in the background: `generation_rounds` row + `BackgroundTasks` | **Shown in Jobs.** Fixed so a restart can't leave it stuck |
| **Bulk generation** | `/questions/generate` | Synchronous request | Moves to the background, shown in Jobs |
| **Coverage gap fill** | `/coverage` | Synchronous request + in-memory "running topics" set | Moves to the background, shown in Jobs; in-memory set removed |
| **Judge run** | **New "Run judges" button on `/judges`** | API only; results collected by a manual poll | Button + confirm; results collected automatically; shown in Jobs |

**Not jobs:** single-question generation, book import, taxonomy import,
refreshes, regenerate, and live student questions (which run on the student's
side and are internal).

---

## 2. How it runs (same pattern `dev` already uses for rounds)

1. The request checks everything that can fail up front (course, curriculum,
   question types). It saves a row as **queued**, replies `202`, and schedules
   the work with FastAPI `BackgroundTasks`.
2. The background function opens its own DB session and claims the row
   atomically (queued → **running**). It commits after every question, so
   progress is visible and nothing paid for is lost.
3. It ends as **done** (with its results stored on the row) or **failed** (with
   the error). It never raises out of the task.
4. Closing the tab doesn't affect the job.

**Storage:**
- New `jobs` table (Alembic migration `0011_jobs`), used only by bulk
  generation and coverage gap fill. It holds `course_id`, kind, title, status,
  done/total, the request, the result, the error and timestamps.
- Rounds keep `generation_rounds`; judge runs keep `judge_batch_runs`.

**One list for the UI:** `GET /api/jobs` (course-scoped) merges all three
sources into one shape.

**Blocking duplicate starts:**
- Rounds: one active round per taxonomy (unchanged).
- Coverage: a topic with a queued or running job is refused (the jobs table
  replaces the in-memory set).
- Judge runs: one active run per course.

**When the server restarts:**
- Queued or running rounds and jobs are marked **failed — "interrupted by a
  server restart"**. Questions already made are kept. Today a stuck round
  blocks every later round on its taxonomy forever.
- Judge runs **resume**: their results are still coming at the provider, so
  collection restarts.

**Judge results:** a background thread polls the provider every 60 s and
records results until the run finishes, both after submitting and after a
restart.

---

## 3. What you see

- **Jobs button** in `PageHeader`, next to the taxonomy selector: a spinner
  and the running count when anything is running.
- **Popover:** In progress (with progress bars), the 3 most recent finished
  jobs, and **View all jobs →**.
- **Run-detail window:**
  - Left: All / Active / Done / Failed tabs.
  - Right: status, numbers (made / dropped / skipped / failed), error, and a
    link to the results (review queue for a round, questions filtered by run id
    for generation).
  - Deep link: `?job=<id>`.
- **Toast** when a job finishes while you're anywhere in the Studio.
- **Bulk generate / coverage pages:** show "Started — running in Jobs". The
  page follows its job and shows today's results when it finishes.
- **Run judges (`/judges`):**
  - The confirm step shows how many questions will be re-judged.
  - The button is disabled while a run is active, or with the reason when
    re-runs are switched off (`JUDGE_BATCH_ENABLED`).
- **Refresh:** the UI checks every 2 s while anything is active, otherwise every 30 s.

---

## 4. Testing

- **pytest:** `TestClient` runs `BackgroundTasks` before returning, so a
  request-level test sees the finished job. Fake LLM clients come in through
  the existing dependency overrides.
- **New tests:**
  - bulk generation and coverage end done (results stored) or failed (error
    stored, made questions kept);
  - restart marks rounds and jobs failed and unblocks the next round;
  - jobs list is course-scoped (account isolation sweep);
  - judge auto-collection runs to completion with a fake transport.
- **Existing guards kept green:**
  - `test_every_route_is_classified`;
  - the LLM-route list;
  - `alembic check` (migrations match models).
- **Frontend:** Vitest for the Jobs menu, dialog, generate/coverage "Started"
  states and the Run judges confirm; `biome lint` + typecheck.

---

## 5. Cancel and retry

- **Cancel** (`POST /api/jobs/{id}/cancel`): bulk generation, coverage fill and question
  rounds.
  - A queued job ends at once.
  - A running job finishes the question in flight (already paid for) and stops before the
    next.
  - It shows as **Cancelled**, and everything made before the stop is kept.
  - Judge runs can't be cancelled: the provider's batch API offers no cancel, only deleting
    a finished batch, so the window says so.
- **Retry** (`POST /api/jobs/{id}/retry`) starts a *new* job:

  | Kind | What a retry does |
  |---|---|
  | Bulk generation | Only the questions not reached yet (resumes the fixed plan at `start_at`) |
  | Coverage fill | Gaps not reached; for a finished run, the gaps that failed |
  | Question round | Starts the next round |
  | Judge run | Submits again |

  - The server sends the button text (`retry_label`, e.g. "Retry the remaining 14").
  - A background job can be retried once, so the same questions are never made twice.
- **Storage:** migration `0012` adds `cancel_requested_at` to `background_jobs` and
  `generation_rounds`. A cancelled job is stored as failed with that column set.

## 6. Not doing

- A log pane: the window shows counts and the error
- Celery/Redis; SSE/WebSockets
- A sidebar Jobs item
