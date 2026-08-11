# Professor feedback collection — design

**Date:** 2026-08-11  
**Status:** approved for planning  
**Approach:** Extend the existing `app/feedback` boundary (Approach 1)

## Goal

Build the human feedback collection layer that later drives personalization.

A professor can **approve**, **reject**, or **edit** a generated question. All feedback is
persistently stored without losing the original generation. Professor feedback remains the
authority for professor preference (ADR-006). Book and taxonomy inputs stay structured JSON
uploads (already implemented); this work does not touch ingestion.

## Non-goals

- Professor authentication / real `professor_id` assignment
- Editing typed `content_json` fields (options, Parsons blocks, etc.)
- Re-running deterministic validation or the LLM judge after an edit
- Building or applying a preference profile (`app/personalization` stays a boundary)
- Student adaptive engine changes

## Existing foundations (preserve)

| Piece | Location | Role |
| --- | --- | --- |
| Original retention | ADR-003, `Question.original_*`, `apply_professor_edit` | Never overwrite generated text |
| Append-only reviews | ADR-003/006, `ProfessorReviewRow`, `record_review` | Preference history |
| Review decisions | `ReviewDecision` | `approve` / `reject` / `edit` |
| Question statuses | `QuestionStatus` | Includes `APPROVED` / `REJECTED` (no `EDITED`) |
| Detail UI | `question_detail.html` | Already shows validation + judge |
| Feedback list | `/feedback` | Recent reviews table |
| Generation grounding | book JSON + taxonomy JSON | Unchanged |

## Decisions locked in brainstorming

1. **Editable fields:** `prompt`, `reference_solution`, `tests` only.
2. **Reasons:** required (≥1) for Reject; optional for Edit; not used for Approve.
3. **Question status:** Approve → `APPROVED`; Reject → `REJECTED`; Edit → `APPROVED`.
   - `question.status` = whether the current question is usable.
   - Review `decision` = how it became usable (`APPROVE` vs `EDIT`).
   - Do **not** add `QuestionStatus.EDITED`.
4. **Edit snapshot:** store complete post-edit values of all three editable fields on the review
   row; derive `changed_fields` in the service.
5. **Diff-from-current check:** lives in the **service**, not in a cross-row Pydantic validator.

## Schema

### `RejectionReason` (`StrEnum`)

| Value | Label |
| --- | --- |
| `technically_incorrect` | Technically incorrect |
| `incorrect_answer` | Incorrect answer |
| `incorrect_tests` | Incorrect tests |
| `not_grounded_in_source` | Not grounded in source |
| `wrong_topic_subtopic` | Wrong topic/subtopic |
| `too_easy` | Too easy |
| `too_difficult` | Too difficult |
| `ambiguous` | Ambiguous |
| `poor_wording` | Poor wording |
| `poor_distractors` | Poor distractors |
| `poor_tests` | Poor tests |
| `not_pedagogically_useful` | Not pedagogically useful |
| `too_similar_repetitive` | Too similar/repetitive |
| `other` | Other |

`other` does not require a free-text comment; comment remains optional for every decision.

### `ProfessorReview` / `ProfessorReviewRow` fields

| Field | Rule |
| --- | --- |
| `id` | Review ID |
| `question_id` | Original question row |
| `decision` | `approve` / `reject` / `edit` |
| `reasons_json` | Logical `list[RejectionReason]`; persisted as JSON text. Empty for Approve. |
| `comment` | Optional free text, stored verbatim |
| `edited_prompt` | Full accepted prompt for Edit; `NULL` otherwise |
| `edited_reference_solution` | Full accepted solution for Edit; `NULL` otherwise |
| `edited_tests` | Full accepted tests for Edit; `NULL` otherwise |
| `changed_fields_json` | Service-derived subset of `prompt`, `reference_solution`, `tests`; Edit only |
| `professor_id` | Nullable until authentication exists |
| `reviewed_generator_name` / `reviewed_generator_version` | Copied from question at review time |
| `created_at` | Timestamp |

**Referenced via `question_id` (not duplicated as new review columns):**

- QuestionSpec (`spec_json`)
- Deterministic validation (`validation_report_json`)
- LLM judge evaluation (`pedagogical_eval_json`)
- Source citations (`content_json.sources`)
- Topic / subtopic / difficulty on the question row

### Question row contract (unchanged semantics)

- On Edit: update current `prompt` / `reference_solution` / `tests` via `apply_professor_edit`.
- `original_*` fields are written at generation and **never** overwritten.
- Status mirrors usability as above.

## Service / write path

Single entry point in `app/feedback` (extend or replace the thin `record_review` helper):

