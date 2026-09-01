# Coverage "Generate" button — implementation milestones

Goal: a professor clicks **Generate** under a topic on `/coverage`; the system
retrieves the textbook section(s) that teach that topic's gap subtopics, generates
grounded questions through the existing `GenerationService`, flags likely
duplicates, and drops everything into the review queue. Replaces the current
`501` on `POST /api/coverage/generation-runs`.

## Shared design decisions (apply to every milestone)

- **Retrieval unit = `book_sections` row** (the production ingestion splitter's
  output). Never re-chunk. Confirmed best by `spikes/rag_taxonomy_bench.py`.
- **Query string = `"{topic.name} - {subtopic.name}: {subtopic.description}"`.**
  Name-only scored hit@1 0.65; this scored 0.85 on the taxonomy benchmark.
- **Dense vector search only** (`text-embedding-3-small` via the OpenRouter key
  already in `.env` — endpoint verified working). No reranker, no BM25 hybrid:
  they did not move hit@k on real taxonomy queries. Revisit only if the
  multi-book test regresses.
- **In-memory cosine.** ~1,600 sections total; numpy dot-product is sub-millisecond.
  No vector DB, no `sqlite-vss`.
- **The generator picks its own topic/subtopics from the section (ADR-031).** A
  run cannot be *aimed*; it retrieves for a subtopic, generates, and reports back
  which topic the generator claimed. Mismatches are surfaced, never hidden.
- **Dedup is a soft flag, never a gate.** Research + `spikes/topic_agent_spike.py`
  both say calibrate-before-blocking; the review queue is the backstop.
- **No migration tool (ADR-008).** New *tables* are free (`create_all` picks them
  up). Adding a *column* to an existing table forces a `data/adaptive_trainer.db`
  recreate and `verify_schema` failure — so every new field below lands in a new
  table, never on `questions`.
- **Synchronous request** for now (one professor, review-gated). If a run exceeds
  ~30 s in practice, an async job is a follow-up, not a redesign.

---

## m1 — Section embedding store + retrieval endpoint  ✅ DONE

**Outcome.** All acceptance criteria met. 1,624 sections embedded against the real
DB in ~52 s (`$≈0.01`); re-run reports `embedded 0 / skipped 1624`. Real-DB
retrieval smoke: subtopic 97 "Aliasing" → *Think Python 10.11 Aliasing* (0.63),
subtopic 32 "range() and counted loops" → *Counter Loops: while and range* /
*2.3 The range function*. Full backend suite green (1042). Two deviations from the
plan below.

**Deviations.**
- **Neither-param error is 422, not 400.** No route in the repo raises a bare
  400; they all raise `AdaptiveTrainerError` subclasses. `DomainRuleError` (422)
  is used, with a message naming the fix. Tests assert 422.
- **`MAX_EMBED_CHARS` is 18k, not 28k**, and the embedder now splits requests by
  a char budget + retries transient failures, and `backfill` commits per 64-row
  group. Found during the real backfill: a 23.5k-char section still exceeded the
  8192-token input cap (dense prose/code runs well under 4 chars/token).
- **Extra chore:** removed `pypdf` + `llama-index-readers-file` from the venv —
  spike-only installs that tripped `test_boundaries.py` (ADR-016/048: PyMuPDF is
  the only permitted PDF lib). Not committed (venv only).

**Deliverable.** A new `section_embeddings` table, a backfill command that embeds
every `book_sections` row once, and `GET /api/retrieval/sections?query=<text>` (or
`?subtopic_id=<id>`) returning the ranked sections with score, book, chapter,
section number/title and a snippet. The professor (or Amit) can curl the endpoint
and get the right section back for a real subtopic query.

**Acceptance criteria.**
- `SectionEmbeddingRow(section_id FK unique, model, dim, vector BLOB, content_hash, created_at)` in `app/persistence/models.py`; `init_db()` creates it with no `.db` reset.
- `python -m scripts.embed_sections` (or `scripts/embed_sections.py`) embeds all sections of all `imported` books, is idempotent (skips rows whose `content_hash` is unchanged), and prints `embedded N / skipped M / total T`.
- `app/retrieval/` module: `SectionEmbeddingStore` (embed + persist + load-all-into-memory) and `SectionRetriever.search(query: str, *, book_ids=None, top_k=5) -> list[RetrievedSection]`.
- `SectionRetriever.for_subtopic(subtopic_id, top_k)` builds the query string per the shared rule and restricts to the curriculum version's `source_book_ids`.
- `GET /api/retrieval/sections` returns `RetrievedSectionOut[]` (section_id, book_title, chapter_title, section_number, section_title, score, snippet); 400 if neither `query` nor `subtopic_id` given.
- Embedding client failure returns a 502 with the provider message, not a 500 stack.
- Unit tests: cosine ranking on a tiny fixture; `for_subtopic` query-string shape; endpoint happy path + the 400.

