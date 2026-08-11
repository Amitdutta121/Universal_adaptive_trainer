# LLM pedagogical evaluation (advisory judge)

**Status:** approved for implementation  
**Date:** 2026-08-11

## Problem

Deterministic validation (ADR-023) catches invalid Python, broken tests, incorrect
executable output, and malformed structure. It does not fully capture pedagogical
qualities: source grounding in instructional text, whether the assigned subtopic is
actually assessed, difficulty alignment, clarity, ambiguity, usefulness for
introductory Python, answer/explanation consistency, distractor quality, or test
quality as pedagogy.

ADR-004 already states that LLM judgment is advisory and cannot override
deterministic failure. This milestone adds a separate structured LLM evaluation
layer that every generated question receives, while leaving question status under
deterministic authority only.

Book and taxonomy input remain structured JSON (already implemented). No PDF.

## Goals

1. Every generated question has deterministic validation **and** a separate stored
   pedagogical evaluation object (`completed`, `skipped`, or `error`).
2. The judge returns structured per-dimension results (not an opaque single grade).
3. Deterministic hard failures skip the judge; the LLM never overrides those failures.
4. Question detail UI clearly distinguishes deterministic checks from LLM evaluation
   and exposes rationales.
5. Keep the design small: reuse `StructuredLLMClient` + Instructor + Pydantic;
   thin new `app/evaluation/` package; orchestration in `GenerationService`.

## Non-goals

- Making the judge final authority for `QuestionStatus`
- Professor preference learning / personalization
- Re-judge button or evaluation history table
- Changing deterministic validation rules
- Student-facing UI
- PDF or heuristic book extraction

## Locked decisions

### Flow and ownership

```
generate question
        │
        ▼
DeterministicQuestionValidator.validate()
        │
        ├── FAIL → status = VALIDATION_FAILED
        │           pedagogical_eval = skipped (reason: deterministic_failed)
        │           (judge is not called)
        │
        └── PASS → PedagogicalJudge.evaluate(...)  (up to 3 attempts)
                    ├── success → pedagogical_eval = completed
                    └── all attempts fail → pedagogical_eval = error
                    status remains VALIDATION_PASSED in both cases
        │
        ▼
persist validation_report_json + pedagogical_eval_json
display two distinct panels
```

- **`GenerationService` owns skip orchestration.** It calls
  `skipped_evaluation(...)` when `report.passed` is false. It calls
  `PedagogicalJudge.evaluate(...)` only when deterministic checks passed.
- **`PedagogicalJudge` never decides to skip.** It only performs the LLM
  evaluation (with retries) or returns an `error` evaluation after exhausted
  attempts.

### Precedence (hard rule)

If deterministic checks establish invalid Python, broken canonical tests,
incorrect executable output, or malformed structure, the LLM judge must not
override that failure.

- Question `status` continues to come only from
  `QuestionValidationReport.resulting_status()` (deterministic checks only).
- A completed or glowing pedagogical evaluation cannot change
  `VALIDATION_FAILED` to passed.
- An `error` pedagogical evaluation cannot change `VALIDATION_PASSED` to failed.

### Judge input

Give the judge:

1. The **complete generated question artifact**: prompt, typed content fields
   (`content_json` / decoded draft fields), reference solution, tests, question
   type, and requested difficulty.
2. **Only the relevant source/taxonomy context**: the source section(s) tied to
   the question (text + citation) and the approved topic/subtopic labels (and any
   short definition available for that subtopic). No other book chapters or
   curriculum tree.

Also state in the prompt that deterministic checks already passed (the judge is
not re-checking executability).

### Rubric (`RUBRIC_VERSION = "pedagogical-judge@1"`)

| Dimension id | Applicability |
| ------------ | ------------- |
| `source_grounding` | always |
| `subtopic_alignment` | always |
| `difficulty_alignment` | always |
| `clarity` | always |
| `ambiguity` | always (higher score = less harmful ambiguity) |
| `pedagogical_usefulness` | always |
| `intro_python_appropriateness` | always |
| `answer_explanation_consistency` | when answer/explanation present and not fully settled by deterministic checks; else `not_applicable` |
| `distractor_quality` | multiple-choice only; else `not_applicable` |
| `test_quality` | executable/testable types with tests; else `not_applicable` |

### Per-dimension fields

- `dimension` — enum id from the rubric
- `score` — integer `1–5`, or `null` when not applicable
- `applicable` — bool
- `confidence` — float `0.0–1.0`
- `rationale` — concise string
- `issues` — list of short strings (may be empty)

### Overall advisory summary

- `overall_advisory_score` — **unweighted arithmetic mean of applicable dimension
  scores**, provided only as a summary. Individual dimension results remain the
  **primary** evaluation output.
