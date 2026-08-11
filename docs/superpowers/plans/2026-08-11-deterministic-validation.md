# Deterministic Question Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every generated question gets a stored, visible deterministic validation report; runtime/structural truth outranks any future LLM judge.

**Architecture:** Replace `NullQuestionValidator` with a session-aware orchestrator that runs shared grounding checks, then type-specific checks (using one `LocalCodeRunner` for executable types). Hook it into `GenerationService` after persist. No distributed sandbox.

**Tech Stack:** Pydantic v2, stdlib `ast` / `subprocess` / `tempfile`, SQLAlchemy 2.0, Jinja2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-11-deterministic-validation-design.md`

## Global Constraints

- No LLM in `app/validation`. No “Schema valid” check or UI line.
- Shared checks only: `approved_taxonomy_ids`, `source_section_ids`, `allowed_question_type`, `allowed_difficulty`. Decode failure is `content_unreadable` (fail-only).
- Hybrid tests: `stdin` optional (default `""`); at least one of `stdout` or `assert` required; empty-string `stdout` is valid expected output.
- `QuestionCheck.severity` is always `"error"`. Any deterministic `passed=False` fails the report.
- Auto-validate after flush, before generation commit. Store `validation_report_json`. Status `validation_passed` / `validation_failed`.
- Runner: `sys.executable -I`, timeout `Settings.validation_timeout_seconds` default `2.0`. Not a production sandbox.
- Check **names** and passing **detail** strings are locked in the spec; copy them verbatim.
- Python 3.12, `from __future__ import annotations`, ruff line length 100.
- Tests live in `tests/`, never write the developer `data/` directory.
- Commands: `.\.venv\Scripts\python.exe -m pytest <file> -v` then full `pytest`, `ruff check .`, `ruff format --check .` before commit.
- Do not edit `.cursor/plans/` files.

## File structure

| Path | Responsibility |
| ---- | -------------- |
| `app/domain/questions.py` | `QuestionCheck.severity` + `evidence`; `Question.validation_report_json` |
| `app/generation/schemas.py` | `ExecutableTestCase`; typed `tests` on coding/completion/debugging drafts |
| `app/config.py` | `validation_timeout_seconds` |
| `app/persistence/models.py` | `QuestionRow.validation_report_json` |
| `app/validation/report.py` | `make_check` |
| `app/validation/runner.py` | `LocalCodeRunner` |
| `app/validation/shared.py` | Grounding checks |
| `app/validation/type_checks.py` | Per-type checks |
| `app/validation/service.py` | `DeterministicQuestionValidator` |
| `app/validation/__init__.py` | Public exports; drop null raise |
| `app/generation/service.py` | Validate after persist |
| `app/web/routes/pages.py` | Pass checks into detail template |
| `app/web/templates/question_detail.html` | Automatic Checks panel |
| `app/web/static/css/app.css` | Evidence pre under checklist |
| `docs/DECISIONS.md` | ADR-004 implication + ADR-023 |
| `tests/test_validation_*.py` | Unit/integration/UI tests |

## Interfaces (locked)

```python
def make_check(
    name: str,
    passed: bool,
    detail: str,
    evidence: str | None = None,
) -> QuestionCheck:
    """Always deterministic=True, severity='error'."""

class ExecutableTestCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    stdin: str = ""
    stdout: str | None = None
    assert_code: str | None = Field(default=None, alias="assert")

class LocalCodeRunner:
    def __init__(self, timeout_seconds: float | None = None) -> None: ...
    def run_script(self, source: str, *, stdin: str = "") -> ScriptResult: ...
    def run_tests(self, source: str, tests: list[ExecutableTestCase]) -> TestRunSummary: ...

@dataclass(frozen=True)
class ScriptResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool

@dataclass(frozen=True)
class TestRunSummary:
    passed_count: int
    total: int
    timed_out: bool
    evidence: str | None

def check_shared(question: Question, session: Session | None) -> list[QuestionCheck]: ...
def check_type(question: Question, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]: ...

class DeterministicQuestionValidator:
    def __init__(self, session: Session | None = None) -> None: ...
    def validate(self, question: Question) -> QuestionValidationReport: ...