**Validation.**
```
.\.venv\Scripts\python.exe -m scripts.embed_sections
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval.py -q
# backend on :8099
curl "http://127.0.0.1:8099/api/retrieval/sections?subtopic_id=32"      # range() and counted loops
curl "http://127.0.0.1:8099/api/retrieval/sections?query=while+loop+break"
```
Expect the top hit for subtopic 32 to be a range()/counted-loop section of a source book.

**Touches.** `app/persistence/models.py`, `app/retrieval/__init__.py` (+ `store.py`, `retriever.py`, `schema.py`), `app/web/routes/api/retrieval.py` (new router) + register in the API app, `app/web/routes/api/schemas.py`, `scripts/embed_sections.py`, `tests/test_retrieval.py`. Reuse the embedding-client construction from `spikes/rag_taxonomy_bench.py` / `scripts/semantic_book_search_check.py`.

**Not in this milestone.** No generation. No BM25/hybrid/rerank. No auto-embed on import (m5). No UI.

---

## m2 — Generate-for-gaps end to end via API (no UI)

**Deliverable.** `POST /api/coverage/generation-runs` stops returning 501. Given
the selected gap targets (`FillGapsRequest`, unchanged: `[{subtopic_id, difficulty}]`),
for each target it retrieves the top-1 section (m1), calls
`GenerationService.generate_batch`, and returns a run summary: `run_id`, per
question `{question_id, requested_subtopic_id, claimed_topic_id, claimed_subtopic_ids, section_id, status, aim_matched}`. The new questions appear in the review queue with no extra step.

