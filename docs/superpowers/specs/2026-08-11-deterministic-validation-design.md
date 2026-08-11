# Deterministic question validation

**Status:** approved for implementation  
**Date:** 2026-08-11

## Problem

Generated questions are persisted as `GENERATED` with no automatic checks.
`app/validation` is a null seam that raises `FeatureNotAvailableError`.
ADR-004 already requires deterministic checks to outrank any future LLM judge.
This milestone implements those checks for the local research prototype.

Book and taxonomy input remain structured JSON (already implemented). No PDF.

## Goals

1. Every generated question receives a stored deterministic validation report.
2. The question detail page shows an **Automatic Checks** panel (pass and fail).
3. Runtime/executable Python behavior outranks any later LLM judgment.
4. Keep the design small: Pydantic, stdlib `ast` / `subprocess` / `tempfile`, existing repos.

## Non-goals

- LLM judge or advisory non-deterministic checks
- Production sandbox (containers, cgroups, seccomp, network jail)
- Student scoring UI
- Professor approve/reject/edit write UI
- A separate “Validate” button (validation runs automatically after persist)

## Locked decisions

### No separate schema-valid check

Instructor already validated the draft at generation time. Do **not** show
“Schema valid”. Decode `content_json` as JSON; if it is missing, not an object,
or not valid JSON, emit failing check `content_unreadable` and skip type-specific
checks. Type-specific field rules still run on the decoded object (tampered or
hand-built fixtures).

### Shared grounding checks (always)

| Check name | Pass when |
| ---------- | --------- |
| `approved_taxonomy_ids` | `curriculum_version_id` is an **approved** version; `topic_id` and `subtopic_id` belong to that version |
| `source_section_ids` | Every id in `spec_json.source_section_ids` and `content_json.sources[].section_id` exists |
| `allowed_question_type` | `question_type` is a `QuestionType` member (not null) |
| `allowed_difficulty` | `difficulty` is a `Difficulty` member |

### Hybrid executable tests

Each test case is:

```json
{"stdin": "optional", "stdout": "optional", "assert": "optional"}
```

Rules:

- `stdin` defaults to `""`.
- At least one of `stdout` or `assert` is required. Empty-string `stdout` is a
  valid expected output (program prints nothing).
- Both may be present: feed stdin, append assert source, compare captured stdout.

Drafts for code completion, debugging, and coding use
`tests: list[ExecutableTestCase]` (min length 1).

### Severity

`QuestionCheck.severity` is a label. This milestone always stores `"error"`.
Any deterministic `passed=False` fails `QuestionValidationReport.passed` and
sets status `validation_failed`. Compile/runtime/ID failures never pass.

Optional `evidence` holds truncated stdout/stderr or mismatch detail.

### When validation runs

After each question row is flushed (so `id` exists), before the generation
batch commit. Status becomes `validation_passed` or `validation_failed`.
Report JSON is stored on the row.

### Runtime strategy

`LocalCodeRunner` writes a temp file and runs
`sys.executable -I` (isolated mode) with a timeout from
`Settings.validation_timeout_seconds` (default `2.0`), captured stdout/stderr,
minimal env (`PATH`, `PYTHONIOENCODING`, plus Windows `SYSTEMROOT`/`WINDIR`).
Not a multi-tenant sandbox. Documented in ADR-023.

## Architecture

```
GenerationService.generate_for_sections
  → persist QuestionRow (flush)
  → DeterministicQuestionValidator.validate(Question)
       → shared.py grounding checks
       → type_checks.py (may call LocalCodeRunner)
  → write validation_report_json + status
  → commit
  → GET /questions/{id} renders Automatic Checks
```

Packages:

| Module | Responsibility |
| ------ | -------------- |
| `app/validation/report.py` | `make_check(...)` |
| `app/validation/runner.py` | subprocess + hybrid harness |
| `app/validation/shared.py` | taxonomy / source / type / difficulty |
| `app/validation/type_checks.py` | per-`QuestionType` checks |
| `app/validation/service.py` | orchestrator |
| `app/validation/__init__.py` | `get_question_validator(session=...)` |