```text
submit_review(
  session,
  question_id,
  decision,
  *,
  reasons: list[RejectionReason] = [],
  comment: str | None = None,
  prompt: str | None = None,                 # Edit: full post-edit values
  reference_solution: str | None = None,
  tests: str | None = None,
  professor_id: int | None = None,
) -> ProfessorReviewRow
```

### Flow

1. Load question; raise `NotFoundError` if missing.
2. Enforce decision rules in the **service**:
   - **Reject:** ≥1 reason; ignore/clear edit payloads.
   - **Approve:** reasons empty; ignore/clear edit payloads.
   - **Edit:** require submitted full post-edit values for all three editable fields
     (use empty string when a field is unused for that question type); compare to the
     question’s **current** fields with `None` normalized to `""`; derive
     `changed_fields`; error if `changed_fields` is empty. On the review row, store
     all three `edited_*` strings (never leave them null on an Edit decision).
3. If Edit: apply `apply_professor_edit` to the domain object / row; leave `original_*` untouched.
4. Set `question.status` to `APPROVED` or `REJECTED` (Edit → `APPROVED`).
5. Append `ProfessorReviewRow` with decision, reasons JSON, comment, generator copies,
   `professor_id`, and (Edit only) full `edited_*` snapshots plus derived `changed_fields_json`.
6. Persist through existing repository + session commit pattern used by routes.

### Libraries / stack reuse

- Pydantic for reason enum and review DTO shape
- SQLAlchemy ORM + repositories for persistence
- Existing `apply_professor_edit` for original preservation
- FastAPI `Form` + Jinja2 for the review UI (ADR-007)

## UI workflow

### Question detail (`GET /questions/{id}`)

Keep existing panels (question text, assessment details, deterministic checks, LLM evaluation,
answer, tests, sources). Add:

1. **QuestionSpec** panel (decode `spec_json` when present).
2. **Review** panel at the bottom:
   - Decision radio: Approve | Reject | Edit
   - Multi-select reason checkboxes (all structured reasons)
   - Optional comment textarea
   - Edit textareas for `prompt`, `reference_solution`, `tests` (prefilled with current values;
     used only for Edit; server ignores them for Approve/Reject)
   - Submit → `POST /questions/{id}/review` → redirect to detail or `/feedback`

Server is the source of truth for reason/edit rules. Light HTML constraints are optional;
no SPA / no JS build step.

### Feedback dashboard (`GET /feedback`)

- Counts: reviewed, approved, rejected, edited (from review `decision`, not question status)
- Rejection-reason distribution across reviews that carry reasons
- Existing recent-reviews table, plus a Reasons column

`professor_id` remains null in the UI for this milestone.

## Tests

### Service / persistence

- Approve → status `APPROVED`; empty reasons; no edit snapshots
- Reject with multiple reasons → stored; status `REJECTED`
- Reject with zero reasons → error
- Reject/`other` with optional comment
- Edit with full post-edit values → current fields updated; `original_*` unchanged;
  review stores all three `edited_*` + derived `changed_fields`
- Edit with no actual changes → error
- Append-only: second review does not mutate the first
- Feedback retrieval / aggregates

### Web

- Detail page shows review form plus existing validation/judge content
- POST approve / reject / edit happy paths
- Feedback page shows counts and reason distribution

### Manual verification

- Review several generated questions in the UI
- Inspect `professor_reviews` and `questions.original_*` in SQLite

## Edit preservation mechanism (summary)

```text
Generation  →  original_* frozen on question
Edit        →  question current fields updated
            →  review row stores full edited_* + changed_fields
            →  original_* never touched
Later edits →  new append-only review rows; earlier snapshots remain
```

Before → after for personalization is therefore available from a single Edit review row
(`edited_*` vs question `original_*`, or vs prior review snapshots).

## Limitations

- No authentication → `professor_id` always null this milestone
- Edit surface limited to three fields
- No post-edit re-validation or re-judge
- Personalization deferred
- Progressive HTML enhancement only for reason UI; server enforces rules

## Files expected to change (planning hint)

| Area | Likely files |
| --- | --- |
| Domain | `app/domain/enums.py`, `app/domain/feedback.py` |
| Feedback service | `app/feedback/__init__.py` (or a small `service.py`) |
| Persistence | `app/persistence/models.py`, `app/persistence/repositories.py` |
| Web | `app/web/routes/pages.py`, `question_detail.html`, `feedback.html` |
| Tests | `tests/test_feedback*.py`, extend `test_persistence` / web tests as needed |
| Docs | this spec; optional ADR note only if a settled rule changes (none expected) |
