# Handoff — coverage "Generate" button, m4 done + verified end-to-end; m5 next

Full milestone specs: **`docs/MILESTONES.md`**. This doc only carries state + deltas.

## Goal
A professor clicks **Generate** under a topic on `/coverage`; the system retrieves the
teaching section, generates grounded questions, flags likely duplicates, and drops them
into the review queue. **m1, m2, m3, m4 done.** m4 is not yet committed (see below).
Active: **m5** (auto-embed on ingest + retrieval status endpoint).

## Real end-to-end click-through, this session (found + fixed a real bug)
Drove the actual Generate button in Chrome against a live backend (SSLKEYLOGFILE
unset — see gotcha below) for the "Sets" topic (12 gap cells, the smallest topic).
First attempt: real 500 after ~30s, even though the backend kept working and the
12 questions landed in the DB moments later (`validation_passed`, topic_id 12) —
the professor would see a false failure for a run that actually succeeded.

**Root cause**: `frontend/next.config.ts`'s `/api/*` rewrite proxies through Next's
built-in `httpxy` proxy, which defaults `proxyTimeout` to **30000ms**
(`node_modules/next/dist/server/lib/router-utils/proxy-request.js:37`) when not set.
Coverage generation does one retrieval + one LLM call **per gap cell, sequentially**
(`app/web/routes/api/coverage.py:run_generation_for_gaps`) — every topic in the
Sample taxonomy needs at least 12 targets (smallest is "Sets"; largest, "Functions",
is 42), and each round-trip is ~8-10s against openrouter/gpt-4o. So **every**
topic-level Generate click exceeds 30s and hits this proxy timeout; the small
manual check from the previous session (traced only the SSLKEYLOGFILE 500, see
[[avast-sslkeylogfile-500]]) didn't run long enough to expose it.

**Fix**: `frontend/next.config.ts` now sets `experimental.proxyTimeout: 600_000`.
Re-ran the same click after restarting the frontend: run completed in ~119s, UI
showed "12 generated · 1 possible duplicate · 3 on a different topic" with a working
"Review these →" link to `/questions?run_id=...`, which correctly narrowed to
exactly those 12 rows. This fix must ship with m4 — without it the feature doesn't
work end-to-end for any real topic, only for a hypothetical ≤3-target one.
Touched-files list below now also includes `frontend/next.config.ts`.

## Done this session (m4, not yet committed)
- `frontend/src/app/coverage/components/coverage-grid.tsx` — the placeholder button
  (`onClick={() => {}}`) is wired. `topicGapTargets(topic)` builds the `CoverageTargetRef[]`
  from every cell with `needed > 0` across the topic's subtopics; `TopicGenerateButton`
  owns its own `useGenerateCoverageRun()` mutation (spinner + disabled while pending,
  disabled entirely when `topicGapTargets` is empty), renders the inline "N generated ·
  M possible duplicates · K on a different topic" summary plus a `Review these →` link to
  `/questions?run_id=...` on success, and `QueryError` on failure.
- `frontend/src/lib/api/queries.ts:useGenerateCoverageRun` — `POST
  /api/coverage/generation-runs`, invalidates `coverage`, `questions`, `system.counts`.
- **Backend gap closed**: `run_id` query param on `GET /api/questions`
  (`app/persistence/repositories.py:QuestionRepository.list_recent`, joins through
  `QuestionEvaluationRow`; wired through `app/web/routes/api/questions.py` and echoed on
  `QuestionListResponse.run_id`). `frontend/src/app/questions/questions-browser.tsx` reads
  it as a `nuqs` URL param (`?run_id=`) alongside the existing filters, shown as an active
  filter chip, cleared by "Clear filters".
- **Backend gap closed**: `GenerationRunResponse.possible_duplicates: int` —
  `app/web/routes/api/dedup.py:flag_possible_duplicates` now returns how many of the rows
  it was given received ≥1 flag (question count, not flag-pair count); accumulated in
  `run_generation_for_gaps` (`app/web/routes/api/coverage.py`).
- `frontend/src/lib/api/schema.d.ts` regenerated (`pnpm run api:types`); `types.ts` gained
  `CoverageTargetRef`, `GenerationRunResponse`.
- `tests/test_api.py` — one exact-dict assertion updated for the new `run_id: None` field.
- `frontend/src/app/coverage/components/coverage-grid.test.tsx` — mocks
  `useGenerateCoverageRun` from `@/lib/api/queries` (same pattern as
  `question-review.test.tsx`); covers click→mutate-with-targets, disabled-when-no-gaps,
  pending spinner, success summary + review link, and the readable error render. 5 new
  tests, all passing alongside the existing render test.