Allowed validation dependencies (document in package docstring):
`app.config`, `app.domain`, `app.errors`, `app.persistence`,
`app.generation.schemas` (draft/test-case shapes only). No LLM.

## Type-specific checks

Exact check **names** and passing **detail** strings (UI uses `detail`):

### Multiple choice

| name | pass detail |
| ---- | ----------- |
| `mc_options_valid` | Options are valid |
| `mc_no_duplicate_options` | No duplicate options |
| `mc_correct_option_exists` | Correct-answer reference exists |
| `mc_explanation_present` | Explanation exists |

Fail when fewer than 2 options, blank options, exact duplicate strings,
`correct_option_index` missing or out of range, or explanation missing/blank.

### True/false

| name | pass detail |
| ---- | ----------- |
| `tf_boolean_answer` | Valid boolean answer |
| `tf_explanation_present` | Explanation exists |

### Output prediction

| name | pass detail |
| ---- | ----------- |
| `output_code_parses` | Prediction code parses |
| `expected_output_verified` | Expected output verified |

Parse `code` with `ast.parse`. Run it (empty stdin). Compare captured stdout to
`expected_output` after newline normalisation (`\r\n` → `\n`) and stripping at
most one trailing newline from both sides.

### Code completion

| name | pass detail |
| ---- | ----------- |
| `completion_reference_parses` | Reference solution parses |
| `harness_valid` | Test harness is valid |
| `reference_passes_tests` | `{passed}/{total} tests pass` |

Execute **reference_solution**, not the incomplete stub.

### Debugging

| name | pass detail |
| ---- | ----------- |
| `debug_broken_exhibits_issue` | Broken code exhibits the issue |
| `debug_reference_parses` | Reference solution parses |
| `harness_valid` | Test harness is valid |
| `reference_passes_tests` | `{passed}/{total} tests pass` |

Broken code must fail at least one test, fail to parse, time out, or exit
non-zero. Reference must parse and pass every test. If broken already passes
every test, `debug_broken_exhibits_issue` fails.

### Parsons

| name | pass detail |
| ---- | ----------- |
| `parsons_order_consistent` | Canonical order is consistent |
| `parsons_indent_valid` | Indentation representation is valid |
| `parsons_reference_compiles` | Reconstructed reference compiles |

Order is consistent when `correct_order` is a permutation of all block ids
(no unknowns, no extras, no duplicates). Indent is an `int >= 0` per block.
Reconstruct with `4 * indent` leading spaces + `text`, then `compile(..., "exec")`.

### Coding

| name | pass detail |
| ---- | ----------- |
| `coding_reference_parses` | Reference solution parses |
| `harness_valid` | Test harness is valid |
| `reference_passes_tests` | `{passed}/{total} tests pass` |

## Persistence

- `Question.validation_report_json: str | None`
- `QuestionRow.validation_report_json` (`Text`, nullable)
- Value is `QuestionValidationReport.model_dump_json()`

Fresh test DBs pick this up via `create_all`. Existing developer SQLite files
may need delete/recreate (ADR-008).

## UI

Question detail, after assessment details, before source citations:

Heading: `Automatic Checks`

Each check: `✓ {detail}` or `✗ {detail}`. Failed checks with `evidence` show it
in a `<pre>`. If there is no report JSON: `Automatic checks have not been recorded.`

Panel class: `panel-success` when the report passed, `panel-error` otherwise.

Exact UI test phrase: page contains `Automatic Checks` and `Approved curriculum IDs`.

## Tests

Deliberately invalid fixtures for every type, plus a happy path for each
executable type. Shared-check failures for bad taxonomy, missing section, and
null type. Boundary test: `get_question_validator()` must not raise
`FeatureNotAvailableError`.

## Limitations (must appear in runner docstring and ADR-023)

Local same-user research prototype. Isolated mode (`-I`) and a timeout reduce
accident risk; they do not stop generated code from using the filesystem or
other process capabilities. Not safe for untrusted multi-tenant execution.