def get_question_validator(session: Session | None = None) -> QuestionValidator: ...
```

Passing detail strings (verbatim):

- `approved_taxonomy_ids` → `Approved curriculum IDs`
- `source_section_ids` → `Source section IDs exist`
- `allowed_question_type` → `Allowed question type`
- `allowed_difficulty` → `Allowed difficulty`
- `mc_options_valid` → `Options are valid`
- `mc_no_duplicate_options` → `No duplicate options`
- `mc_correct_option_exists` → `Correct-answer reference exists`
- `mc_explanation_present` → `Explanation exists`
- `tf_boolean_answer` → `Valid boolean answer`
- `tf_explanation_present` → `Explanation exists`
- `output_code_parses` → `Prediction code parses`
- `expected_output_verified` → `Expected output verified`
- `completion_reference_parses` / `debug_reference_parses` / `coding_reference_parses` → `Reference solution parses`
- `harness_valid` → `Test harness is valid`
- `reference_passes_tests` → `{passed}/{total} tests pass`
- `debug_broken_exhibits_issue` → `Broken code exhibits the issue`
- `parsons_order_consistent` → `Canonical order is consistent`
- `parsons_indent_valid` → `Indentation representation is valid`
- `parsons_reference_compiles` → `Reconstructed reference compiles`

---

### Task 1: QuestionCheck, ExecutableTestCase, timeout setting

**Files:**
- Modify: `app/domain/questions.py`
- Modify: `app/generation/schemas.py`
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `tests/test_domain.py`
- Modify: `tests/test_generation_schemas.py`
- Modify: `tests/test_generation_pages.py`
- Modify: `tests/test_generation_base.py`
- Modify: `tests/test_config.py`
- Create: `app/validation/report.py`

**Interfaces:**
- Consumes: existing `QuestionCheck` / draft models
- Produces: `QuestionCheck.severity: str = "error"`, `QuestionCheck.evidence: str | None = None`, `Question.validation_report_json: str | None = None`
- Produces: `ExecutableTestCase` as specified above; `CodeCompletionDraft.tests`, `DebuggingDraft.tests`, `CodingDraft.tests` become `list[ExecutableTestCase] = Field(min_length=1)`
- Produces: `make_check(name, passed, detail, evidence=None) -> QuestionCheck`
- Produces: `Settings.validation_timeout_seconds: float = 2.0` (`gt=0`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_domain.py` inside `TestValidationPrecedence`:

```python
def test_check_records_severity_and_evidence(self) -> None:
    check = QuestionCheck(
        name="expected_output_verified",
        passed=False,
        severity="error",
        detail="Expected output verified",
        evidence="wanted '3' got '4'",
    )
    assert check.severity == "error"
    assert check.evidence == "wanted '3' got '4'"
    assert check.deterministic is True
```

Add to `tests/test_generation_schemas.py`:

```python
from app.generation.schemas import ExecutableTestCase

def test_executable_test_case_requires_stdout_or_assert() -> None:
    with pytest.raises(ValidationError):
        ExecutableTestCase(stdin="1\n")


def test_executable_test_case_allows_empty_stdout() -> None:
    case = ExecutableTestCase(stdout="")
    assert case.stdout == ""
    assert case.assert_code is None


def test_executable_test_case_accepts_assert_alias() -> None:
    case = ExecutableTestCase.model_validate({"assert": "assert add(1, 2) == 3"})
    assert case.assert_code == "assert add(1, 2) == 3"
```

Change `test_coding_requires_tests` to use `tests=[{"stdin": "", "stdout": "3\n"}]`.
Change `test_prompt_fields_from_testable_draft` tests to `[{"assert": "assert True"}]`.

Add to `tests/test_config.py`:

```python
def test_validation_timeout_default() -> None:
    assert _settings().validation_timeout_seconds == 2.0
```

Add `tests/test_validation_report.py`:

```python
from app.validation.report import make_check

def test_make_check_is_deterministic_error() -> None:
    check = make_check("allowed_difficulty", True, "Allowed difficulty")
    assert check.passed is True
    assert check.deterministic is True
    assert check.severity == "error"
    assert check.evidence is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_domain.py tests/test_generation_schemas.py tests/test_config.py tests/test_validation_report.py -v`

Expected: FAIL (`make_check` missing, `ExecutableTestCase` missing, timeout setting missing, and/or old test dicts still accepted without stdout/assert).

- [ ] **Step 3: Implement**

`QuestionCheck` — add `severity: str = "error"` and `evidence: str | None = None`.
`Question` — add `validation_report_json: str | None = None`.

`ExecutableTestCase` in `app/generation/schemas.py`:

```python
class ExecutableTestCase(BaseModel):
    """One hybrid stdin/stdout/assert case for executable question types."""

    model_config = ConfigDict(populate_by_name=True)

    stdin: str = ""
    stdout: str | None = None
    assert_code: str | None = Field(default=None, alias="assert")

    @model_validator(mode="after")
    def _requires_stdout_or_assert(self) -> ExecutableTestCase:
        if self.stdout is None and self.assert_code is None:
            raise ValueError("each test needs stdout or assert")
        return self
```

Need `ConfigDict` import. Set the three draft `tests` fields to `list[ExecutableTestCase] = Field(min_length=1)`.

`prompt_fields_from_draft` already `json.dumps(draft.tests)` — dump with `by_alias=True` so stored JSON uses `"assert"`:

```python
return draft.prompt, draft.reference_solution, json.dumps(
    [case.model_dump(mode="json", by_alias=True) for case in draft.tests]
)
```

`app/validation/report.py`:

```python
"""Helpers for building deterministic validation checks."""

from __future__ import annotations

from app.domain.questions import QuestionCheck


def make_check(
    name: str,
    passed: bool,
    detail: str,
    evidence: str | None = None,
) -> QuestionCheck:
    """Build a deterministic error-severity check."""
    return QuestionCheck(
        name=name,
        passed=passed,
        deterministic=True,
        severity="error",
        detail=detail,
        evidence=evidence,
    )
```

Add to `Settings` after LLM settings:

```python
validation_timeout_seconds: float = Field(default=2.0, gt=0)
```

Add to `.env.example`:

```
# Seconds a generated snippet may run during deterministic validation.
VALIDATION_TIMEOUT_SECONDS=2
```

Update FakeClient drafts in `tests/test_generation_pages.py` and `tests/test_generation_base.py` to `tests=[{"assert": "assert True"}]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_domain.py tests/test_generation_schemas.py tests/test_generation_pages.py tests/test_generation_base.py tests/test_config.py tests/test_validation_report.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```
feat(validation): add check evidence fields and hybrid test case schema
```

---

### Task 2: LocalCodeRunner

**Files:**
- Create: `app/validation/runner.py`
- Create: `tests/test_validation_runner.py`

**Interfaces:**
- Consumes: `ExecutableTestCase`, `get_settings().validation_timeout_seconds`
- Produces: `ScriptResult`, `TestRunSummary`, `LocalCodeRunner`, `normalize_output(text: str) -> str`, `EVIDENCE_LIMIT = 800`

`normalize_output`: replace `\r\n`/`\r` with `\n`, then strip at most one trailing `\n`.

`run_script`: write `snippet.py` in a temp dir; `subprocess.run([sys.executable, "-I", path], cwd=tmpdir, input=stdin, capture_output=True, text=True, timeout=timeout, env=minimal)`. On `TimeoutExpired`, `timed_out=True`, `exit_code=None`. Minimal env: `PATH`, `PYTHONIOENCODING=utf-8`; on `sys.platform == "win32"` also `SYSTEMROOT` and `WINDIR` from `os.environ`.

`run_tests`: for each case, `source` plus `\n` plus `assert_code` if set; `run_script` with case.stdin. A case passes when not timed out, `exit_code == 0`, and if `stdout is not None` then `normalize_output(result.stdout) == normalize_output(case.stdout)`. Summary `evidence` is truncated joined failure lines when not all passed.

- [ ] **Step 1: Write the failing tests** (`tests/test_validation_runner.py`)

```python
from __future__ import annotations

from app.generation.schemas import ExecutableTestCase
from app.validation.runner import LocalCodeRunner, normalize_output


def test_normalize_output_strips_one_trailing_newline() -> None:
    assert normalize_output("3\r\n") == "3"
    assert normalize_output("a\n\n") == "a\n"


def test_run_script_captures_stdout() -> None:
    result = LocalCodeRunner(timeout_seconds=2).run_script("print(1 + 2)")
    assert result.timed_out is False
    assert result.exit_code == 0
    assert normalize_output(result.stdout) == "3"


def test_run_script_times_out() -> None:
    result = LocalCodeRunner(timeout_seconds=0.3).run_script("import time; time.sleep(5)")
    assert result.timed_out is True


def test_run_tests_stdout_and_assert() -> None:
    source = "def add(a, b):\n    return a + b\n"
    summary = LocalCodeRunner(timeout_seconds=2).run_tests(
        source,
        [
            ExecutableTestCase(stdin="", stdout=None, assert_code="assert add(1, 2) == 3"),
            ExecutableTestCase.model_validate({"stdin": "", "assert": "assert add(2, 2) == 4"}),
        ],
    )
    assert summary.passed_count == 2
    assert summary.total == 2
    assert summary.timed_out is False


