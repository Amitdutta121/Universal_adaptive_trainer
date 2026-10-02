# Generic assessment — isolated capabilities, any subject

Supersedes `docs/SUBJECT_PROFILE_MILESTONES.md` (its "one subject per database" decision predates
courses; ADR-051/054 made the subject a property of the course).

**Goal.** Grading is done by **isolated capability graders** that know nothing about the app, and
every prompt (generator, judges, judge-learning) follows the **course's subject** instead of
assuming introductory Python. Python courses behave exactly as before.

- **Track C — capabilities** (done, ADR-055): a standalone `graders/` package; the app grades
  through it.
- **Phase 2** (second half): question types become one module each (T0), then subject-neutral
  prompts (S), validation through `check_spec` (C8) and the first non-Python types (T1, T2) run
  in parallel.

---

## Decisions (apply to every work package)

1. **Isolation is enforced, not hoped for.** `graders/` is a top-level package beside `app/`.
   It imports only the standard library, pydantic, pint and sympy. A test fails if any file under
   `graders/` imports `app` (AST scan), and `graders/` tests run without the app's fixtures.
2. **One grader per capability, versioned.** Capability ids are the ones in
   `app/assessment/catalog.py` (`structured.choice`, `code.python.tests`, …). Each grader declares
   `capability`, `version` (e.g. `"1"`), a pydantic **spec** model (per-question settings) and an
   **answer** convention.
3. **Two calls per grader.** `check_spec(spec) -> list[SpecIssue]` (is this question gradable:
   well-formed, reference answer scores full marks) and `grade(spec, answer) -> GradeResult`.
   A malformed **answer** is a wrong answer (score 0, `format_error` set), never an exception; a
   malformed **spec** raises `SpecError` (the question should not have been served).
4. **Scores are 0–1 inside `graders/`; the app keeps 0–100** at its edge (`MAX_SCORE`).
5. **Code runs through an `Executor`**, never `subprocess` inside a grader. `LocalExecutor` is
   today's runner, moved; `PistonExecutor` (sandbox, Docker) is chosen by config.
6. **Behaviour-identical first.** Moving the five built capabilities must not change any score: a
   replay of every stored attempt, old path vs new, must match exactly before the old code is
   deleted.