- `overall_advisory_status` — display band only; never drives `QuestionStatus`.
  - `skipped` / `error` when evaluation status is those values.
  - Else if the mean of applicable confidences is below 0.5 → `uncertain`
    (still store and show the numeric mean).
  - Else from the mean score: `strong` if mean ≥ 4, `adequate` if mean ≥ 3,
    else `weak`.

Avoid opaque “8.7/10 therefore good” presentation: UI lists dimensions first;
overall mean is secondary.

### Retries

When deterministic checks passed, `PedagogicalJudge` attempts the structured LLM
call up to **3 times** (initial call + 2 retries) on `LLMRequestError` or
`MalformedModelOutputError`. Each attempt uses the existing client with
Instructor `max_retries=0` (no repair loop inside a single attempt). After three
failures, return `status=error` with detail; leave question status as
`VALIDATION_PASSED`.

### Persistence

- New nullable `pedagogical_eval_json` column on `questions` (`QuestionRow` and
  domain `Question`), alongside existing `validation_report_json`.
- Store one `PedagogicalEvaluation` JSON blob including:
  - `question_id`
  - `status` (`completed` | `skipped` | `error`)
  - `skip_reason` / `error_detail` as applicable
  - `overall_advisory_score`, `overall_advisory_status`
  - `dimensions`
  - `judge_model` (from `StructuredLLMClient.description`)
  - `rubric_version`
  - `created_at`
- No evaluation history table in this milestone.
- Existing SQLite files missing the column fail `verify_schema` and must be
  recreated (ADR-008); no migration tool yet.

### Package layout

Thin new package `app/evaluation/`:

| Module | Responsibility |
| ------ | -------------- |
| `__init__.py` | Public types / factory |
| `rubric.py` | `RUBRIC_VERSION`, dimension ids, short judge instructions |
| `schema.py` | Pydantic LLM response model + stored `PedagogicalEvaluation` |
| `service.py` | `PedagogicalJudge.evaluate(...)`; constructors `skipped_evaluation` / helpers for error |

Allowed dependencies: `domain`, `persistence` (read-only context loaders as needed),
`llm`, `ingestion` retrieval for section text, `config` via existing patterns.
Does not import `adaptive` or `personalization`. Does not perform deterministic
validation.

`app/validation/` remains LLM-free (ADR-023).

### UI

On `question_detail.html`, replace the single “Automatic Checks” framing with two
clearly labeled panels:

1. **Deterministic checks** — existing ✓/✗ list and evidence.
2. **LLM pedagogical evaluation** — status; for `completed`, each dimension with
   score/5, confidence, rationale, and issues; overall mean shown as summary only;
   for `skipped` / `error`, show reason; show `judge_model`, `rubric_version`,
   timestamp.

### ADR

Record **ADR-024** in `docs/DECISIONS.md`: advisory pedagogical judge; GenerationService
owns skip; dimensions primary; unweighted mean summary; cannot override deterministic
failure; stored separately from the deterministic report.

## Error handling

| Case | Behavior |
| ---- | -------- |
| Deterministic fail | Skip judge; store `skipped`; status `VALIDATION_FAILED` |
| Judge success | Store `completed`; status `VALIDATION_PASSED` |
| Judge fails 3× | Store `error`; status still `VALIDATION_PASSED` |
| Malformed model output | Counts as an attempt; after 3 → `error` |

## Testing

Mock `StructuredLLMClient` for normal tests (same pattern as generation tests).

Required cases:

1. Deterministic fail → `pedagogical_eval.status == skipped`; judge not called.
2. Deterministic pass + valid judge output → `completed` persisted with dimensions.
3. Malformed structured outputs / provider errors exhaust 3 attempts → `error`;
   question remains `VALIDATION_PASSED`.
4. Judge success cannot override deterministic failure (orchestration never calls
   judge on fail; status still from deterministic report).
5. Schema rejects out-of-range scores and invalid structures.

Representative valid and invalid generation/validation examples should show both
panels populated appropriately.

## Verification / completion report

Implementation is complete when:

- Rubric version and dimension list match this spec.
- Structured schema matches this spec.
- Precedence logic matches the flow above.
- Files under `app/evaluation/`, persistence column, generation wiring, UI panels,
  ADR-024, and tests exist.
- `pytest`, `ruff check`, and `ruff format --check` pass.
- Completion report lists: judge rubric; structured schema; precedence logic; files
  changed; tests/results; UI test flow.

## Out of scope follow-ups

- Manual re-run of the judge from the UI
- Append-only evaluation history
- Feeding judge output into professor preference learning
- Changing generation prompts based on judge scores