def test_run_tests_reports_stdout_mismatch() -> None:
    summary = LocalCodeRunner(timeout_seconds=2).run_tests(
        "print(4)",
        [ExecutableTestCase(stdout="3")],
    )
    assert summary.passed_count == 0
    assert summary.total == 1
    assert summary.evidence
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_runner.py -v`

Expected: FAIL (module missing)

- [ ] **Step 3: Implement `app/validation/runner.py`**

Module docstring must state: local research prototype; `-I` and timeout are not a multi-tenant sandbox; generated code can still use the filesystem.

Implement as specified. Truncate evidence with `EVIDENCE_LIMIT = 800`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_validation_runner.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```
feat(validation): add local isolated subprocess runner for hybrid tests
```

---

### Task 3: Shared grounding checks

**Files:**
- Create: `app/validation/shared.py`
- Create: `tests/test_validation_shared.py`

**Interfaces:**
- Consumes: `Question`, `Session`, `CurriculumRepository`, `BookStructureRepository`, `make_check`, `CurriculumStatus`
- Produces: `check_shared(question: Question, session: Session | None) -> list[QuestionCheck]` always returning four checks in this order: `approved_taxonomy_ids`, `source_section_ids`, `allowed_question_type`, `allowed_difficulty`

Pass details verbatim from the Interfaces section.

Fail details (use these exact strings):

- taxonomy: `Curriculum IDs are not an approved topic/subtopic pair.`
- sources: `Source section IDs are missing or do not exist.`
- type: `Question type is not allowed.`
- difficulty: `Difficulty is not allowed.`

Logic:

- `allowed_question_type` passes iff `question.question_type` is not `None`.
- `allowed_difficulty` passes always for a constructed `Question` (field is a `Difficulty`); still emit the check so the UI can show it.
- Taxonomy: session required. Load version with `CurriculumRepository(session).get_with_tree`. Fail on `NotFoundError`, status not `APPROVED`, topic id missing from that version, or subtopic not under that topic.
- Sources: collect ints from `spec_json` (`source_section_ids`) and `content_json` `sources` list `section_id`. Empty set fails. Each id must exist via `BookStructureRepository.get_section` (catch `NotFoundError`). Invalid JSON for spec/content is treated as no ids from that field.

Reuse the seed pattern from `tests/test_generation_pages.py` `_seed` (book JSON + taxonomy JSON).

- [ ] **Step 1: Write the failing tests**

```python
from app.domain.enums import Difficulty, QuestionType
from app.domain.questions import Question
from app.validation.shared import check_shared

def test_shared_checks_pass_for_seeded_ids(session, settings) -> None:
    # seed book + approved taxonomy; build Question with those ids and spec/content sources
    ...
    checks = {c.name: c for c in check_shared(question, session)}
    assert checks["approved_taxonomy_ids"].passed is True
    assert checks["approved_taxonomy_ids"].detail == "Approved curriculum IDs"
    assert checks["source_section_ids"].passed is True
    assert checks["allowed_question_type"].passed is True
    assert checks["allowed_difficulty"].passed is True


def test_shared_checks_reject_unknown_section(session, settings) -> None:
    ...
    question.content_json = '{"sources":[{"section_id": 999999}]}'
    checks = {c.name: c for c in check_shared(question, session)}
    assert checks["source_section_ids"].passed is False


def test_shared_checks_reject_null_type(session, settings) -> None:
    question = Question(prompt="x", question_type=None)
    checks = {c.name: c for c in check_shared(question, session)}
    assert checks["allowed_question_type"].passed is False
```

Include a test that a non-approved curriculum version fails `approved_taxonomy_ids` if you can construct one; otherwise missing ids / wrong topic is enough.

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_validation_shared.py -v`

- [ ] **Step 3: Implement `check_shared`**

- [ ] **Step 4: Run to verify pass**

- [ ] **Step 5: Commit**

```
feat(validation): check approved taxonomy, source, type, and difficulty
```

---

### Task 4: Type-specific checks and invalid fixtures

**Files:**
- Create: `app/validation/type_checks.py`
- Create: `tests/test_validation_types.py`