7. **The app owns question types; graders own checking.** The app maps a stored question's
   `content` to a grader spec (`app/assessment/specs.py`). Question-type-specific authoring
   checks that are not "can this be graded" (e.g. a debugging question's buggy code must fail)
   stay in `app/validation/type_checks.py`, using the executor.

## The contract (C0 — written first, then frozen)

```python
# graders/core.py
class SpecError(Exception): ...                 # the question cannot be graded at all

@dataclass(frozen=True)
class TestResult:  name: str; passed: bool; points: float; max_points: float; message: str | None

@dataclass(frozen=True)
class GradeResult:
    score: float                                # 0.0 – 1.0
    tests: tuple[TestResult, ...] = ()          # per-test detail (code graders), else empty
    feedback: str | None = None                 # shown to the student afterwards
    format_error: str | None = None             # the answer could not be read (scored 0)

@dataclass(frozen=True)
class SpecIssue:   code: str; message: str

class Grader(Protocol):
    capability: str
    version: str
    spec_model: type[BaseModel]
    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]: ...
    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult: ...

# graders/executors/base.py
@dataclass(frozen=True)
class RunRequest:  language: str; source: str; stdin: str = ""; timeout_s: float = 5.0
@dataclass(frozen=True)
class RunResult:   stdout: str; stderr: str; exit_code: int | None; timed_out: bool
                    infra_error: str | None = None   # added in C5: executor could not run it
class ExecutorError(Exception): ...   # graders raise it for infra_error; never graded as wrong
class Executor(Protocol):
    def run(self, request: RunRequest) -> RunResult: ...

# graders/registry.py
def get_grader(capability: str) -> Grader: ...  # KeyError for an unknown or unbuilt capability
def available_capabilities() -> list[str]: ...
def set_executor(factory: Callable[[], Executor] | None) -> None: ...
def get_executor() -> Executor: ...   # added in C5: the one shared executor; the app's authoring checks use it too

# Every grader module (graders/structured.py, ...) exposes exactly one entry point,
# which the registry imports by module path:
def build(executor_factory: Callable[[], Executor]) -> list[Grader]: ...
```

Each work package adds files; **none edits the contract files** after C0. A change to the contract
goes back to the lead.

---

## Track C — work packages

```
C0 contract ──┬── C1 structured graders ──┐
              ├── C2 python graders ──────┼── C5 app integration + replay ── C6 sandbox switch-over
              ├── C3 quantity grader      │
              ├── C4 symbolic grader      │
              └── C7 sandbox executor ────┘
```
C1–C4 and C7 run **in parallel** (disjoint files). C5 needs C1+C2. C6 needs C5+C7.

**Status (2026-10-01): C0–C7 done** (ADR-055). Replay: 345 stored attempts and 37 synthetic cases identical;
342 stored questions re-validate identically; synthetic cases also identical with `EXECUTOR=piston`.
C6 keeps `local` as the default in development; production must set `EXECUTOR=piston`.

| WP | Owns (only these files) | Deliverable | Acceptance (its own tests) |
|---|---|---|---|
| **C0** lead | `graders/__init__.py`, `core.py`, `registry.py`, `executors/__init__.py`, `executors/base.py`, `tests/graders/test_isolation.py`, `pyproject.toml` | contract + registry skeleton + isolation test | isolation test passes; registry lists nothing yet |
| **C1** | `graders/structured.py`, `graders/text.py`, `tests/graders/test_structured.py`, `tests/graders/test_text.py` | `structured.choice` (single and multi-correct), `structured.ordering` (order + optional indent), `text.normalized_match` (line endings + one trailing newline; optional case/space folding off by default) | answer conventions identical to `app/adaptive/scoring.py` (index string; `true`/`false`; Parsons newline/comma layout, 4-space indents, tabs = 1 level) |
| **C2** | `graders/python.py`, `graders/executors/local.py`, `tests/graders/test_python.py` | `code.python.execute` (run, capture) and `code.python.tests` (hybrid stdin/stdout/assert cases, partial credit) on `LocalExecutor` (today's `LocalCodeRunner` logic, moved) | same pass/fail and evidence text as `app/validation/runner.py` on the existing runner tests' cases |
| **C3** | `graders/quantity.py`, `tests/graders/test_quantity.py` | `quantity.units`: value + unit, relative/absolute tolerance, accepted units, unit conversion via pint, sig-fig option | `9.81 m/s^2` vs `981 cm/s^2` passes; wrong dimension is a format error; tolerance edges |
| **C4** | `graders/symbolic.py`, `tests/graders/test_symbolic.py` | `symbolic.expression_equivalence`: parse with `sympy.parsing` (safe transformations, **no `eval` of arbitrary input**), declared variables, equivalence by simplify + randomized numeric check | `2*x*sin(x)+x**2*cos(x)` ≡ `x*(2*sin(x)+x*cos(x))`; non-equivalent fails; malicious input (`__import__`) is a format error |
| **C7** | `graders/executors/piston.py`, `docker/piston/` (compose + README), `tests/graders/test_piston.py` (skipped without Docker) | `PistonExecutor` over Piston's HTTP API with CPU/memory/output limits | hostile suite contained (file write outside sandbox, network, fork bomb, infinite loop); same `RunResult` as `LocalExecutor` on the C2 cases |
| **C5** lead | `app/assessment/specs.py`, `app/adaptive/scoring.py`, `app/validation/runner.py`, `app/validation/type_checks.py`, `tests/test_grader_replay.py` | the app grades through `graders/`: content → spec mapping for the 7 types; scoring calls `get_grader`; validation uses the executor; old runner becomes a thin shim then goes | **replay: every stored attempt scores identically old vs new**; re-validating every stored question gives identical reports; full suite green |
| **C6** lead | `app/config.py`, `.env.example` | `EXECUTOR=local|piston` (+ `PISTON_URL`), applied at startup by `app/assessment/executor.py` | switching to piston keeps the suite green (Docker present) |

**Rules for parallel agents.** Touch only the files you own. Do not edit the contract, the app, or
another package's files. Run `pytest tests/graders/test_<yours>.py` and `ruff check graders/<yours>`
before reporting. No commits. Report: files, test output, deviations from the contract.

**Validation (track C).**
```
.\.venv\Scripts\python.exe -m pytest tests/graders -q
.\.venv\Scripts\python.exe -m pytest tests/test_grader_replay.py -q   # after C5
.\.venv\Scripts\python.exe -m pytest -q                               # whole suite
```

---

## Phase 2 — subject-neutral generation and new question types (parallel plan)

**Where we are.** Track C is done (ADR-055), but generation is still Python-only. The system prompt
says "introductory-Python" (`app/generation/principles.py:5`). The course's question types only
gate what may be requested (`app/web/routes/api/deps.py::ensure_question_types_allowed`). Numeric
and formula graders exist, but no question type uses them. Authoring checks
(`app/validation/type_checks.py`) never call a grader's `check_spec`.

**Goal.**
- Generation, validation and judging follow the course's subject.
- A Physics course can offer numeric-with-units and equation questions end to end: generated,
  validated, answered and scored.
- Python courses behave exactly as before.

**Why there is a wave 0.** Per-type logic is switched on `QuestionType` in six backend places and
four frontend files:
- **Backend:**
  - `generation/prompts.py::_TYPE_INSTRUCTIONS`
  - `generation/schemas.py::RESPONSE_MODEL_FOR` and `scoring_kind_for`
  - `assessment/specs.py::plan_for`
  - `validation/type_checks.py::_CHECKER_FOR`
  - `web/routes/api/schemas.py`
  - `assessment/catalog.py`
- **Frontend:**
  - `student-session-screen.tsx`
  - `review-question-content.tsx`
  - `questions-browser.tsx`
  - `spec-sheet-types.ts`

Two agents adding types in parallel would collide on every one of those. Wave 0 turns each type into
**one backend module and one frontend file**. After that, a new type is new files only.

### Phase 2 decisions

1. **One type, one module.** Everything type-specific lives in `app/question_types/<type>.py` and
   `frontend/src/lib/question-types/<type>.tsx`:
   - the draft schema;
   - the shipped instruction;
   - stored content;
   - the grading plan;
   - type-only authoring checks;
   - the answer input;
   - the review renderer.

   The old switch points become lookups.
2. **Implemented is derived.** A type is `implemented` when its backend module is registered, the
   same way `built` follows the graders registry. Nobody edits `implemented=` flags in
   `catalog.py`.
3. **Gradable means `check_spec`.** Validation asks the type's grading plan and the grader's
   `check_spec` whether a question can be marked. Type modules keep only the checks that are not
   about grading, for example "the buggy code must fail".
4. **The subject comes from the course.** Every prompt is built from a `SubjectProfile`: subject
   preset plus "does any chosen type run code". The Python profile reproduces today's prompts
   byte for byte (golden file).
5. **Behaviour-identical gates on every refactor.** Each refactor must keep all of these:
   - the golden prompts;
   - `scripts/replay_grading.py` (345 attempts);
   - `scripts/revalidate_questions.py` (342 questions; same pass/fail per question);
   - the full backend suite and vitest.
6. **No live LLM without a go.** Every package proves itself with the fake LLM client. A live run
   happens only after Amit says go.

### Seam contract (written in wave 0, then frozen)

```python
# app/question_types/base.py
class QuestionTypeModule(Protocol):
    question_type: QuestionType
    kind: QuestionKind                                  # discrete | testable_program
    draft_model: type[TaxonomyClaim]                    # what the LLM must return
    instruction: str                                    # shipped type instruction (ADR-033 may replace it)
    def columns_from_draft(self, draft) -> DraftColumns   # prompt / reference_solution / tests columns
    def grading_plan(self, content: dict, tests: object) -> GradingPlan    # raises Unmarkable
    def authoring_checks(self, content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]
    def student_view(self, content: dict, *, seed: int) -> StudentView   # whitelist: options, code,
                                                                         # blocks, answer_hint
# Each module ends with  TYPE = <instance>.  The whole draft is stored as `content` (build_content).

# app/question_types/__init__.py
_MODULES = (..., "app.question_types.numeric_response", "app.question_types.equation_response")
def get_type(question_type: QuestionType) -> QuestionTypeModule: ...   # KeyError if not built
def implemented_types() -> list[QuestionType]: ...                       # missing module = not built
def type_for_draft(draft) -> QuestionTypeModule: ...
```

Shared helpers for type modules: `app/question_types/_shared.py` (explanation, test-case specs,
authoring-check helpers, the executable-test contract text) and `_executable.py` (base for the
code types). `ServedQuestionOut.answer_hint` carries `StudentView.answer_hint` to the student.
Unbuilt types: generation refuses them (`InvalidQuestionSpecError`), the instruction API answers
501, validation reports `question_type_built` failed, scoring treats them as unmarkable.

```ts
// frontend/src/lib/question-types/registry.ts
export type QuestionTypeUI = {
  answerLabel: string;
  AnswerInput: React.FC<{ question: StudentQuestion; value: string; onChange(v: string): void }>;
  ReviewContent: React.FC<{ content: QuestionContent }>;
};
export const QUESTION_TYPE_UI: Record<QuestionType, QuestionTypeUI | null>;  // null = not built
```

- **Enum values:** `QuestionType.NUMERIC_RESPONSE` and `EQUATION_RESPONSE` are added in wave 0.
  The column is a string (`StrEnumType`), so no migration is needed.
- **Placeholder files:** wave 0 creates the frontend files `numeric-response.tsx` and
  `equation-response.tsx` exporting `null` (`// TODO(real): T1/T2`). T1 and T2 replace only
  their own file.

### Waves

```
Wave 0 (lead, short)   S0 golden prompts ──► T0a backend type seams
                                             T0b frontend type seams      (T0a ∥ T0b)
Wave 1 (parallel)      S1 subject prompts │ S2 per-subject personalization │ S4 UI strings
                       C8 validation via check_spec │ T1 numeric_response │ T2 equation_response
                       C9 grader hardening
Wave 2 (lead)          S3 wire subject through call sites ─► S5 end-to-end (fake LLM) ─► live run on go
```

### Work packages

| WP | Wave | Owns (only these files) | Deliverable | Acceptance |
|---|---|---|---|---|
| **S0** lead | 0 | `tests/golden/python_prompts.json`, `scripts/show_prompts.py`, `tests/test_golden_prompts.py` | Snapshot of every shipped prompt (generator system and per-type, judges, judge-learning), **captured from the unmodified code** | Snapshot test passes on the current code |
| **T0a** lead | 0 | `app/question_types/` (base, registry, the 7 existing types), and the dispatch points in `generation/prompts.py`, `generation/schemas.py`, `generation/base.py`, `assessment/specs.py`, `assessment/catalog.py` (`implemented` derived), `validation/type_checks.py`, `web/routes/api/schemas.py`, `domain/enums.py` (2 new values) | Each existing type moves into its own module; the switch points become `get_type()` lookups. The two new enum values are added with no backend module, so they are not implemented. | All decision-5 gates identical. `catalog` still offers exactly the 7 types. |
| **T0b** lead | 0 | `frontend/src/lib/question-types/` (registry, the 7 existing types, 2 `null` placeholders), and the per-type branches in `student-session-screen.tsx`, `review-question-content.tsx`, `questions-browser.tsx`, `spec-sheet-types.ts` | Per-type UI moves behind `QUESTION_TYPE_UI`. Screens look unchanged. | tsc, biome lint and vitest pass. Before/after screenshots of each of the 7 types are identical. |
| **S1** | 1 | `app/subjects/` (new: `SubjectProfile`, `profile_for(course)`), `app/generation/principles.py`, `app/evaluation/prompts.py`, `app/evaluation/judge_learning.py`, `tests/test_subject_prompts.py` | Prompts become functions of a profile. Code-only fragments and issue codes appear only when a code type is chosen. The module-level constants stay, as the Python profile's output, so callers keep working until S3. | Python profile matches the golden file byte for byte. A Physics profile's prompts contain none of `python`, `code`, `program`, `tests`. `effective_rubric_version` is unchanged for Python. |
| **S2** | 1 | migration `0004_subject_scoped_personalization`, `app/persistence/models.py` (`subject` on `judge_prompts` and `type_instructions` only), `app/evaluation/judge_prompts.py`, `app/personalization/instructions.py`, `tests/test_subject_personalization.py` | Edited judge prompts and learned instructions are scoped per subject; existing rows become `intro_python`. | A rule learned in a Python course never reaches a Physics course. The migration upgrades a copy of the real DB. |
| **S4** | 1 | `frontend/src/lib/navigation.ts`, landing page, the non-type strings in the student and questions screens | No hard-coded subject left in shared UI; the course's subject label is used instead. | `grep -ri python frontend/src` hits only code-type files under `lib/question-types/` and tests. |
| **C8** | 1 | `app/validation/gradable.py` (new), `app/validation/service.py`, `app/question_types/{the 7 existing}.py` (only their `authoring_checks`), `tests/test_gradable.py` | One check, `gradable`: `get_type().grading_plan()` followed by `get_grader().check_spec()`. Every per-type check that duplicates it is removed. | `scripts/revalidate_questions.py` gives the same pass/fail per question on all 342. A question with an out-of-range correct option, or a reference that fails its tests, still fails. |
| **T1** | 1 | `app/question_types/numeric_response.py`, `frontend/src/lib/question-types/numeric-response.tsx`, `tests/question_types/test_numeric_response.py` | Numeric response (graded by `quantity.units`). Draft: `prompt`, `value`, `unit`, `tolerance`, `accepted_units?`, `sig_figs?`, `explanation`. A subject-neutral instruction. The answer input is a number plus unit field. The review panel shows value, unit and tolerance. | A fake-LLM draft becomes a stored question that passes validation. `9.81 m/s^2` and `981 cm/s^2` both score 100. A wrong dimension scores 0 with a format message. The type shows as implemented in the catalog. |
| **T2** | 1 | `app/question_types/equation_response.py`, `frontend/src/lib/question-types/equation-response.tsx`, `tests/question_types/test_equation_response.py` | Equation response (graded by `symbolic.expression_equivalence`). Draft: `prompt`, `expected`, `variables`, `equation?`, `explanation`. The answer input is a math text field with a hint (`^`, implicit ×). | A fake-LLM draft validates. `x*(2*sin(x)+x*cos(x))` scores 100 against `2*x*sin(x)+x**2*cos(x)`. Input containing `__import__` scores 0 with a format message. The type is implemented. |
| **C9** | 1 | `graders/symbolic.py`, `graders/quantity.py`, `app/assessment/executor.py`, their tests | Review leftovers: symbolic budget runs in a killable child process instead of a daemon thread; quantity value 0 uses an absolute tolerance; startup refuses `EXECUTOR=local` when `ENVIRONMENT=production`. | The C4/C3 suites still pass. A pathological expression leaves no running thread. A production boot with the local executor fails clearly. |
| **S3** lead | 2 | `generation/base.py`, `generation/service.py`, `generation/batch.py`, the evaluation call sites, the judge-learning trigger, `frontend/src/lib/api/schema.d.ts` (regenerated) | The course's profile reaches generation, judging, batch re-runs and judge-learning, via question → curriculum version → course. | A fake LLM records a Physics prompt for a Physics course and the golden prompt for a Python course. OpenAPI types are regenerated, and tsc passes. |
| **S5** lead | 2 | `tests/test_subject_end_to_end.py`, "ML / LLMs" preset in `catalog.py` | End-to-end Physics run with the fake LLM. Create a course with MCQ, numeric and equation; generate; validate; take a student session with right and wrong answers; check the dashboard. The Python course runs the same way. | Both pass. One live LLM run per new type **only after a go** (spends API budget). |

### Rules for parallel agents (wave 1)

- **Scope:** touch only the files in your row. In particular, do not edit the seam contract
  (`app/question_types/base.py`, `__init__.py`, `frontend/src/lib/question-types/registry.ts`),
  the graders contract, or another row's files. If you need a seam change, stop and report it.
- **Branches:** each agent works in its own git worktree (`isolation: "worktree"`) branched from
  the wave-0 commit. The lead merges in this order: S2 → S1 → C8 → T1 → T2 → C9 → S4, then runs
  the decision-5 gates after each merge.
- **Cost:** fake LLM only. No commits to `feature/courses`. No API spend.
- **Report:** files changed, the test command output, and any deviation from the contract.

### Validation (phase 2)

```
.\.venv\Scripts\python.exe -m pytest tests/test_golden_prompts.py tests/question_types tests/graders -q
.\.venv\Scripts\python.exe -m scripts.replay_grading          # 345 identical
.\.venv\Scripts\python.exe -m scripts.revalidate_questions    # 342, same pass/fail
.\.venv\Scripts\python.exe -m pytest -q                       # whole suite
cd frontend; pnpm exec tsc --noEmit; pnpm exec biome lint .; pnpm exec vitest run
```

---

## Later (not in these milestones)

- `semantic.source_grounded` (LLM rubric grader, practice only) and a `short_explanation` type on
  top of it.
- Multi-language code types via the same executor (Piston already supports other languages).
- Changing a course's question types after creation.

**Active:** wave 0 (S0 → T0a ∥ T0b). Track C (C0–C7) is done.