**Acceptance criteria.**
- Endpoint builds one `ChunkQuestionRequest(section_id, counts={difficulty: 1}, question_types=[MULTIPLE_CHOICE])` per resolved target, deduping repeated `section_id`s into one request with summed counts.
- Uses the approved curriculum version; `require_approved_version` failure returns 409, not 500.
- A target whose subtopic retrieves nothing above a floor score is reported as `{subtopic_id, skipped: "no confident section"}` — the run continues for the rest.
- Response `aim_matched` = (`claimed_topic_id` == the requested subtopic's topic). Mismatches are returned, not filtered.
- Questions persist via the existing `_generate_specs` path: one `run_id`, per-question commit, validation + judge already run, `status` set from the validation report → they land in `list_unreviewed` automatically (only `VALIDATION_FAILED` is excluded).
- Partial provider failure keeps what was generated and returns 207-style body (`generated: [...], failed: [...]`) with 200.
- Tests: `tests/test_coverage.py` gains cases for the run endpoint (happy path, unknown subtopic, no-section skip, aim mismatch surfaced) using a fake `StructuredLLMClient` like the other generation tests.

**Validation.**
```
.\.venv\Scripts\python.exe -m pytest tests/test_coverage.py tests/test_generation_batch.py -q
# backend on :8099, professor cookie per the test playbook
curl -s -b /tmp/cj -X POST http://127.0.0.1:8099/api/coverage/generation-runs \
  -H 'Content-Type: application/json' \
  -d '{"targets":[{"subtopic_id":32,"difficulty":"medium"},{"subtopic_id":34,"difficulty":"easy"}]}'
curl -s -b /tmp/cj "http://127.0.0.1:8099/api/questions?status=validation_passed" | jq '.[0]'
```
Expect 2 new questions, each citing a retrieved section, visible in the unreviewed list.

**Touches.** `app/web/routes/api/coverage.py` (replace `start_generation_run`), `app/web/routes/api/schemas.py` (run-summary response model), maybe a thin `app/coverage/generation.py` orchestrator that wires `SectionRetriever` → `GenerationService`, `tests/test_coverage.py`. Reuse `GenerationService.generate_batch`, `ChunkQuestionRequest`, `compile_chunk_requests`.

**Not in this milestone.** No dedup flags (m3). No UI (m4). One section and one MCQ per gap cell — multiple sections / counts / question types are later. No async job.

---

## m3 — Duplicate flagging surfaced in review

**Deliverable.** After a generation run, each new question is embedded
(`prompt` + option text) and compared by cosine to existing `APPROVED` +
`VALIDATION_PASSED` questions **with the same `topic_id`**. Pairs above threshold
get a row in a new `question_similarity_flags` table. The review queue response
carries `possible_duplicate_of: [{question_id, prompt_excerpt, score}]`, and the
review UI can pre-fill the `TOO_SIMILAR_REPETITIVE` rejection reason.

**Acceptance criteria.**
- `QuestionSimilarityRow(question_id FK, similar_question_id FK, score float, model, created_at)`; new table, no `.db` reset.
- Flagging runs inside the m2 orchestrator after `generate_batch` returns, in the same request; a flagging failure logs and returns the run without flags (never fails the run).
- Threshold is a named constant (start 0.85, per the near-duplicate literature) with a comment that it is uncalibrated.
- `GET /api/questions` unreviewed items and the review-detail endpoint include `possible_duplicate_of` (empty list when none).
- Re-running m2 for the same subtopic twice: the second batch's questions carry flags pointing at the first batch's (now approved-or-pending) questions.
- Tests: `tests/test_dedup.py` — cosine flagging on a fixture with one near-copy and one unrelated question; flags absent across different topics; run still succeeds when the embedder raises.

**Validation.**
```
.\.venv\Scripts\python.exe -m pytest tests/test_dedup.py -q
# generate twice for the same target, then:
curl -s -b /tmp/cj "http://127.0.0.1:8099/api/questions?status=validation_passed" \
  | jq '.[] | {id, possible_duplicate_of}'
```
Expect the later questions to list an earlier `question_id` with a score ≥ 0.85.

**Touches.** `app/persistence/models.py`, `app/coverage/generation.py` (or wherever m2's orchestrator lives), `app/web/routes/api/questions.py` + its response schemas, `app/domain/feedback.py` only if a pre-fill hook is needed, `tests/test_dedup.py`.

**Not in this milestone.** No auto-reject or auto-hide. No threshold calibration. No cross-topic or against-rejected comparison. No UI change beyond the field being present in the response.

---

## m4 — The button

**Deliverable.** The **Generate** button in `coverage-grid.tsx` calls
`POST /api/coverage/generation-runs` with the topic's gap cells, shows a pending
state, and on completion shows an inline result — "6 generated · 2 possible
duplicates · 1 landed on a different topic" — with a link to the review queue
filtered to that `run_id`.

**Acceptance criteria.**
- Regenerated `frontend/src/lib/api/schema.d.ts` from the updated OpenAPI; typed mutation in `frontend/src/lib/api/queries.ts`.
- Button disabled + spinner while the request is in flight; disabled entirely for a topic with zero gaps.
- Result summary rendered inline on the topic card (not a modal), counts sourced from the run-summary response, with a `Review these →` link to `/questions` filtered by run.
- Error (502 from the embedder, 409 no approved curriculum) shows a readable message on the card, not a silent no-op.
- `coverage-grid.test.tsx` covers: click fires the mutation with the right targets, pending state, success summary, error message.

**Validation.**
```
cd frontend
pnpm biome lint src/app/coverage
pnpm tsc --noEmit          # NOT `pnpm run lint` — broken repo-wide, see memory
pnpm vitest run src/app/coverage
```
Then click-path: `/coverage` → **Generate** under a topic with gaps → spinner → summary → **Review these** opens the filtered review queue showing the new questions.

**Touches.** `frontend/src/app/coverage/components/coverage-grid.tsx`, `frontend/src/lib/api/queries.ts`, `frontend/src/lib/api/types.ts`, `frontend/src/lib/api/schema.d.ts` (regenerated), `frontend/src/app/coverage/components/coverage-grid.test.tsx`. Possibly `frontend/src/app/questions/*` for the `run_id` filter if it does not exist.

**Not in this milestone.** No progress streaming. No async/background run + polling. No per-subtopic or per-difficulty controls on the card — one click generates for all of the topic's gaps.

---

## m5 — Embedding freshness

**Deliverable.** Importing a book auto-embeds its sections (no manual
`scripts.embed_sections`), and `GET /api/retrieval/status` reports
`{sections_total, embedded, stale, missing, model}` so drift is visible.

**Acceptance criteria.**
- The ingestion completion path (`app/ingestion/service.py`) calls
  `SectionEmbeddingStore.backfill(book_id=...)` after a successful import,
  failures logged and non-fatal (the book still imports).
- Editing/re-importing a book re-embeds only sections whose `content_hash` changed.
- `GET /api/retrieval/status` numbers match a fresh `scripts.embed_sections --dry-run`.
- Test: importing a fixture book leaves its sections embedded; changing one section's text marks exactly that one stale then re-embeds it.

**Validation.**
```
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval.py tests/test_ingestion_service.py -q
curl -s http://127.0.0.1:8099/api/retrieval/status | jq
```

**Touches.** `app/ingestion/service.py`, `app/retrieval/store.py`, `app/web/routes/api/retrieval.py`, `tests/test_retrieval.py`, `tests/test_ingestion_service.py`.

**Not in this milestone.** No re-embed-on-model-change automation (manual `scripts.embed_sections --rebuild`). No background queue for large imports.

---

## Sequence

`m1 → m2 → m3 → m4 → m5` — strict; m2 needs m1's retriever, m3/m4 need m2's endpoint, m5 is polish on m1.

**Active: m2** (m1 committed). Run `start m2` to implement, `verify m2` to check it against the acceptance criteria. One milestone per session; commit before the next.

### Deferred (not milestones yet)

- Multi-book disambiguation validation (index books 2+3+5, re-run `spikes/rag_taxonomy_bench.py`) — do this **before m2** if you want confidence the top-1 section comes from the right book.
- Concept-index layer (decompose subtopics into testable concepts; track coverage + dedup at concept grain) — the bigger feature this button is a step toward.
- Async generation run + polling, if synchronous latency bites.
- Cross-encoder reranker, only if multi-book retrieval regresses.
- Dedup threshold calibration on the existing approved/rejected question split.