**Interfaces:**
- Consumes: `LocalCodeRunner`, `ExecutableTestCase`, `make_check`, `normalize_output`
- Produces: `load_content(question: Question) -> dict | None` (`None` if missing/invalid JSON/not a dict)
- Produces: `check_type(question: Question, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]`

Dispatch on `question.question_type`. If type is `None`, return `[]` (shared checks already failed it).

Implement every type per spec. Helpers:

- `_parses(source: str) -> bool` via `ast.parse`
- `_parse_tests(raw: object) -> list[ExecutableTestCase] | None` — `None` means harness invalid (not a list, empty list, or any case fails `ExecutableTestCase` validation)
- Parsons reconstruct: `(" " * (4 * indent)) + text` joined by `\n`; `compile(source, "<parsons>", "exec")`
- Debugging broken exhibits issue: run tests against `content["code"]`; pass this check if harness invalid is already reported, or broken `passed_count < total` or `timed_out` or parse fail of broken code

Invalid fixtures (each must produce `passed=False` on the named check, or `content` so badly shaped that the type check fails that name):

| Type | Fixture | Named failure |
| ---- | ------- | ------------- |
| MC | duplicate option strings | `mc_no_duplicate_options` |
| MC | `correct_option_index` 9 with 2 options | `mc_correct_option_exists` |
| TF | `correct_answer`: `"yes"` | `tf_boolean_answer` |
| TF | missing/blank explanation | `tf_explanation_present` |
| Output | `code` `def (` | `output_code_parses` |
| Output | code `print(4)` expected `3` | `expected_output_verified` |
| Completion | tests `[{}]` | `harness_valid` |
| Completion | reference `def (` | `completion_reference_parses` |
| Debugging | broken code already `print(3)` and tests expect `3` | `debug_broken_exhibits_issue` |
| Debugging | reference fails tests | `reference_passes_tests` |
| Parsons | `correct_order` missing a block | `parsons_order_consistent` |
| Parsons | indent `-1` | `parsons_indent_valid` |
| Coding | reference `print(1)` vs stdout `2` | `reference_passes_tests` |

Happy paths (all type checks passed):

- MC: 2 unique options, index 0, explanation present
- TF: `correct_answer` bool, explanation present
- Output: `print(3)` / expected `3`
- Completion: `def add(a,b):\n    return a+b` with `{"assert": "assert add(1,2)==3"}`
- Debugging: broken `print(1)` vs tests stdout `2`; reference `print(2)`
- Parsons: `print(3)` as one block indent 0, order that block, compiles
- Coding: same as completion reference+assert

Tests should build a `Question` with `content_json=json.dumps(...)` and call `check_type` with a `LocalCodeRunner(timeout_seconds=2)`.

- [ ] **Step 1: Write failing tests covering every row above**

- [ ] **Step 2: Run `pytest tests/test_validation_types.py -v` — expect fail**

- [ ] **Step 3: Implement `type_checks.py`**

- [ ] **Step 4: Run until pass**

- [ ] **Step 5: Commit**

```
feat(validation): add per-type deterministic checks and fixtures
```

---

### Task 5: Orchestrator, persistence, generation hook

**Files:**
- Create: `app/validation/service.py`
- Modify: `app/validation/__init__.py`
- Modify: `app/persistence/models.py`
- Modify: `app/generation/service.py`
- Modify: `tests/test_boundaries.py`
- Create: `tests/test_validation_service.py`
- Modify: `tests/test_persistence.py` (assert `validation_report_json` round-trip)

**Interfaces:**
- Consumes: `check_shared`, `load_content`, `check_type`, `LocalCodeRunner`, `QuestionValidationReport`
- Produces: `DeterministicQuestionValidator(session=None).validate(question) -> QuestionValidationReport`
- Produces: `get_question_validator(session=None) -> QuestionValidator` returning `DeterministicQuestionValidator`
- Produces: `QuestionRow.validation_report_json` nullable Text
- GenerationService after `_questions.add`: flush already happens in `add`; call validator with a domain `Question` copy that has `id=row.id` and the same fields; set `row.validation_report_json = report.model_dump_json()` and `row.status = report.resulting_status()`

`validate` algorithm:

1. `checks = check_shared(question, session)`
2. `content = load_content(question)`
3. If `content is None`: append `make_check("content_unreadable", False, "Question content is readable")`; return report (no type checks)
4. Else `checks.extend(check_type(question, content, LocalCodeRunner()))`
5. Return `QuestionValidationReport(question_id=question.id, checks=checks)`

