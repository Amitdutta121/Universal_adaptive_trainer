# Implementation Plan: Chunks, extensible styles, adaptive tutorials, video, professor agent

## Overview
Replace the validated chapter/section book tree with flat, versioned, library-parsed chunks. Merge the
question-generation entry points into one. Move question styles to community-contributed YAML. Add an
adaptive tutorial generator: trusted renderers plus a YAML recipe library, with the amount of guidance driven by
BKT mastery and with video clips as sources. Put a professor chat agent on top of the existing dashboard, and
finish with student-loop features adapted from DeepTutor. Source: the spec agreed in the planning conversation
(2026-10-14).

## Architecture Decisions
- **The chunk is the only source unit.** Content-hash id, book version, page range, heading path, text. Books are
  never re-chunked in place: a re-import makes a new version, so stored ids stay valid for frozen sets.
- **No groundedness judge in anything new.** Tutorial blocks, recipes and clips just store `chunk_ids`. The
  existing judges question generation already uses (e.g. `rounds._hard_lesson_supported`) stay untouched.
- **Parse with a library** (Docling or local `unstructured`, chosen by a spike on the Agah book). Retrieval is
  hybrid (BM25 + current embeddings, reciprocal rank fusion). LlamaIndex is adopted only if it beats that on the
  eval harness.
- **One `POST /generation-runs`** (target list + `dry_run`) replaces 7 generation endpoints, provided they share
  one pipeline (checked first).
- **Styles and recipes are YAML validated by Pydantic models**, with a published JSON Schema and CI checks. Ids are
  never renamed.
- **Renderers are few and trusted.** html runs in `iframe sandbox="allow-scripts"`, without same-origin, under a
  CSP that blocks the network. Executable content gets its truth from tools (`python_trace`), not from the LLM.
  html blocks pass a headless Playwright check.
- **The composer picks the format by content type and the amount of guidance by BKT mastery**
  (worked → faded → cue). Blocks are pre-generated, approved by the professor and frozen with the set. Selection is
  seeded and deterministic; live generation is only a fallback.
- **The agent is a side panel.** Pydantic AI with ~12 task tools over services. Approvals need a human click on an
  approval card; spending needs a confirmed cost estimate. Frontend: CopilotKit (AG-UI).
- **Model settings are chosen in the UI, per role:** generation, judges, agent, tutorials, ask-why, embeddings,
  transcription. Values saved in the database override `.env`, which stays the default. API keys are stored
  encrypted with a server secret and the API only ever returns them masked. Settings apply to the whole
  instance and only an admin can change them.
- **Planning convention:** this file plus `tasks/todo.md` replace the docs/ milestone file for this work.
  One phase per session, commit between phases.

## Task List
Full task definitions, acceptance criteria and verification are in `tasks/todo.md`.

### Phase 0: Baseline (spec M1)
- [x] T1: Retrieval gold set from the Agah book
- [x] T2: Retrieval eval harness + current baseline
- [x] T3: Parse spike, Docling vs unstructured

### Checkpoint A: Human picks the parser from the T3 report

### Phase 1: Chunks replace the book tree (M2)
- [x] T4: `chunks` table (schema only: no data copy or id map, by decision 2026-10-14)
- [x] T5: Library parser → chunks on import, versioned
- [x] T6: Chunk retrieval + `/chunks` endpoint (eval run pending: spends API)
- [x] T7: Repoint generation + validation to chunk ids
- [x] T8: Repoint evidence, evaluation, coverage, styles
- [x] T9: Frontend chunk viewer + scroll-page single generation
- [x] T10: Retire the chapter/section validation and the JSON book upload

### Checkpoint B: Full suite green, frozen-set replay unchanged, Agah import + scroll generation work in the UI

### Phase 2: Hybrid retrieval (M3)
- [x] T11: BM25 + RRF, measured against the baseline (LlamaIndex fusion is the default)

### Checkpoint C: Eval report shows hybrid ≥ baseline on every metric

### Phase 2b: Model settings
- [x] T41: Settings store, with the database overriding environment variables, per role
- [x] T42: Settings API + test connection + model list
- [x] T43: Changing the embedding model re-embeds and switches atomically
- [x] T44: Settings screen

### Checkpoint C2: Switch the generation model and the embedding model from the UI; retrieval keeps working throughout

### Phase 3: One generation endpoint (M4)
- [x] T12: Confirm a shared pipeline, write ADR-066 (stop if not shared)
- [x] T13: `POST /generation-runs` backend
- [x] T14: Switch frontend callers
- [x] T15: Delete old endpoints + prod/sync

### Checkpoint D: All generation flows work through the new endpoint in the UI

### Phase 4: YAML question styles (M5)
- [x] T16: YAML loader + convert the Python library + JSON Schema
- [x] T17: CI checks + id lock + CONTRIBUTING-styles.md
- [x] T18: Course-local styles + export to YAML

### Checkpoint E: Contributor flow: adding one YAML style passes CI and appears in setup

