# Base (cold-start) question generation

**Status:** approved for planning  
**Date:** 2026-08-11

## Problem

A new professor has no preference history. The generation package is still a null
seam (`NullQuestionGenerator` raises `FeatureNotAvailableError`). Domain
`Question` rows, SQLite tables, Instructor structured LLM access, approved
taxonomy upload, and book-section retrieval already exist. The missing piece is
a **base generator** that produces textbook-grounded, typed assessment questions
from those inputs.

## Goals

1. Define a stable **QuestionSpec** (request contract) independent of any generated
   candidate, shared later by base / personalized / GEPA generators.
2. Implement a **base** generator that uses Instructor + type-specific schemas
   (not one vague universal prompt).
3. Support seven question types and three difficulties.
4. Ground each question in **one book section** (section-first).
5. Persist structured content so later scoring can use discrete 0/100 or
   `passed_tests / total_tests * 100`.
6. Give the professor a UI to select taxonomy + difficulty + type + section(s),
   generate, and inspect the result.
7. Keep the implementation small: reuse Pydantic, Instructor, existing repos and
   `SourceRetrieval`.

## Non-goals

- Student delivery / runtime scoring UI.
- Automatic validation sandbox (ADR-004 stays deferred).
- Professor approve/reject/edit write UI (recording API already exists).
- Personalized or GEPA generators (descriptor slots only).
- PDF parsing or book conversion.
- Persisting token chunks (sections stay whole; any context-window split is
  ephemeral inside the generator call only).

## Locked product decisions

### Section-first generation (option A)

The professor selects:

- approved **topic** + **subtopic** (same for the whole run);
- **difficulty** and **question type**;
- **book** and one or more **sections** (or “all sections in this book”).

The system builds **one QuestionSpec and one question per selected section**.
Taxonomy is still required (ADR-002). Unapproved taxonomy IDs are rejected before
any LLM call.

### QuestionSpec

Conceptual shape:

```json
{
  "curriculum_version_id": 1,
  "topic_id": 10,
  "subtopic_ids": [42],
  "difficulty": "medium",
  "question_type": "debugging",
  "source_section_ids": [7],
  "seed": null
}
```

Rules:

- IDs are **database primary keys** of rows in the latest (or named) **approved**
  curriculum version and of imported `book_sections`.
- Cold-start path: `source_section_ids` has **exactly one** id per Spec.
- `subtopic_ids` has length ≥ 1; every subtopic must belong to `topic_id` under
  that curriculum version.
- Spec must not accept unapproved or foreign taxonomy IDs.
- Spec is stored on the question (`spec_json`) for later generator comparison.

### QuestionType vs QuestionKind

- **QuestionType** (new): assessment format — `multiple_choice`, `true_false`,
  `output_prediction`, `code_completion`, `debugging`, `parsons`, `coding`.
- **QuestionKind** (existing): scoring mode — `discrete` | `testable_program`.

Mapping:

| QuestionType | QuestionKind |
| ------------ | ------------ |
| multiple_choice, true_false, output_prediction, parsons | discrete |
| code_completion, debugging, coding | testable_program |

### Difficulty

`easy` | `medium` | `hard` — reasoning complexity within the linked section’s
taught skill. Hard must not introduce Python features the section did not teach.

### Source grounding

Allowed: new variable names, different literals, new examples, normal
prerequisite Python knowledge.

Required: the skill assessed must be taught by the linked section text.

Do not mechanically copy textbook examples unless appropriate.

### Parsons

Blocks carry `text` and `indent` (indent levels in the correct solution). Stored
content includes `blocks` and `correct_order` (block ids).

## Architecture

```
UI POST /questions/generate
  → GenerationService
      → resolve sections (explicit ids or all-in-book)
      → build QuestionSpec per section (validate taxonomy + section)
      → BaseQuestionGenerator.generate_one(spec)
            → SourceRetrieval section text + citation
            → common principles + type-specific prompt
            → StructuredLLMClient.complete_structured(type schema)
            → map to domain Question + content_json
      → QuestionRepository.add
  → redirect to detail (1) or bank (many)
```

### Modules (lean)

| Path | Responsibility |
| ---- | -------------- |
| `app/domain/enums.py` | Add `QuestionType` |
| `app/generation/spec.py` | `QuestionSpec` + `build_question_spec(...)` validation |
| `app/generation/schemas.py` | Seven Instructor response models + stored content helpers |
| `app/generation/principles.py` | Shared system prompt rules |
| `app/generation/prompts.py` | Per-type prompt builders; dispatch by type |
| `app/generation/base.py` | `BaseQuestionGenerator` |
| `app/generation/service.py` | Batch orchestration + persistence |
| `app/generation/__init__.py` | Public API; `get_question_generator()` → base |
| `app/domain/questions.py` | Extend `Question` fields |
| `app/persistence/models.py` | Extend `QuestionRow` |
| `app/web/routes/pages.py` | Generate + detail routes |
| `app/web/templates/questions.html` | Form + bank |
| `app/web/templates/question_detail.html` | Structured display |

### Persistence

Additive columns on `questions` (existing DBs must be deleted once; ADR-008):

- `question_type`
- `topic_id` (nullable FK)
- `spec_json`
- `content_json`

Retain `prompt`, `reference_solution`, `tests`, `original_*`, generator provenance.
Fill `prompt` / `reference_solution` / `tests` from structured content on save so
existing edit/review invariants keep working. `tests` remains a JSON text blob of
test cases for testable types.

### Generator identity

`GeneratorDescriptor(kind=BASE, name="base", version="1")` stamped on every
question (ADR-005).

### LLM

Use existing `get_structured_client()` / `require_llm()`. No new HTTP client.
Mock the `StructuredLLMClient` protocol in unit tests.

## Professor UI flow

1. `GET /questions` — readiness + generate form (if approved curriculum and ≥1 book)
   + question bank.
2. Form fields: topic, subtopic (`optgroup` by topic), difficulty, type, book,
   multi-select sections, checkbox “all sections in book”.
3. `POST /questions/generate`.
4. One section → redirect `GET /questions/{id}`; many → redirect `/questions` with
   created count / ids visible.
5. Detail shows prompt, answer/reference, explanation, tests, topic/subtopic,
   difficulty, type, source citation(s), generator label, status.

Zero JS build step; prefer `optgroup` for subtopics.

## Testing

- All seven schemas validate.
- Spec rejects unapproved taxonomy / missing sections.
- Mocked LLM path persists source refs and correct scoring kind for each type.
- Page tests for form + detail.
- Update boundary tests: base generator is live; validation/personalization/adaptive
  stay null.
- Optional `@pytest.mark.integration` real call when API key is configured.

## Completion report (for implementer)

Return: QuestionSpec design, generator architecture, type-specific modules, files
changed, tests/results, real-generation result if performed, exact UI flow, known
limitations.