Package docstring: implemented; allowed deps include persistence + generation.schemas; no LLM. Remove `NullQuestionValidator` and `PLANNED_DETERMINISTIC_CHECKS` (or keep the tuple unused — prefer remove).

`test_question_validation_fails_loudly` becomes `test_question_validation_returns_a_report`: `get_question_validator().validate(Question(prompt="Anything"))` returns a `QuestionValidationReport` whose `passed` is False (null type / missing taxonomy).

Generation hook test: reuse FakeClient + `_seed`; after `generate_for_sections`, loaded row has non-empty `validation_report_json` and status is `validation_passed` or `validation_failed` (not `generated`). Prefer a FakeClient coding/output draft that passes so status is `validation_passed`.

Copy `validation_report_json` in `_row_from_question` if present.

- [ ] **Step 1: Write failing tests** (boundary + service persist/hook + persistence column)

- [ ] **Step 2: Run them — expect fail**

- [ ] **Step 3: Implement orchestrator, column, hook**

- [ ] **Step 4: Run `pytest tests/test_validation_service.py tests/test_boundaries.py tests/test_persistence.py tests/test_generation_pages.py tests/test_generation_base.py tests/test_generation_integration.py -v`**

Expected: PASS

- [ ] **Step 5: Commit**

```
feat(validation): persist reports and validate after generation
```

---

### Task 6: Automatic Checks UI, ADR-023, full suite

**Files:**
- Modify: `app/web/routes/pages.py` (`question_detail`)
- Modify: `app/web/templates/question_detail.html`
- Modify: `app/web/static/css/app.css`
- Modify: `docs/DECISIONS.md`
- Create: `tests/test_validation_pages.py`

**Interfaces:**
- Consumes: `validation_report_json` on the row
- Produces: template context `validation_checks` (list of dicts or `QuestionCheck`) and `validation_passed` (bool | None if no report)

Parse report with `QuestionValidationReport.model_validate_json`. On bad JSON, treat as no report.

Template (place the panel after Assessment details):

```html
  <section class="panel {% if validation_passed is none %}{% elif validation_passed %}panel-success{% else %}panel-error{% endif %}">
    <h2>Automatic Checks</h2>
    {% if validation_checks %}
      <ul class="checklist">
        {% for check in validation_checks %}
          <li>
            {% if check.passed %}✓{% else %}✗{% endif %} {{ check.detail or check.name }}
            {% if not check.passed and check.evidence %}
              <pre class="check-evidence">{{ check.evidence }}</pre>
            {% endif %}
          </li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="empty">Automatic checks have not been recorded.</p>
    {% endif %}
  </section>
```

CSS:

```css
.check-evidence { margin: 6px 0 0; font-size: 12px; white-space: pre-wrap; }
```

Exact UI test: seed book+taxonomy; insert a `QuestionRow` with `validation_report_json` containing a passing `approved_taxonomy_ids` check whose detail is `Approved curriculum IDs`; `GET /questions/{id}` status 200; body contains `Automatic Checks` and `Approved curriculum IDs` and `✓`.

Also a failing report shows `✗` and `Automatic Checks`.

ADR-004 implications: replace the sentence about raising until sandbox design with: deterministic execution checks run via a local isolated subprocess runner (ADR-023); validation stores a report and never returns a vacuously empty passing report.

ADR-022 implications: remove “Automatic validation … remain deferred”; validation is implemented.

Append **ADR-023 — Local deterministic validation uses an isolated subprocess runner**:

- Status accepted
- Hybrid test shape
- `-I` + timeout + temp dir
- No LLM in validation
- Limitations: not multi-tenant isolation; filesystem still reachable in theory
- UI Automatic Checks
- Report stored on the question

- [ ] **Step 1: Write `tests/test_validation_pages.py` (exact phrases above)**

- [ ] **Step 2: Run — expect fail (heading missing)**

- [ ] **Step 3: Implement UI + ADRs**

- [ ] **Step 4: Full suite**

```
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Expected: all pass. If ruff format fails, run `ruff format .` and re-check.

- [ ] **Step 5: Commit**

```
feat(validation): show Automatic Checks and record ADR-023
```

---

## Completion report (after Task 6)

Return to the user:

- Validators implemented (shared + per-type names)
- Runtime/safety strategy
- Files changed
- Tests/results (command + pass)
- Known limitations
- Exact UI test: `tests/test_validation_pages.py` asserting `Automatic Checks` and `Approved curriculum IDs`