### Phase 5: Tutorial renderers and recipes (M6)
- [x] T19: Recipe schema + loader + seed recipes + tutorial_blocks table
- [x] T20: `python_trace` tool
- [x] T21: Block generator (recipe + chunks + tool → payload)
- [x] T22: Frontend renderers + sandboxed html
- [x] T23: Playwright check for html blocks

### Checkpoint F: The 3 seed recipes generate and render for one Agah subtopic

### Phase 6: Composer and student experience (M7)
- [x] T24: Pre-generation job + professor approval by recipe
- [x] T25: Freeze approved blocks with the question set
- [x] T26: Composer (BKT band → guidance level, seeded)
- [x] T27: Student UI: worked block after a wrong answer, pre-teaching, fading
- [x] T28: Per-recipe stats steer the composer

### Checkpoint G: A playbook student run shows blocks fading as mastery rises

### Phase 7: Video (M8)
- [x] T29: ~~Lecture upload → Whisper~~ (descoped 2026-10-15, YouTube only) → timestamped chunks
- [x] T30: YouTube transcript + paste fallback + availability check
- [x] T31: `video_clip` renderer + clip recipe

### Checkpoint H: A YouTube clip plays in a tutorial (uploaded lectures descoped)

### Phase 8: Professor agent (M9)
- [ ] T32: Pydantic AI agent + AG-UI endpoint + first 4 tools
- [ ] T33: Approval cards + confirming cost before spending
- [ ] T34: Remaining tools
- [ ] T35: CopilotKit side panel

### Checkpoint I: Set up the Agah course end to end via chat, with every approval a human click

### Phase 9: Student loop (M10)
- [ ] T36: Spaced review queue
- [ ] T37: Wrong answers resurface as sibling questions
- [ ] T38: Misconception-tagged distractors + error type
- [ ] T39: Hint-aware BKT credit
- [ ] T40: "Ask why" with citation chips

### Checkpoint: Complete
- [ ] All acceptance criteria met, validation green, the user has reviewed

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Migrating section → chunk breaks frozen sets or existing questions | High | T4 keeps a `section_id → chunk_id` map; legacy `source_section_ids` resolve through it; run the migration on a DB copy; Checkpoint B replays a frozen run |
| Name collision: ADR-044's "per-chunk spec sheet" (`ChunkQuestionRequest`, `chunk-preview.tsx`) already uses "chunk" | Med | Settle naming in T4 (e.g. rename the spec-sheet term to "spec row") before the new table lands |
| Chunk ids changing on re-import | High | Content-hash ids + immutable versions (T4/T5) |
| Docling model download is large and slow | Med | The spike measures it; optional dependency group; cache models on first run |
| html blocks are an XSS/exfiltration surface | High | Sandbox without same-origin + CSP blocking network (T22), Playwright check (T23), never same-origin |
| youtube-transcript-api blocked from server IPs, or no captions | Med | Paste-transcript fallback (T30); lecture upload as the main path |
| Pydantic AI ↔ CopilotKit AG-UI compatibility | Med | Spike at the start of T32 before building tools |
| Switching embedding models leaves retrieval half-migrated | High | T43 re-embeds into a new version and switches only when it's complete; the old vectors stay live until then |
| API keys leak through the settings API or logs | High | Encrypted at rest, masked in responses, excluded from logs (T41/T42 tests) |
| Scope: 44 tasks | High | One phase per session; checkpoints are hard stops for review |

## Phase 1 decisions (2026-10-14)
- **No data migration.** Existing books keep their sections and get chunks only when their file
  is re-imported (`POST /books/{id}/versions`). Questions generated from sections no longer pass
  the `source_chunk_ids` check. Accepted: "if it works as a new user I am fine".
- **ADR-044 naming clash settled by meaning, not renaming:** the spec sheet's "chunk" was a
  section; it now is a chunk (`ChunkQuestionRequest.chunk_id`).
- **Docling is the optional `parse` extra;** without it a PDF is chunked by page text. The suite
  runs `BOOK_PARSER=pages`. This worktree has its own `.venv` (Docling's deps conflict with the
  shared one).
- `GET /chunks/search` is separate from `GET /chunks` so only search needs a verified email
  (it spends embedder credit). Missing chunk vectors are embedded lazily on search.

## Open Questions
- Parser: **Docling** (decided at Checkpoint A, 2026-10-14; `docs/PARSE_SPIKE.md`).
- How long to keep the old `book_sections`/`book_chapters` tables after T10 before dropping them?
- Which model does the agent use by default? It can be changed later in Settings (T41–T44).
- Admin for settings: **the existing fastapi-users `is_superuser` flag** (decided 2026-10-14; `python -m app.auth.create_user --superuser`).
- Whisper: moot for now — custom video upload descoped 2026-10-15 (YouTube only).
- T39 needs hints to exist. Do `cue` tutorial blocks count as hints, or is a separate hint feature needed first?