- `docs/MILESTONES.md` — m4 marked ✅ with 3 deviations (the two gap-closures above, plus
  reaffirming the existing 409→422 deviation from m2/m3); active → m5.

## Verified, how
- `.\.venv\Scripts\python.exe -m pytest -q` — full suite green (backend, background run).
- `pnpm biome lint src/app/coverage src/app/questions src/lib/api` — clean.
- `pnpm tsc --noEmit` — clean.
- `pnpm vitest run src/app/coverage src/app/questions` — 39 passed.
- **Manual click-path**: hit a real 500 clicking Generate in Chrome against the running
  `:8099` dev backend. Traced it to a **pre-existing local-machine issue, not a code bug**:
  `SSLKEYLOGFILE` is set (User env var) to `\\.\aswMonFltProxy\<id>` — an Avast SSL-inspection
  pipe — and Python 3.12's `ssl.create_default_context()` throws `PermissionError` trying to
  open it, which breaks *any* fresh `openai`/`httpx` client construction (also shows up as
  `pip_system_certs: ERROR: could not inject truststore` at process startup, before any
  request). This would break m1–m3's embedder calls too; it isn't m4-specific and pytest
  never hits it because tests override the embedder dependency.
  Confirmed the endpoint itself is correct by starting a throwaway backend on `:8100` with
  `SSLKEYLOGFILE` unset for that process only (`unset SSLKEYLOGFILE && uvicorn app.main:app
  --port 8100`, killed after): real generation run succeeded end to end (`possible_duplicates`
  present, `aim_matched: true`), and `GET /api/questions?run_id=...` correctly narrowed to
  just the new question. **Not fixed** — it's a local Avast/Python interaction, not
  something a code change addresses; workaround is `unset SSLKEYLOGFILE` (or exclude
  python.exe from Avast's SSL scan) before starting the real `:8099` dev server if a professor
  wants to click through the UI on this machine.

## Not done / next
1. **Commit m4** before starting m5 (per workflow: one milestone per session, commit
   before the next). Touched: `app/web/routes/api/{coverage,dedup,questions}.py`,
   `app/persistence/repositories.py`, `app/web/routes/api/schemas.py`, `tests/test_api.py`,
   `frontend/src/lib/api/{queries,types,schema.d.ts}.ts`,
   `frontend/src/app/coverage/components/coverage-grid.{tsx,test.tsx}`,
   `frontend/src/app/questions/questions-browser.tsx`, `frontend/next.config.ts`,
   `docs/MILESTONES.md`.
2. **Start m5** — auto-embed on ingest (`app/ingestion/service.py` calls
   `SectionEmbeddingStore.backfill(book_id=...)` after import) + `GET
   /api/retrieval/status`. See `docs/MILESTONES.md` "m5" for the full spec.
3. Optional follow-up, not blocking: the local `SSLKEYLOGFILE`/Avast issue above will
   recur for any manual click-path check on this machine until it's worked around outside
   this repo (unset the env var for the shell that starts uvicorn, or exclude python.exe
   from Avast SSL scanning).

## Files that matter (m5)
- `app/ingestion/service.py`, `app/retrieval/store.py`, `app/web/routes/api/retrieval.py`,
  `tests/test_retrieval.py`, `tests/test_ingestion_service.py` — see MILESTONES.md "m5".

## Gotchas (carried forward + new)
- **`app.coverage` must not import `app.generation`**, and **`app.generation` must not
  import `app.retrieval`** (its own docstring).
- **`get_query_embedder()` raises `ConfigurationError` (500)** when `LLM_PROVIDER=none`.
  Tests override it (`_run` helper in `tests/test_coverage.py`).
- **Test DB visibility**: `session` fixture and the app's `TestClient` use separate
  `Engine`s on the same sqlite file; only *committed* writes cross over.
- **`session.rollback()` mid-request expires ORM instances** — read primitive fields off a
  row before any later call that might fail and roll back.
- **`_generate_specs` commits per question** — no single transaction around a run.
- Full `pytest -q` takes ~2 min — run it in the background.
- **New**: on this machine, `SSLKEYLOGFILE` env var points at an Avast SSL-inspection pipe
  and breaks fresh `openai`/`httpx` client construction with `PermissionError` — see
  "Verified, how" above. Affects any endpoint that builds a real embedder/LLM client, not
  just coverage generation. `unset SSLKEYLOGFILE` before starting uvicorn to work around it
  for manual testing.
- Untracked spike files + `*_fresh_*.log` litter the repo root (pre-existing); don't commit
  them.
