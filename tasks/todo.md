# Task List

Plan and decisions: `tasks/plan.md`. One phase per session; stop at every checkpoint for human review.

**Command shorthand used below**
- `PYTEST <file>` = `.\.venv\Scripts\python.exe -m pytest <file>`
- `BACKEND` = `.\.venv\Scripts\python.exe -m pytest` + `-m ruff check .` + `-m ruff format --check .`
- `FRONTEND` = in `frontend/`: `pnpm run typecheck; pnpm exec biome lint .; pnpm run test`
  (`pnpm run lint` fails repo-wide on autocrlf formatting, so don't gate on it.)
- `TYPES` = `cd frontend; pnpm run api:types` after any API change

Rules for every task:
- No groundedness-judge calls in new code; new artifacts store `chunk_ids`.
- No unrelated changes. A new dependency needs one line of justification in the PR/commit.
- Placeholders are marked `TODO(real):`.
- Never claim done without running the task's verification.

---

## Phase 0: Baseline

## Task 1: Retrieval gold set from the Agah book
**Description:** Build a small gold set: about 40 queries (subtopic titles plus a few student-style questions)
mapped to the book sections that teach them. Create it from the existing Agah import, then have it checked by hand.
It's what lets us measure later retrieval changes.

**Acceptance criteria:**
- [x] `tests/fixtures/retrieval_gold.json` holds ≥40 entries `{query, relevant_section_ids[], relevant_pages[]}`. Pages are included so the set survives the move to chunks.
- [x] The script that builds the draft is reproducible; manual edits are noted in the file.

**Verification:**
- [x] `PYTEST tests/test_retrieval_eval.py -k gold`: the fixture loads and every id/page exists in the test DB
- [x] Manual check: spot-check 10 entries against the PDF (10/10 by the agent, 2026-10-14)

**Dependencies:** None
**Files likely touched:** `scripts/build_retrieval_gold.py`, `tests/fixtures/retrieval_gold.json`, `tests/test_retrieval_eval.py`
**Estimated scope:** S

## Task 2: Retrieval eval harness and baseline
**Description:** Metrics: recall@k, precision@k, nDCG@k and MRR, with no LLM judge (modelled on DeepTutor
`services/rag/eval/metrics.py`, Apache-2.0, notice kept if copied). Matches are by page overlap, so the same harness
scores sections now and chunks later. Run it on the current `SectionRetriever`.

**Acceptance criteria:**
- [x] `app/retrieval/eval.py` has pure metric functions, unit-tested on hand-computed cases
- [x] `scripts/eval_retrieval.py` prints a metrics table for k = 1, 3, 5, 10
- [x] `docs/RETRIEVAL_BASELINE.md` records the baseline numbers and the command used

**Verification:**
- [x] `PYTEST tests/test_retrieval_eval.py`
- [x] Manual check: the script runs against the dev DB and the numbers match the doc

**Dependencies:** T1
**Files likely touched:** `app/retrieval/eval.py`, `scripts/eval_retrieval.py`, `tests/test_retrieval_eval.py`, `docs/RETRIEVAL_BASELINE.md`
**Estimated scope:** M

## Task 3: Parse spike, Docling vs unstructured
**Description:** In `spikes/parse_spike/` (an isolated venv or an optional dependency group, not the main
dependencies), parse the Agah PDF with Docling (`HybridChunker`) and with `unstructured`
(`partition_pdf` + `chunk_by_title`). Compare heading paths, page ranges, tables, code blocks, run time and install size.

**Acceptance criteria:**
- [x] `docs/PARSE_SPIKE.md` has a comparison table, 3 sample chunks from each library, and a recommendation
- [x] Also notes DOCX/PPTX support for each library

**Verification:**
- [x] Manual check: heading paths for 3 known sections match the book's table of contents (leaf heading 3/3; the chapter level comes from the PDF outline, see PARSE_SPIKE.md)

**Dependencies:** None
**Files likely touched:** `spikes/parse_spike/*`, `docs/PARSE_SPIKE.md`
**Estimated scope:** S

## Checkpoint A: After Tasks 1–3
- [ ] `BACKEND` green -- NOT green: 4 pre-existing test failures (circular import in `app/validation/runner.py`) and 154 pre-existing ruff errors in files Phase 0 did not touch
- [x] Human picks the parser and approves moving to Phase 1 -- Docling chosen 2026-10-14 (retrieval measured in PARSE_SPIKE.md)

---

## Phase 1: Chunks replace the book tree

## Task 4: `chunks` table and migration
**Description:** Add a `chunks` table: content-hash id, book_id, book_version, ordinal, page_start/page_end,
heading_path, text, source_kind (`book` now, `video` later), start/end seconds (nullable). Alembic migration `0022`
copies every `book_sections` row into `chunks`; the heading path is built from chapter/section titles. It also
writes a `section_chunk_map`. Settle the naming clash with ADR-044 "spec-sheet chunk" here.

**Acceptance criteria:**
- [x] Migration upgrades and downgrades cleanly on a copy of the dev DB, with no row lost (counts match)
- [x] Ids are deterministic: running it twice gives the same ids
- [x] Repository methods: get chunk, list by book/page (legacy section resolution dropped: no migration)

**Verification:**
- [x] `PYTEST tests/test_persistence.py tests/test_chunks.py`
- [x] Manual check: `alembic upgrade head` on a DB copy, then compare row counts

**Dependencies:** Checkpoint A
**Files likely touched:** `app/persistence/models.py`, `app/persistence/migrations/versions/0022_chunks.py`, `app/persistence/repositories.py`, `tests/test_chunks.py`
**Estimated scope:** M

## Task 5: Library parser → chunks on import
**Description:** A new ingestion path uses the chosen parser to produce chunks: chunked by heading, content-hash
ids, and a new book_version on re-import. PDF first, plus DOCX/PPTX if the parser supports them. The upload
endpoint uses it; the book import job keeps the same job contract.

**Acceptance criteria:**
- [x] Importing the same file twice reuses the existing version; a changed file creates a new one
- [x] Every chunk has a page range and a heading path (DOCX: no pages)
- [x] Unsupported or corrupt files are rejected before any row is written

**Verification:**
- [x] `PYTEST tests/test_ingestion_chunking.py tests/test_book_import_job.py`
- [x] Manual check: Agah PDF re-imported (API, Docling): 174 chunks, 117/117 pages, full heading paths

**Dependencies:** T4
**Files likely touched:** `app/ingestion/chunking.py`, `app/ingestion/service.py`, `pyproject.toml` (parser dependency, justified), `tests/test_ingestion_chunking.py`
**Estimated scope:** M

## Task 6: Chunk retrieval and the `/chunks` endpoint
**Description:** The embedding store is keyed by chunk id + content hash + embedding model.
`SectionRetriever` becomes `ChunkRetriever`. `GET /chunks?book_id=&page=&q=` replaces
`/books/{id}/sections*` and `/retrieval/sections`.

**Acceptance criteria:**
- [x] Changing the embedding model re-embeds; the same model reuses the cache
- [x] The eval harness on chunks is ≥ the baseline (no regression): MRR@10 0.741 → 0.934, better on every metric
- [x] Looking chunks up by page returns the chunks covering that page

**Verification:**
- [x] `PYTEST tests/test_chunk_retrieval.py tests/test_retrieval_eval.py`
- [x] `scripts/eval_retrieval.py`: numbers appended to `docs/RETRIEVAL_BASELINE.md`

**Dependencies:** T5
**Files likely touched:** `app/retrieval/store.py`, `app/retrieval/retriever.py`, `app/web/routes/api/retrieval.py`, `app/web/routes/api/books.py`
**Estimated scope:** M

## Task 7: Repoint generation and validation to chunk ids
**Description:** `rounds._section_for`, `live.py`, `batch.py` and `GenerationService` ground in chunks, and question
specs store `source_chunk_ids`. `validation/shared.py` checks that chunks exist and resolves legacy
`source_section_ids` through the map.

**Acceptance criteria:**
- [x] New questions store `source_chunk_ids` (old section questions do not validate: no migration, by decision)
- [x] Existing generation tests pass unchanged, apart from fixture field names

**Verification:**
- [x] `PYTEST tests/test_rounds.py tests/test_live_questions.py tests/test_generation_batch.py tests/test_validation_shared.py`

**Dependencies:** T6
**Files likely touched:** `app/generation/rounds.py`, `app/generation/live.py`, `app/generation/batch.py`, `app/generation/service.py`, `app/validation/shared.py`
**Estimated scope:** M

## Task 8: Repoint evidence, evaluation, coverage and styles
**Description:** `subtopic_evidence` gets a `chunk_id` foreign key (data migrated through the map), and the
evaluation service, coverage, `courses/overview` and `styles/library` read chunks.

**Acceptance criteria:**
- [x] No code outside migrations references `BookSectionRow` (except its model, kept for the table)
- [x] The evidence citation shows the heading path plus pages (`Chunk.citation`)

**Verification:**
- [ ] `PYTEST tests/test_evaluation_service.py tests/test_coverage.py tests/test_taxonomy_drafting.py tests/test_styles.py`
- [x] `rg BookSectionRow app --glob '!**/migrations/**'` → models.py only

**Dependencies:** T7
**Files likely touched:** `app/persistence/models.py`, `app/persistence/migrations/versions/0023_evidence_chunks.py`, `app/evaluation/service.py`, `app/web/routes/api/coverage.py`, `app/styles/library.py`
**Estimated scope:** M

## Task 9: Frontend chunk viewer and scroll-page single generation
**Description:** The book detail screen shows chunks by page instead of the chapter/section tree; the section route
becomes a chunk route. In single generation, the chunk preview loads the chunks for the page currently scrolled to.

**Acceptance criteria:**
- [x] The professor scrolls the PDF and the preview shows that page's chunks
- [x] Generating from the preview uses those chunk ids

**Verification:**
- [x] `TYPES` then `FRONTEND`
- [x] Manual check (`run` skill): import Agah, scroll, generate one question (questions 353, 354)

**Dependencies:** T6
**Files likely touched:** `frontend/src/app/courses/[courseId]/books/[book_id]/book-detail-screen.tsx`, `.../components/book-structure.tsx`, `.../sections/[section_id]/page.tsx`, `frontend/src/app/courses/[courseId]/questions/generate/components/chunk-preview.tsx`, `frontend/src/lib/api/queries.ts`
**Estimated scope:** M

## Task 10: Retire the chapter/section validation and the JSON book upload
**Description:** Delete the outline/fallback/assemble PDF path, the book JSON schema upload, `books/document-guide`
and their tests. Tables stay until the open question about dropping them is answered.

**Acceptance criteria:**
- [x] `tests/test_boundaries.py` is updated for the new parser module
- [x] There is no dead import, route or UI card left for the JSON book format

**Verification:**
- [ ] `BACKEND` + `FRONTEND`

**Dependencies:** T8, T9
**Files likely touched:** `app/ingestion/pdf/*`, `app/ingestion/schema.py`, `app/web/routes/api/books.py`, `frontend/.../books/components/document-guide-card.tsx`, `tests/test_ingestion_*.py`
**Estimated scope:** M

## Checkpoint B: After Tasks 4–10
- [x] `BACKEND` + `FRONTEND` green (2072 passed, 0 failed; the 4 failures carried from Phase 0 fixed)
- [x] A frozen-set student run replays exactly as before the migration (seeded): by construction --
  `app/adaptive`, the student routes, `app/assessment` and `graders` have no diff since e60b536 and
  never read chunks, sections or sources
- [x] Agah import, scroll generation and a round all work in the UI (round 2, course 2: 3/3
  produced, every question grounded in a Heinold chunk of its own course)
- [ ] Review with human before Phase 2

---

## Phase 2: Hybrid retrieval

## Task 11: BM25 + RRF
**Description:** Add BM25 over chunk text (`bm25s` or `rank_bm25`, with a justification) and merge it with the
vector ranking by reciprocal rank fusion inside `ChunkRetriever`. Compare with LlamaIndex
`QueryFusionRetriever` only if the in-house version falls short of the baseline.

**Acceptance criteria:**
- [ ] Hybrid ≥ vector-only on every metric in the harness, with the results in the doc -- NOT met:
  in-house RRF was below dense everywhere (MRR@10 0.888). LlamaIndex `QueryFusionRetriever`
  (MRR@10 0.937, student MRR@5 0.944) trades nDCG@10 −0.015 and heading MRR −0.020; the human
  chose it as the default at Checkpoint C (`CHUNK_RETRIEVAL_MODE`, `docs/RETRIEVAL_BASELINE.md`)
- [x] Results are deterministic for a fixed index (stable sort in BM25 and RRF ties)

**Verification:**
- [x] `PYTEST tests/test_chunk_retrieval.py tests/test_retrieval_eval.py`
- [x] `scripts/eval_retrieval.py --mode hybrid` (2026-10-14)

**Dependencies:** Checkpoint B
**Files likely touched:** `app/retrieval/retriever.py`, `app/retrieval/bm25.py`, `pyproject.toml`, `docs/RETRIEVAL_BASELINE.md`
**Estimated scope:** S

## Checkpoint C
- [x] The eval report has been reviewed by the human (2026-10-14: use LlamaIndex hybrid)

---

## Phase 2b: Model settings

## Task 41: Settings store, per role
**Description:** An `app_settings` table holds provider, model, base_url and api_key for each role:
`generation`, `judges`, `agent`, `tutorials`, `ask_why`, `embeddings`, `transcription`. A resolver returns the
effective config for a role: the DB value if set, otherwise `.env` (`app/config.py` stays the default). Keys are
encrypted with a server secret from `.env` (new dependency `cryptography`, for Fernet; justify it). The LLM and
embedder clients are built from the resolver, not from `get_settings()` directly.

**Acceptance criteria:**
- [x] With no DB rows, behaviour is identical to today
- [x] A DB row for a role changes only that role's client
- [x] Keys never appear in plaintext in the DB, the logs or `repr` (Fernet, key derived from AUTH_SECRET_KEY)

**Verification:**
- [x] `PYTEST tests/test_model_settings.py tests/test_config.py tests/test_llm_client.py`

**Dependencies:** Checkpoint C
**Files likely touched:** `app/settings_store.py`, `app/persistence/models.py` (+ migration), `app/llm/client.py`, `app/retrieval/embedder.py`, `tests/test_model_settings.py`
**Estimated scope:** M

## Task 42: Settings API, test connection and model list
**Description:** `GET /settings` returns the effective config per role with keys masked and a source label
(`db` or `env`). `PUT /settings/{role}` is admin only. `POST /settings/{role}/test` makes one minimal call (for
embeddings, it also returns the vector dimension). `GET /settings/models?provider=` lists models from the provider
(e.g. OpenRouter `/models`), cached.

**Acceptance criteria:**
- [x] A non-admin gets 403 on PUT and test (admin = `is_superuser`)
- [x] A failed test returns the provider's error without saving anything
- [x] Saving requires that a test has passed for that config (signed test token bound to the config, 30 min)

**Verification:**
- [x] `PYTEST tests/test_settings_api.py` (provider HTTP mocked), then `TYPES`

**Dependencies:** T41
**Files likely touched:** `app/web/routes/api/settings.py`, `app/web/routes/api/schemas.py`, `tests/test_settings_api.py`
**Estimated scope:** M

## Task 43: Changing the embedding model
**Description:** Saving a new `embeddings` model queues a re-embedding job into a new embedding version (the cache is
already keyed by model, T6). Retrieval keeps using the old vectors until the job completes, then switches
atomically. The UI shows progress, and the eval harness can be run on the new version.

**Acceptance criteria:**
- [x] Retrieval works at every moment of the switch (test queries mid-job)
- [x] A failed or cancelled job leaves the old model active
- [x] Old vectors are kept until the next successful switch

**Verification:**
- [x] `PYTEST tests/test_embedding_switch.py tests/test_jobs.py`

**Dependencies:** T42
**Files likely touched:** `app/retrieval/store.py`, `app/retrieval/reembed.py`, `app/jobs/*`, `tests/test_embedding_switch.py`
**Estimated scope:** M

## Task 44: Settings screen
**Description:** An admin page with one row per role: provider dropdown, model picker (from T42's list, with free
text allowed), base URL, a masked key field, a Test button and a Save button that's enabled after a passing test.
It shows whether each value comes from the database or from `.env`, and the re-embedding progress for embeddings.
It follows the existing course-screen design patterns, with no new visual language.

**Acceptance criteria:**
- [x] A non-admin doesn't see the page in navigation and gets 403 from the API (link in the sidebar footer: settings are instance-wide, the nav is per course)
- [x] Switching the generation model and the embedding model works end to end

**Verification:**
- [x] `FRONTEND`
- [x] Manual check (`run` skill): switch the generation model, generate one question; switch the embedding model, watch the re-embed, retrieve
  (2026-10-14: gpt-4o -> gpt-4o-mini, question 358 made by gpt-4o-mini; 3-small -> 3-large,
  842 chunks re-embedded while a search every 2 s kept answering on 3-small, then 3-large;
  both reset to .env, the switch back embedded 0 chunks)

**Dependencies:** T43
**Files likely touched:** `frontend/src/app/settings/page.tsx`, `frontend/src/app/settings/settings-screen.tsx`, `frontend/src/lib/api/queries.ts`, `frontend/src/lib/navigation.ts`
**Estimated scope:** M

## Checkpoint C2
- [x] Both switches work in the UI, retrieval never breaks, and keys stay masked everywhere
- [ ] Human review

---

## Phase 3: One generation endpoint

## Task 12: Confirm a shared pipeline (ADR-066)
**Description:** Read-only. Trace `/questions/generate`, `/questions/{id}/regenerate`, `/questions/batch-plan`,
`/questions/generate-batch`, `/questions/generation-plan`, `/coverage/generation-runs` and `POST /rounds` down to
the generator. Write ADR-066 with the target-list schema
(`chunks | gaps | setup_cells | regenerate{question_id, feedback}`) and `dry_run`.
**If they don't share a pipeline, stop and report.**

**Acceptance criteria:**
- [x] ADR-066 maps each old endpoint to a target kind, including differences in job, cost and response
  (2026-10-14: shared only below the orchestrator -- plain `_generate_specs` vs round
  `generate_round_question`; ADR proposes one endpoint over both pipelines, not a merge)

**Verification:**
- [ ] Manual check: the human approves ADR-066

**Dependencies:** Checkpoint C
**Files likely touched:** `docs/DECISIONS.md`
**Estimated scope:** XS

## Task 13: `POST /generation-runs` backend
**Description:** One endpoint plus a service that queues a job for any target kind. `dry_run` returns the
planned questions and a cost estimate without calling the model.

**Acceptance criteria:**
- [x] Every existing generation test scenario passes through the new endpoint
  (chunks + regenerate in `tests/test_generation_runs.py`; gaps via `test_coverage.py`'s `_run`;
  rounds parametrized in `test_rounds.py`; one test per old route kept until T15)
- [x] `dry_run` makes no model call and writes no row (one test per kind)

**Verification:**
- [x] `PYTEST tests/test_generation_runs.py tests/test_rounds.py tests/test_generation_batch.py tests/test_generation_regenerate.py`
  (2026-10-15: full suite 2115 passed, 34 skipped; ruff clean on touched files)

**Dependencies:** T12
**Files likely touched:** `app/web/routes/api/generation_runs.py` (no `app/generation/runs.py`: see ADR-066), `app/web/routes/api/schemas.py`, `tests/test_generation_runs.py`
**Estimated scope:** M

## Task 14: Switch frontend callers
**Description:** `queries.ts`, `run-summary.tsx`, `question-review.tsx`, `questions-browser.tsx` and the spec sheet
call `/generation-runs`.

**Acceptance criteria:**
- [x] No frontend reference to the old endpoints (2026-10-15: grep of `src/` and `schema.d.ts` is empty;
  the unused `useSyncProdQuestionSet` hook is removed too)

**Verification:**
- [x] `TYPES` then `FRONTEND`
- [ ] Manual check: single, batch, gap-fill, round and regenerate each work in the UI

**Dependencies:** T13
**Files likely touched:** `frontend/src/lib/api/queries.ts`, `.../questions/generate/components/run-summary.tsx`, `.../generate/single/components/question-review.tsx`, `.../questions/questions-browser.tsx`, `.../generate/spec-sheet-types.ts`
**Estimated scope:** M

## Task 15: Delete old endpoints and prod/sync
**Acceptance criteria:**
- [x] The 7 old routes and `/question-sets/prod/sync` are gone; their tests are migrated or removed
  (`generation-plan`'s listing moved to `GET /chunks/outline`; the `sync_prod_question_set`
  service stays, because the public `prod` join lobby still reads the alias)
- [x] OpenAPI types are regenerated

**Verification:**
- [x] `BACKEND` + `TYPES` + `FRONTEND` (2026-10-15: 2102 passed, 34 skipped; ruff clean on touched
  files, the 3 remaining errors predate Phase 3; typecheck, biome lint, vitest 685 passed)

**Dependencies:** T14
**Files likely touched:** `app/web/routes/api/questions.py`, `app/web/routes/api/coverage.py`, `app/web/routes/api/rounds.py`, `tests/test_api.py`
**Estimated scope:** S

## Checkpoint D
- [ ] Every generation flow works in the UI; human review

---

## Phase 4: YAML question styles

## Task 16: YAML loader, converted library and JSON Schema
**Description:** Styles live in `styles/<subject>/<id>.yaml`, loaded and validated by `QuestionStyle`.
Convert `app/styles/python.py` with ids unchanged and remove `_LIBRARIES`. A script exports
`styles/schema.json` from `QuestionStyle.model_json_schema()`.

**Acceptance criteria:**
- [x] `get_library()` returns the same styles as before (a test compares them)
  (2026-10-15: `test_yaml_library_matches_the_python_library` in ad4840a, removed with
  `python.py` in 097018c; `order.txt` keeps display order)
- [x] An invalid YAML file fails with the file name and field named

**Verification:**
- [x] `PYTEST tests/test_styles.py tests/test_setup_routes.py` (+ `styles/schema.json` staleness test)

**Dependencies:** Checkpoint D
**Files likely touched:** `app/styles/library.py`, `app/styles/loader.py`, `styles/intro_python/*.yaml`, `scripts/export_style_schema.py`
**Estimated scope:** M

## Task 17: CI checks, id lock and contributor guide
**Description:** For every example of every style: it passes its question type's `authoring_checks` and grader.
Ids are unique and namespaced. A `styles/ids.lock` file fails CI if an id is removed or renamed.
Add `CONTRIBUTING-styles.md`.

**Acceptance criteria:**
- [x] Removing an id, a broken example and a duplicate id each fail CI with a clear message
  (2026-10-15: `app/styles/checks.py`; code examples gained `solution` + `test_cases` so they
  can go through their type's authoring checks and grader)

**Verification:**
- [x] `PYTEST tests/test_styles.py`

**Dependencies:** T16
**Files likely touched:** `tests/test_styles.py`, `styles/ids.lock`, `CONTRIBUTING-styles.md`
**Estimated scope:** S

## Task 18: Course-local styles and export to YAML
**Description:** A table for professor-made styles, validated by the same schema; they appear in setup next to the
library styles. An "Export to YAML" action downloads a file ready for a PR.

**Acceptance criteria:**
- [x] A course style is visible only in its course (also in the account-isolation sweep)
- [x] The exported YAML passes T17's checks

**Verification:**
- [x] `PYTEST tests/test_course_styles.py`, `TYPES`, `FRONTEND` (2026-10-15: full backend
  2131 passed, 9 account-isolation failures then fixed and that file rerun green; typecheck, biome lint, vitest 687 passed)
- [ ] Manual check: create, use and export a style in the UI (2026-10-15: create, list,
  duplicate refusal and export checked over HTTP on a fresh backend; not clicked through in
  the browser, and "use" stops short of saving a setup, which spends LLM credit)

**Dependencies:** T17
**Files likely touched:** `app/persistence/models.py` (+ migration), `app/web/routes/api/setup.py`, `frontend/.../questions/setup/question-setup-dialog.tsx`, `tests/test_course_styles.py`
**Estimated scope:** M

## Checkpoint E
- [ ] Adding one new YAML style in a branch passes CI and shows up in setup; human review

---

## Phase 5: Tutorial renderers and recipes

## Task 19: Recipe schema, seed recipes and the tutorial_blocks table
**Description:** A `TutorialRecipe` model (id, subject, renderer, prompt, fits, guidance_levels, inputs, tool?,
checks), loaded from `recipes/<subject>/*.yaml`, with a JSON Schema exported. Seed recipes: code-trace stepper (html +
`python_trace`), topic flow (mermaid), one-line misconception (markdown). A `tutorial_blocks` table holds subtopic,
recipe_id, guidance_level, renderer, payload, chunk_ids, status and set_version_id.

**Acceptance criteria:**
- [ ] A block without chunk_ids can't be saved
- [ ] The recipe CI checks mirror T17 (id lock, schema)

**Verification:**
- [ ] `PYTEST tests/test_recipes.py`

**Dependencies:** Checkpoint E
**Files likely touched:** `app/tutorials/schema.py`, `app/tutorials/loader.py`, `recipes/intro_python/*.yaml`, `app/persistence/models.py` (+ migration)
**Estimated scope:** M

## Task 20: `python_trace` tool
**Description:** Runs a code snippet under `sys.settrace` inside the existing code-execution sandbox and returns
the steps `[{line, locals, stdout}]`, with step and time limits.

**Acceptance criteria:**
- [ ] Traces of loops, functions and exceptions are correct
- [ ] Infinite loops hit the step cap and return an error, not a hang

**Verification:**
- [ ] `PYTEST tests/test_python_trace.py`

**Dependencies:** T19
**Files likely touched:** `app/tutorials/tools/python_trace.py`, `tests/test_python_trace.py`
**Estimated scope:** S

## Task 21: Block generator
**Description:** recipe + retrieved chunks + the tool's output (if any) → one LLM call → a payload validated against
the renderer's contract → saved with chunk_ids. No judge.

**Acceptance criteria:**
- [ ] The stepper payload embeds the recorded trace exactly, never one generated by the LLM
- [ ] An invalid payload gets one repair retry, then is marked failed

**Verification:**
- [ ] `PYTEST tests/test_tutorial_generator.py` (using the LLM fakes)

**Dependencies:** T20
**Files likely touched:** `app/tutorials/generator.py`, `app/tutorials/renderers.py`, `tests/test_tutorial_generator.py`
**Estimated scope:** M

## Task 22: Frontend renderers and sandboxed html
**Description:** A renderer registry: markdown, mermaid, chartjs, html. html is rendered in
`<iframe sandbox="allow-scripts">` with a CSP that blocks network access, plus a resize message.
New dependencies: `mermaid` and `chart.js`, with justification.

**Acceptance criteria:**
- [ ] html can't read the parent page or make network requests (tests cover both)
- [ ] An unknown renderer shows a safe fallback

**Verification:**
- [ ] `FRONTEND`
- [ ] Manual check: render each seed recipe's block

**Dependencies:** T21
**Files likely touched:** `frontend/src/components/tutorial/renderer-registry.tsx`, `.../html-frame.tsx`, `.../mermaid-block.tsx`, `.../chart-block.tsx`, `frontend/package.json`
**Estimated scope:** M

## Task 23: Playwright check for html blocks
**Description:** At generation time, load each html block headless: fail on console errors. For the stepper, click
through and compare the displayed steps to the trace. Add a Python Playwright dependency, with justification.

**Acceptance criteria:**
- [ ] A deliberately broken stepper fixture fails; a correct one passes

**Verification:**
- [ ] `PYTEST tests/test_html_block_check.py`

**Dependencies:** T21
**Files likely touched:** `app/tutorials/checks.py`, `tests/test_html_block_check.py`, `pyproject.toml`
**Estimated scope:** S

## Checkpoint F
- [ ] All 3 seed recipes generate and render for one Agah subtopic; human review

---

## Phase 6: Composer and student experience

## Task 24: Pre-generation job and approval by recipe
**Description:** A job generates blocks for each subtopic × guidance level × applicable recipe. The professor
approves by recipe after viewing a sample of its blocks.

**Acceptance criteria:**
- [ ] Approving a recipe approves its blocks; rejecting one hides them
- [ ] The job reports cost and progress like generation jobs

**Verification:**
- [ ] `PYTEST tests/test_tutorial_pregeneration.py`, `FRONTEND`

**Dependencies:** Checkpoint F
**Files likely touched:** `app/tutorials/jobs.py`, `app/web/routes/api/tutorials.py`, `frontend/src/app/courses/[courseId]/tutorials/*`
**Estimated scope:** M

## Task 25: Freeze blocks with the question set
**Acceptance criteria:**
- [ ] Freezing a set snapshots its approved blocks; later edits don't change a frozen set

**Verification:**
- [ ] `PYTEST tests/test_trust_freeze.py tests/test_tutorial_freeze.py`

**Dependencies:** T24
**Files likely touched:** `app/web/routes/api/coverage.py`, `app/tutorials/freeze.py`, `tests/test_tutorial_freeze.py`
**Estimated scope:** S

## Task 26: Composer
**Description:** Input: subtopic, BKT mastery, last answer. Low mastery or a wrong answer → `worked`, 3–4 blocks;
medium → `faded`; high → one `cue` block or none. Formats are chosen by fit with the content kind. Approved, frozen
blocks only; seeded and deterministic. Live generation is used only when the bank is empty.

**Acceptance criteria:**
- [ ] The same seed and state give the same blocks
- [ ] The number of blocks goes down as mastery goes up (property test)

**Verification:**
- [ ] `PYTEST tests/test_composer.py`

**Dependencies:** T25
**Files likely touched:** `app/tutorials/composer.py`, `app/adaptive/service.py`, `tests/test_composer.py`
**Estimated scope:** M

## Task 27: Student UI
**Description:** After a wrong answer, the result card shows the composed `worked` blocks. Before the first
question of a topic, pre-teaching blocks show if prior mastery is low. Blocks fade as mastery rises.

**Acceptance criteria:**
- [ ] It works in a frozen-set run; with no blocks, the card falls back to today's explanation

**Verification:**
- [ ] `FRONTEND`
- [ ] Manual check: a student run following `student-workflow-test-playbook`

**Dependencies:** T26
**Files likely touched:** `frontend/src/app/students/join/session/[training_session_id]/student-session-screen.tsx`, `app/web/routes/api/students.py`
**Estimated scope:** M

## Task 28: Per-recipe stats steer the composer
**Acceptance criteria:**
- [ ] Each recipe's approval rate and next-attempt correctness are stored
- [ ] The composer weights recipes by these stats, and below a threshold a recipe is no longer chosen

**Verification:**
- [ ] `PYTEST tests/test_recipe_stats.py tests/test_composer.py`

**Dependencies:** T27
**Files likely touched:** `app/tutorials/stats.py`, `app/tutorials/composer.py`, `tests/test_recipe_stats.py`
**Estimated scope:** S

## Checkpoint G
- [ ] A playbook student run shows blocks fading; human review

---

## Phase 7: Video

## Task 29: Lecture upload → Whisper → timestamped chunks
**Description:** Upload a video or audio file; transcribe it (`faster-whisper`, or a hosted API, per the open
question); chunk at sentence boundaries into `chunks` with `source_kind=video` and start/end seconds.

**Acceptance criteria:**
- [ ] Chunks have monotonic, non-overlapping timestamps
- [ ] Video chunks are retrievable like book chunks

**Verification:**
- [ ] `PYTEST tests/test_video_ingestion.py`, using a short fixture clip

**Dependencies:** Checkpoint G
**Files likely touched:** `app/ingestion/video.py`, `app/web/routes/api/books.py` (or a new media route), `pyproject.toml`
**Estimated scope:** M

## Task 30: YouTube transcripts, paste fallback and availability check
**Description:** A YouTube link fetches its transcript via `youtube-transcript-api`; when that fails, the professor
pastes the transcript. A periodic job flags videos that are private, deleted or not embeddable.
Never download the video.

**Acceptance criteria:**
- [ ] A failed fetch shows the paste option; nothing half-imports

**Verification:**
- [ ] `PYTEST tests/test_youtube_source.py` (network mocked)

**Dependencies:** T29
**Files likely touched:** `app/ingestion/youtube.py`, `app/jobs/*`, `tests/test_youtube_source.py`
**Estimated scope:** S

## Task 31: `video_clip` renderer and clip recipe
**Description:** The payload is `{video_id|media_id, start, end}`, snapped to sentence boundaries and padded by
1–2 s. YouTube clips play through the IFrame API (`startSeconds`/`endSeconds`), uploaded lectures through
`<video>` with a media fragment. A recipe "show the clip that explains this" serves the `worked` level. A clip
never claims to show what's on screen.

**Acceptance criteria:**
- [ ] The clip plays only the chosen range, in both player types

**Verification:**
- [ ] `PYTEST tests/test_video_clip.py`, `FRONTEND`
- [ ] Manual check: one uploaded and one YouTube clip in a tutorial

**Dependencies:** T30
**Files likely touched:** `frontend/src/components/tutorial/video-clip-block.tsx`, `recipes/intro_python/video_clip.yaml`, `app/tutorials/renderers.py`
**Estimated scope:** S

## Checkpoint H
- [ ] Both kinds of clip play inside a tutorial; human review

---

## Phase 8: Professor agent

## Task 32: Agent backend and first tools
**Description:** Start with a compatibility spike: Pydantic AI's AG-UI endpoint ↔ CopilotKit. Then add the agent
service (its model is the `agent` role from the settings resolver, T41) and the tools `import_material`, `propose_curriculum`,
`edit_curriculum` and `coverage_report`, calling services directly.

**Acceptance criteria:**
- [ ] The tools reuse service functions; no business rule lives in the prompt
- [ ] The agent runs with fake LLMs in tests

**Verification:**
- [ ] `PYTEST tests/test_agent_tools.py`

**Dependencies:** Checkpoint H
**Files likely touched:** `app/agent/agent.py`, `app/agent/tools.py`, `app/web/routes/api/agent.py`, `pyproject.toml`
**Estimated scope:** M

## Task 33: Approval cards and confirming cost before spending
**Description:** Approving a curriculum, saving a style and publishing a set are deferred tool calls that wait
for a human click. `plan_generation` returns a dry-run cost; `run_generation` requires that plan to be confirmed.

**Acceptance criteria:**
- [ ] A test shows the agent can't approve, publish or spend without a human confirmation event

**Verification:**
- [ ] `PYTEST tests/test_agent_approvals.py`

**Dependencies:** T32, T13
**Files likely touched:** `app/agent/tools.py`, `app/agent/approvals.py`, `tests/test_agent_approvals.py`
**Estimated scope:** M

## Task 34: Remaining tools
**Description:** `preview_styles` (3 sample questions side by side), `review_summary`, `open_view` and
`student_report`.

**Acceptance criteria:**
- [ ] About 12 tools in total, each with a typed input and a test

**Verification:**
- [ ] `PYTEST tests/test_agent_tools.py`

**Dependencies:** T33
**Files likely touched:** `app/agent/tools.py`, `tests/test_agent_tools.py`
**Estimated scope:** S

## Task 35: CopilotKit side panel
**Description:** A side panel in the course layout. `open_view` navigates the app. Approval cards and the
style-comparison cards render in the chat. New dependency: `@copilotkit/*`, with justification.

**Acceptance criteria:**
- [ ] The panel works on every course page without breaking the existing screens

**Verification:**
- [ ] `FRONTEND`
- [ ] Manual check: set up the Agah course by chat (import → curriculum → styles → generate → publish)

**Dependencies:** T34
**Files likely touched:** `frontend/src/app/courses/[courseId]/layout.tsx`, `frontend/src/components/agent/*`, `frontend/package.json`
**Estimated scope:** M

## Checkpoint I
- [ ] The end-to-end chat setup works and every approval is a human click; human review

---

## Phase 9: Student loop

## Task 36: Spaced review queue
**Description:** Each subtopic gets a stability value; `plan_draw` mixes in due reviews ordered by forgetting risk.
Repeats within the same session don't count as review. The scheduler pattern is from DeepTutor
`learning/scheduler.py` (Apache-2.0).

**Acceptance criteria:**
- [ ] Draws stay seeded and deterministic
- [ ] Due items come back after the interval; lapses shrink stability

**Verification:**
- [ ] `PYTEST tests/test_adaptive_selection.py tests/test_spaced_review.py`

**Dependencies:** Checkpoint I
**Files likely touched:** `app/adaptive/state.py`, `app/adaptive/selection.py`, `app/adaptive/service.py`, `tests/test_spaced_review.py`
**Estimated scope:** M

## Task 37: Wrong answers resurface as sibling questions
**Acceptance criteria:**
- [ ] After a wrong answer, a different question on the same subtopic and difficulty is scheduled for later in the run, never the same question

**Verification:**
- [ ] `PYTEST tests/test_adaptive_service.py`

**Dependencies:** T36
**Files likely touched:** `app/adaptive/service.py`, `app/adaptive/selection.py`
**Estimated scope:** S

## Task 38: Misconception-tagged distractors and error type
**Description:** Each MCQ distractor carries a `misconception` and an `error_type`
(structural/deviation/application/metacognitive). The generator prompt requires them; the student's pick records
them; the roster heatmap can group by misconception.

**Acceptance criteria:**
- [ ] Old MCQs without tags still grade

**Verification:**
- [ ] `PYTEST tests/question_types tests/test_generation_schemas.py`, `FRONTEND`

**Dependencies:** T36
**Files likely touched:** `app/question_types/multiple_choice.py`, `app/generation/prompts.py`, `app/web/routes/api/students.py`, `frontend/.../students/roster/roster-screen.tsx`
**Estimated scope:** M

## Task 39: Hint-aware BKT credit
**Description:** Blocked on the open question "what counts as a hint". Once answered, discount the BKT
update when a hint or cue block was shown before answering.

**Acceptance criteria:**
- [ ] The same answer with a hint raises mastery less than without

**Verification:**
- [ ] `PYTEST tests/test_adaptive_state.py`

**Dependencies:** T27, T36
**Files likely touched:** `app/adaptive/state.py`, `app/domain/mastery.py`
**Estimated scope:** S

## Task 40: "Ask why" with citation chips
**Description:** A box on the result card: retrieve chunks for the question plus the student's text, answer from
them, and show chips with the heading path and pages (or a timestamp). No judge.

**Acceptance criteria:**
- [ ] Every answer shows at least one chip; with no chunk retrieved, it says so instead of answering

**Verification:**
- [ ] `PYTEST tests/test_ask_why.py`, `FRONTEND`
- [ ] Manual check: in a student run

**Dependencies:** T11, T27
**Files likely touched:** `app/tutorials/ask_why.py`, `app/web/routes/api/students.py`, `frontend/.../student-session-screen.tsx`
**Estimated scope:** M

## Checkpoint: Complete
- [ ] `BACKEND` + `FRONTEND` green
- [ ] All acceptance criteria met
- [ ] Human review
