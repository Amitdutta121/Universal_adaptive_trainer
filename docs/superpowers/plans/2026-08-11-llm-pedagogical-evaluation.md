# LLM Pedagogical Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every generated question gets a stored, visible structured LLM pedagogical evaluation that is clearly separate from deterministic validation and never overrides deterministic failure.

**Architecture:** Thin `app/evaluation/` package (rubric + Pydantic schemas + `PedagogicalJudge`). `GenerationService` owns skip-vs-call orchestration after `DeterministicQuestionValidator`. Persist `pedagogical_eval_json` beside `validation_report_json`. Detail page shows two panels.

**Tech Stack:** Pydantic v2, Instructor via existing `StructuredLLMClient`, SQLAlchemy 2.0, Jinja2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-11-llm-pedagogical-evaluation-design.md`

## Global Constraints

- Judge is advisory only (ADR-004). `QuestionStatus` comes only from `QuestionValidationReport.resulting_status()`.
- `GenerationService` owns skip orchestration; `PedagogicalJudge` never decides to skip.
- Skip when deterministic `report.passed` is false → store `status=skipped`, reason `deterministic_failed`; do not call the judge.
- On judge path: up to 3 attempts (initial + 2 retries) on `LLMRequestError` / `MalformedModelOutputError`; then store `status=error`; keep `VALIDATION_PASSED`.
- Overall score = unweighted arithmetic mean of applicable dimension scores; summary only; dimensions are primary.
- Judge input = complete question artifact + only relevant source section(s) and approved topic/subtopic (name + description).
- `app/validation/` stays LLM-free.
- Reuse `StructuredLLMClient`; do not add a second HTTP stack.
- Python 3.12, `from __future__ import annotations`, ruff line length 100.
- Tests mock the judge/LLM; never write the developer `data/` directory.
- Commands: `.\.venv\Scripts\python.exe -m pytest <file> -v` then full `pytest`, `ruff check .`, `ruff format --check .` before commit.
- Do not edit `.cursor/plans/` files.
- Existing local SQLite DBs missing the new column must be recreated (`verify_schema` / ADR-008).

## File structure

| Path | Responsibility |
| ---- | -------------- |
| `app/evaluation/__init__.py` | Package boundary + public exports |
| `app/evaluation/rubric.py` | `RUBRIC_VERSION`, dimension ids, system/user prompt builders |
| `app/evaluation/schema.py` | LLM response model + stored `PedagogicalEvaluation` + summary helpers |
| `app/evaluation/service.py` | `PedagogicalJudge`, `skipped_evaluation`, context loading |
| `app/domain/questions.py` | `Question.pedagogical_eval_json` |
| `app/persistence/models.py` | `QuestionRow.pedagogical_eval_json` |
| `app/generation/service.py` | Orchestrate skip / judge after deterministic validate |
| `app/web/routes/pages.py` | Pass pedagogical eval into detail template |
| `app/web/templates/question_detail.html` | Two panels: Deterministic + LLM evaluation |
| `app/web/static/css/app.css` | Minimal styles for dimension list / rationale |
| `docs/DECISIONS.md` | ADR-024 |
| `CLAUDE.md` | Module map entry for `evaluation/` |
| `tests/test_evaluation_schema.py` | Schema + mean + status bands + malformed |
| `tests/test_evaluation_service.py` | Judge retries, completed/error, no skip inside judge |
| `tests/test_evaluation_generation.py` | Generation orchestration + precedence |
| `tests/test_evaluation_pages.py` | Detail UI shows both panels |
| `tests/test_boundaries.py` | Include `app.evaluation` |
| `tests/test_validation_service.py` (and other FakeClients) | Dispatch on `response_model` so judge path works |

## Interfaces (locked)

```python
# app/evaluation/rubric.py
RUBRIC_VERSION = "pedagogical-judge@1"

class JudgeDimensionId(StrEnum):
    SOURCE_GROUNDING = "source_grounding"
    SUBTOPIC_ALIGNMENT = "subtopic_alignment"
    DIFFICULTY_ALIGNMENT = "difficulty_alignment"
    CLARITY = "clarity"
    AMBIGUITY = "ambiguity"
    PEDAGOGICAL_USEFULNESS = "pedagogical_usefulness"
    INTRO_PYTHON_APPROPRIATENESS = "intro_python_appropriateness"
    ANSWER_EXPLANATION_CONSISTENCY = "answer_explanation_consistency"
    DISTRACTOR_QUALITY = "distractor_quality"
    TEST_QUALITY = "test_quality"

def build_judge_system_prompt() -> str: ...
def build_judge_user_prompt(*, question_artifact: dict, source_sections: list[dict], taxonomy: dict) -> str: ...

# app/evaluation/schema.py
class DimensionEvaluation(BaseModel):
    dimension: JudgeDimensionId
    score: int | None = Field(default=None, ge=1, le=5)
    applicable: bool = True
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    issues: list[str] = Field(default_factory=list)

class JudgeModelResponse(BaseModel):
    """Structured LLM output only (no provenance / status)."""
    dimensions: list[DimensionEvaluation] = Field(min_length=1)

class PedagogicalEvalStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ERROR = "error"

class AdvisoryStatus(StrEnum):
    STRONG = "strong"
    ADEQUATE = "adequate"
    WEAK = "weak"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"
    ERROR = "error"

class PedagogicalEvaluation(BaseModel):
    question_id: int | None = None
    status: PedagogicalEvalStatus
    skip_reason: str | None = None
    error_detail: str | None = None
    overall_advisory_score: float | None = None
    overall_advisory_status: AdvisoryStatus
    dimensions: list[DimensionEvaluation] = Field(default_factory=list)
    judge_model: str | None = None
    rubric_version: str = RUBRIC_VERSION
    created_at: datetime = Field(default_factory=...)

def mean_applicable_score(dimensions: list[DimensionEvaluation]) -> float | None: ...
def derive_advisory_status(
    *,
    status: PedagogicalEvalStatus,
    dimensions: list[DimensionEvaluation],
    overall_score: float | None,
) -> AdvisoryStatus: ...
def evaluation_from_judge_response(
    response: JudgeModelResponse,
    *,
    question_id: int | None,
    judge_model: str,
) -> PedagogicalEvaluation: ...
def skipped_evaluation(*, question_id: int | None, reason: str = "deterministic_failed") -> PedagogicalEvaluation: ...
def error_evaluation(*, question_id: int | None, detail: str, judge_model: str | None) -> PedagogicalEvaluation: ...

# app/evaluation/service.py
JUDGE_MAX_ATTEMPTS = 3

class PedagogicalJudge:
    def __init__(self, session: Session, *, client: StructuredLLMClient | None = None) -> None: ...
    def evaluate(self, question: Question) -> PedagogicalEvaluation:
        """Run the LLM judge. Caller must only invoke when deterministic checks passed."""

# app/generation/service.py (orchestration fragment)
report = validator.validate(Question.model_validate(row))
row.validation_report_json = report.model_dump_json()
row.status = report.resulting_status()
if report.passed:
    row.pedagogical_eval_json = self._judge.evaluate(Question.model_validate(row)).model_dump_json()
else:
    row.pedagogical_eval_json = skipped_evaluation(question_id=row.id).model_dump_json()
```

---

### Task 1: Schema, rubric constants, summary helpers

**Files:**
- Create: `app/evaluation/rubric.py`
- Create: `app/evaluation/schema.py`
- Create: `app/evaluation/__init__.py`
- Test: `tests/test_evaluation_schema.py`

**Interfaces:**
- Consumes: none
- Produces: `RUBRIC_VERSION`, `JudgeDimensionId`, `DimensionEvaluation`, `JudgeModelResponse`, `PedagogicalEvaluation`, `skipped_evaluation`, `error_evaluation`, `evaluation_from_judge_response`, `mean_applicable_score`, `derive_advisory_status`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluation_schema.py`:

```python
"""Pedagogical evaluation schema and advisory summary helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evaluation.rubric import RUBRIC_VERSION, JudgeDimensionId
from app.evaluation.schema import (
    AdvisoryStatus,
    DimensionEvaluation,
    JudgeModelResponse,
    PedagogicalEvalStatus,
    derive_advisory_status,
    error_evaluation,
    evaluation_from_judge_response,
    mean_applicable_score,
    skipped_evaluation,
)


def _dim(
    dimension: JudgeDimensionId,
    *,
    score: int | None,
    applicable: bool = True,
    confidence: float = 0.9,
) -> DimensionEvaluation:
    return DimensionEvaluation(
        dimension=dimension,
        score=score,
        applicable=applicable,
        confidence=confidence,
        rationale="ok",
        issues=[],
    )


def test_rubric_version_locked() -> None:
    assert RUBRIC_VERSION == "pedagogical-judge@1"


def test_dimension_score_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        DimensionEvaluation(
            dimension=JudgeDimensionId.CLARITY,
            score=6,
            applicable=True,
            confidence=0.5,
            rationale="too high",
        )


def test_mean_ignores_non_applicable() -> None:
    dims = [
        _dim(JudgeDimensionId.CLARITY, score=5),
        _dim(JudgeDimensionId.DISTRACTOR_QUALITY, score=None, applicable=False),
        _dim(JudgeDimensionId.SOURCE_GROUNDING, score=3),
    ]
    assert mean_applicable_score(dims) == 4.0


def test_advisory_status_bands_and_uncertain() -> None:
    strong = [_dim(JudgeDimensionId.CLARITY, score=5, confidence=0.9)]
    assert derive_advisory_status(
        status=PedagogicalEvalStatus.COMPLETED,
        dimensions=strong,
        overall_score=5.0,
    ) is AdvisoryStatus.STRONG

    uncertain = [_dim(JudgeDimensionId.CLARITY, score=5, confidence=0.2)]
    assert derive_advisory_status(
        status=PedagogicalEvalStatus.COMPLETED,
        dimensions=uncertain,
        overall_score=5.0,
    ) is AdvisoryStatus.UNCERTAIN

    assert (
        derive_advisory_status(
            status=PedagogicalEvalStatus.SKIPPED,
            dimensions=[],
            overall_score=None,
        )
        is AdvisoryStatus.SKIPPED
    )


def test_skipped_and_error_constructors() -> None:
    skipped = skipped_evaluation(question_id=3)
    assert skipped.status is PedagogicalEvalStatus.SKIPPED
    assert skipped.skip_reason == "deterministic_failed"
    assert skipped.overall_advisory_score is None
    assert skipped.rubric_version == RUBRIC_VERSION

    err = error_evaluation(question_id=3, detail="boom", judge_model="fake/m")
    assert err.status is PedagogicalEvalStatus.ERROR
    assert err.error_detail == "boom"


def test_evaluation_from_judge_response_sets_mean() -> None:
    response = JudgeModelResponse(
        dimensions=[
            _dim(JudgeDimensionId.CLARITY, score=4),
            _dim(JudgeDimensionId.SOURCE_GROUNDING, score=2),
        ]
    )
    evaluation = evaluation_from_judge_response(
        response, question_id=9, judge_model="openrouter/x"
    )
    assert evaluation.status is PedagogicalEvalStatus.COMPLETED
    assert evaluation.overall_advisory_score == 3.0
    assert evaluation.overall_advisory_status is AdvisoryStatus.ADEQUATE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_schema.py -v`

Expected: FAIL (import error — package missing)

- [ ] **Step 3: Implement rubric + schema**

`app/evaluation/rubric.py`:

```python
"""Fixed pedagogical-judge rubric identity and dimension ids."""

from __future__ import annotations

from enum import StrEnum

RUBRIC_VERSION = "pedagogical-judge@1"


class JudgeDimensionId(StrEnum):
    SOURCE_GROUNDING = "source_grounding"
    SUBTOPIC_ALIGNMENT = "subtopic_alignment"
    DIFFICULTY_ALIGNMENT = "difficulty_alignment"
    CLARITY = "clarity"
    AMBIGUITY = "ambiguity"
    PEDAGOGICAL_USEFULNESS = "pedagogical_usefulness"
    INTRO_PYTHON_APPROPRIATENESS = "intro_python_appropriateness"
    ANSWER_EXPLANATION_CONSISTENCY = "answer_explanation_consistency"
    DISTRACTOR_QUALITY = "distractor_quality"
    TEST_QUALITY = "test_quality"
```

`app/evaluation/schema.py`: implement models and helpers per Interfaces. Rules:

- `mean_applicable_score`: average of `score` where `applicable` and `score is not None`; else `None`.
- `derive_advisory_status`: `SKIPPED`/`ERROR` from eval status; else if mean confidence of applicable dims `< 0.5` → `UNCERTAIN`; else `STRONG` if mean ≥ 4, `ADEQUATE` if mean ≥ 3, else `WEAK`.
- `skipped_evaluation`: empty dimensions, `overall_advisory_score=None`, status/advisory `skipped`.
- `error_evaluation`: empty dimensions, `overall_advisory_score=None`, status/advisory `error`.
- `evaluation_from_judge_response`: compute mean + advisory; set `judge_model`, `rubric_version`.

`app/evaluation/__init__.py` docstring: advisory pedagogical evaluation; depends on `llm`, `domain`, `ingestion` retrieval, curriculum repos; does not set question validation status; does not import `adaptive` / `personalization`. Export public symbols used by generation and tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_schema.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/evaluation tests/test_evaluation_schema.py
git commit -m "feat(evaluation): add pedagogical eval schema and rubric"
```

---

### Task 2: PedagogicalJudge service (LLM call + retries)

**Files:**
- Create: `app/evaluation/service.py`
- Modify: `app/evaluation/rubric.py` (add prompt builders)
- Modify: `app/evaluation/__init__.py` (export judge)
- Test: `tests/test_evaluation_service.py`

**Interfaces:**
- Consumes: `JudgeModelResponse`, `evaluation_from_judge_response`, `error_evaluation`, `StructuredLLMClient`, `SourceRetrieval`, `CurriculumRepository`
- Produces: `PedagogicalJudge.evaluate(question) -> PedagogicalEvaluation`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluation_service.py`:

```python
"""PedagogicalJudge retries and completed/error outcomes."""

from __future__ import annotations

from typing import Any

import book_documents as docs
import pytest
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.domain.questions import Question
from app.errors import LLMRequestError, MalformedModelOutputError
from app.evaluation.rubric import JudgeDimensionId
from app.evaluation.schema import (
    DimensionEvaluation,
    JudgeModelResponse,
    PedagogicalEvalStatus,
)
from app.evaluation.service import JUDGE_MAX_ATTEMPTS, PedagogicalJudge
from app.ingestion import BookImportService


def _all_dims() -> list[DimensionEvaluation]:
    return [
        DimensionEvaluation(
            dimension=dim,
            score=4 if dim is not JudgeDimensionId.DISTRACTOR_QUALITY else None,
            applicable=dim is not JudgeDimensionId.DISTRACTOR_QUALITY,
            confidence=0.8,
            rationale="fine",
            issues=[],
        )
        for dim in JudgeDimensionId
    ]


class GoodJudgeClient:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def description(self) -> str:
        return "fake/judge-model"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        self.calls += 1
        assert response_model is JudgeModelResponse
        assert "print" in prompt.lower() or "prompt" in prompt.lower()
        return JudgeModelResponse(dimensions=_all_dims())


class FlakyJudgeClient:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.calls = 0

    @property
    def description(self) -> str:
        return "fake/flaky-judge"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt, response_model
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise MalformedModelOutputError("bad json", detail="nope")
        return JudgeModelResponse(dimensions=_all_dims())


class AlwaysBrokenJudgeClient:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def description(self) -> str:
        return "fake/broken-judge"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt, response_model
        self.calls += 1
        raise LLMRequestError("down", detail="503")


def _seed_question(session: Session, settings: Any) -> Question:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Output","subtopics":[{"name":"Printing","description":"print()"}]}]}'
        ),
    )
    session.commit()
    section = book.chapters[0].sections[0]
    return Question(
        id=1,
        curriculum_version_id=version.id,
        topic_id=version.topics[0].id,
        subtopic_id=version.topics[0].subtopics[0].id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        prompt="What is printed?",
        reference_solution="3",
        content_json=(
            '{"prompt":"What is printed?","code":"print(3)","expected_output":"3",'
            f'"sources":[{{"section_id":{section.id},"citation":"x"}}]}}'
        ),
        spec_json=(
            '{"curriculum_version_id":'
            + str(version.id)
            + ',"topic_id":'
            + str(version.topics[0].id)
            + ',"subtopic_ids":['
            + str(version.topics[0].subtopics[0].id)
            + '],"question_type":"output_prediction","difficulty":"easy",'
            + f'"source_section_ids":[{section.id}]}}'
        ),
    )


def test_judge_returns_completed(session: Session, settings: Any) -> None:
    client = GoodJudgeClient()
    question = _seed_question(session, settings)
    result = PedagogicalJudge(session, client=client).evaluate(question)
    assert result.status is PedagogicalEvalStatus.COMPLETED
    assert client.calls == 1
    assert result.judge_model == "fake/judge-model"
    assert result.overall_advisory_score is not None


def test_judge_retries_then_succeeds(session: Session, settings: Any) -> None:
    client = FlakyJudgeClient(failures_before_success=2)
    result = PedagogicalJudge(session, client=client).evaluate(_seed_question(session, settings))
    assert result.status is PedagogicalEvalStatus.COMPLETED
    assert client.calls == 3


def test_judge_returns_error_after_max_attempts(session: Session, settings: Any) -> None:
    client = AlwaysBrokenJudgeClient()
    result = PedagogicalJudge(session, client=client).evaluate(_seed_question(session, settings))
    assert result.status is PedagogicalEvalStatus.ERROR
    assert client.calls == JUDGE_MAX_ATTEMPTS
    assert result.error_detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_service.py -v`

Expected: FAIL (`PedagogicalJudge` missing)

- [ ] **Step 3: Implement prompt builders + PedagogicalJudge**

In `rubric.py`, add short system prompt text listing dimensions and rules (1–5, `applicable=false` + null score for N/A, concise rationale/issues, deterministic already passed — do not re-check execution).

`build_judge_user_prompt` should embed JSON for:

- `question_artifact`: prompt, question_type, difficulty, reference_solution, tests, content (parsed `content_json` dict)
- `source_sections`: `[{section_id, citation, text}]` only for ids on the question
- `taxonomy`: `{topic_name, subtopic_name, subtopic_description}`

In `service.py`:

```python
JUDGE_MAX_ATTEMPTS = 3

class PedagogicalJudge:
    def __init__(self, session: Session, *, client: StructuredLLMClient | None = None) -> None:
        self._session = session
        self._client = client or get_structured_client()
        self._retrieval = SourceRetrieval(session)
        self._curriculum = CurriculumRepository(session)

    def evaluate(self, question: Question) -> PedagogicalEvaluation:
        artifact, sources, taxonomy = self._load_context(question)
        system = build_judge_system_prompt()
        prompt = build_judge_user_prompt(
            question_artifact=artifact, source_sections=sources, taxonomy=taxonomy
        )
        last_detail = "unknown"
        for _ in range(JUDGE_MAX_ATTEMPTS):
            try:
                response = self._client.complete_structured(
                    system=system,
                    prompt=prompt,
                    response_model=JudgeModelResponse,
                )
                return evaluation_from_judge_response(
                    response,
                    question_id=question.id,
                    judge_model=self._client.description,
                )
            except (LLMRequestError, MalformedModelOutputError) as exc:
                last_detail = str(exc.detail or exc)[:400]
        return error_evaluation(
            question_id=question.id,
            detail=last_detail,
            judge_model=self._client.description,
        )
```

Load section ids from `spec_json.source_section_ids` and/or `content_json.sources`. Use `SourceRetrieval.section_source` / section text APIs already in the codebase. Load topic/subtopic names + `description` via `CurriculumRepository.get_with_tree`.

Do **not** implement skip logic here.

- [ ] **Step 4: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/evaluation tests/test_evaluation_service.py
git commit -m "feat(evaluation): add PedagogicalJudge with retries"
```

---

### Task 3: Persist `pedagogical_eval_json`

**Files:**
- Modify: `app/domain/questions.py` — add field on `Question`
- Modify: `app/persistence/models.py` — add column on `QuestionRow`
- Modify: `app/generation/service.py` — `_row_from_question` copy field
- Test: `tests/test_persistence.py` (extend existing question round-trip)

**Interfaces:**
- Consumes: none new
- Produces: `Question.pedagogical_eval_json: str | None`, `QuestionRow.pedagogical_eval_json`

- [ ] **Step 1: Write/extend failing persistence assertion**

In `tests/test_persistence.py`, wherever a `QuestionRow` is created with `validation_report_json`, also set `pedagogical_eval_json='{"status":"skipped"}'` and assert it reloads.

- [ ] **Step 2: Run the targeted test — expect FAIL** (`no such column` or attribute missing)

- [ ] **Step 3: Add the field/column**

```python
# domain Question
pedagogical_eval_json: str | None = None

# QuestionRow after validation_report_json
pedagogical_eval_json: Mapped[str | None] = mapped_column(Text, default=None)
```

Copy through `_row_from_question`.

- [ ] **Step 4: Run persistence tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/domain/questions.py app/persistence/models.py app/generation/service.py tests/test_persistence.py
git commit -m "feat(persistence): store pedagogical_eval_json on questions"
```

---

### Task 4: Wire GenerationService orchestration + FakeClient dispatch

**Files:**
- Modify: `app/generation/service.py`
- Modify: `tests/test_validation_service.py` (FakeClient dispatch)
- Modify: other generation FakeClients that hit the pass path (`tests/test_generation_pages.py`, `tests/test_generation_base.py` if they go through `GenerationService` validate+judge)
- Test: `tests/test_evaluation_generation.py`

**Interfaces:**
- Consumes: `PedagogicalJudge`, `skipped_evaluation`
- Produces: every generated row has `pedagogical_eval_json`; status still deterministic-only

- [ ] **Step 1: Write failing orchestration tests**

Create `tests/test_evaluation_generation.py`:

```python
"""GenerationService owns skip vs judge; judge cannot override deterministic fail."""

from __future__ import annotations

from typing import Any

import book_documents as docs
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionStatus, QuestionType
from app.evaluation.rubric import JudgeDimensionId
from app.evaluation.schema import (
    DimensionEvaluation,
    JudgeModelResponse,
    PedagogicalEvalStatus,
    PedagogicalEvaluation,
)
from app.generation.schemas import OutputPredictionDraft
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository


def _dims() -> list[DimensionEvaluation]:
    return [
        DimensionEvaluation(
            dimension=d,
            score=5,
            applicable=True,
            confidence=0.9,
            rationale="great",
            issues=[],
        )
        for d in JudgeDimensionId
        if d is not JudgeDimensionId.DISTRACTOR_QUALITY
    ] + [
        DimensionEvaluation(
            dimension=JudgeDimensionId.DISTRACTOR_QUALITY,
            score=None,
            applicable=False,
            confidence=1.0,
            rationale="n/a",
            issues=[],
        )
    ]


class RecordingClient:
    """Generation draft + glowing judge response; counts judge calls."""

    def __init__(self) -> None:
        self.judge_calls = 0

    @property
    def description(self) -> str:
        return "fake/recording"

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt
        if response_model is JudgeModelResponse:
            self.judge_calls += 1
            return JudgeModelResponse(dimensions=_dims())
        return OutputPredictionDraft(
            prompt="What is printed?",
            code="print(3)",
            expected_output="3",
            explanation="prints 3",
        )


class FailingDeterministicClient(RecordingClient):
    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        del system, prompt
        if response_model is JudgeModelResponse:
            self.judge_calls += 1
            return JudgeModelResponse(dimensions=_dims())
        return OutputPredictionDraft(
            prompt="What is printed?",
            code="print(4)",
            expected_output="3",
            explanation="wrong on purpose",
        )


def _seed(session: Session, settings: Any) -> tuple[Any, Any, Any, int]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Python","topics":['
            b'{"name":"Output","subtopics":[{"name":"Printing"}]}]}'
        ),
    )
    session.commit()
    return version, version.topics[0], version.topics[0].subtopics[0], book.chapters[0].sections[0].id


def test_pass_runs_judge_and_stores_completed(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = RecordingClient()
    row = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )[0]
    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_PASSED
    evaluation = PedagogicalEvaluation.model_validate_json(loaded.pedagogical_eval_json)
    assert evaluation.status is PedagogicalEvalStatus.COMPLETED
    assert client.judge_calls == 1


def test_fail_skips_judge_and_stores_skipped(session: Session, settings: Any) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = FailingDeterministicClient()
    row = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_id=subtopic.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )[0]
    loaded = QuestionRepository(session).get(row.id)
    assert loaded.status is QuestionStatus.VALIDATION_FAILED
    evaluation = PedagogicalEvaluation.model_validate_json(loaded.pedagogical_eval_json)
    assert evaluation.status is PedagogicalEvalStatus.SKIPPED
    assert client.judge_calls == 0
```

- [ ] **Step 2: Run — expect FAIL** (no pedagogical_eval_json / judge not wired)

- [ ] **Step 3: Wire GenerationService**

```python
from app.evaluation import PedagogicalJudge, skipped_evaluation

class GenerationService:
    def __init__(self, session: Session, *, client: StructuredLLMClient | None = None) -> None:
        ...
        self._judge = PedagogicalJudge(session, client=client)

    def generate_for_sections(...):
        ...
        report = validator.validate(Question.model_validate(row))
        row.validation_report_json = report.model_dump_json()
        row.status = report.resulting_status()
        if report.passed:
            row.pedagogical_eval_json = self._judge.evaluate(
                Question.model_validate(row)
            ).model_dump_json()
        else:
            row.pedagogical_eval_json = skipped_evaluation(question_id=row.id).model_dump_json()
```

Update every `FakeClient.complete_structured` used with `GenerationService` on the **pass** path to return `JudgeModelResponse` when `response_model is JudgeModelResponse` (same pattern as `RecordingClient`). Minimum files: `tests/test_validation_service.py`, `tests/test_generation_pages.py`. Keep generation drafts unchanged for other `response_model` values.

- [ ] **Step 4: Run**

`.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_generation.py tests/test_validation_service.py tests/test_generation_pages.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/generation/service.py tests/test_evaluation_generation.py tests/test_validation_service.py tests/test_generation_pages.py
git commit -m "feat(generation): run advisory pedagogical judge after validation"
```

---

### Task 5: Question detail UI — two panels

**Files:**
- Modify: `app/web/routes/pages.py` (`question_detail`)
- Modify: `app/web/templates/question_detail.html`
- Modify: `app/web/static/css/app.css` (minimal)
- Test: `tests/test_evaluation_pages.py`

**Interfaces:**
- Consumes: `PedagogicalEvaluation`
- Produces: template vars `pedagogical_eval`, keep `validation_checks` / `validation_passed`

- [ ] **Step 1: Write UI test**

```python
"""Question detail distinguishes deterministic checks from LLM evaluation."""

from __future__ import annotations

# seed book+taxonomy, monkeypatch GenerationService with RecordingClient from Task 4
# POST generate (or insert row with both JSON blobs)
# GET /questions/{id}
# assert b"Deterministic checks" in body
# assert b"LLM pedagogical evaluation" in body
# for completed: assert dimension label / score present
# for skipped fixture: assert b"skipped" and reason text
```

Cover at least one completed and one skipped page (can insert rows directly via repository to avoid full generate if simpler).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

In `question_detail`:

```python
pedagogical_eval = None
if question.pedagogical_eval_json:
    with suppress(ValidationError):
        pedagogical_eval = PedagogicalEvaluation.model_validate_json(
            question.pedagogical_eval_json
        )
```

Template structure:

```html
<section class="panel ...">
  <h2>Deterministic checks</h2>
  ... existing checklist ...
</section>

<section class="panel">
  <h2>LLM pedagogical evaluation</h2>
  {% if pedagogical_eval %}
    <p>Status: {{ pedagogical_eval.status }} · advisory summary: ...</p>
    <p class="meta">{{ pedagogical_eval.judge_model }} · {{ pedagogical_eval.rubric_version }} · {{ pedagogical_eval.created_at }}</p>
    {% if pedagogical_eval.status == "completed" %}
      <ul class="checklist">
        {% for dim in pedagogical_eval.dimensions %}
          <li>
            {% if not dim.applicable %}—{% elif dim.score and dim.score >= 4 %}✓{% elif dim.score and dim.score >= 3 %}⚠{% else %}✗{% endif %}
            {{ dim.dimension }}:
            {% if dim.applicable %}{{ dim.score }}/5{% else %}n/a{% endif %}
            <span class="rationale">{{ dim.rationale }}</span>
            ...
          </li>
        {% endfor %}
      </ul>
      <p class="summary">Overall advisory mean: {{ pedagogical_eval.overall_advisory_score }} ({{ pedagogical_eval.overall_advisory_status }}) — summary only</p>
    {% elif pedagogical_eval.status == "skipped" %}
      <p>Skipped: {{ pedagogical_eval.skip_reason }}</p>
    {% else %}
      <p>Error: {{ pedagogical_eval.error_detail }}</p>
    {% endif %}
  {% else %}
    <p class="empty">Pedagogical evaluation has not been recorded.</p>
  {% endif %}
</section>
```

Rename former “Automatic Checks” heading to **Deterministic checks**.

- [ ] **Step 4: Run UI tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/pages.py app/web/templates/question_detail.html app/web/static/css/app.css tests/test_evaluation_pages.py
git commit -m "feat(web): show deterministic checks and LLM pedagogical evaluation"
```

---

### Task 6: ADR-024, module map, boundary test

**Files:**
- Modify: `docs/DECISIONS.md` — ADR-024
- Modify: `CLAUDE.md` — module map line for `evaluation/`
- Modify: `tests/test_boundaries.py` — add `"app.evaluation"` to `BOUNDARY_MODULES`

- [ ] **Step 1: Write boundary expectation**

Ensure `BOUNDARY_MODULES` includes `"app.evaluation"` so the existing parametrized docstring test covers it.

- [ ] **Step 2: Run `tests/test_boundaries.py` — may FAIL until package docstring is solid**

- [ ] **Step 3: Document**

ADR-024 text (accepted):

- Advisory structured LLM pedagogical judge after deterministic validation.
- `GenerationService` owns skip; judge never overrides deterministic failure.
- Stored in `pedagogical_eval_json` with model, rubric version, timestamp.
- Overall score is unweighted mean of applicable dimensions; dimensions primary.
- `app/validation` remains LLM-free.

CLAUDE.md module map: `evaluation/ | Advisory structured LLM pedagogical evaluation (IMPLEMENTED)`.

- [ ] **Step 4: Run boundaries + ruff**

- [ ] **Step 5: Commit**

```bash
git add docs/DECISIONS.md CLAUDE.md tests/test_boundaries.py
git commit -m "docs: record ADR-024 for advisory pedagogical judge"
```

---

### Task 7: Full verification + completion report

- [ ] **Step 1: Run the full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Expected: all pass. Fix any fallout (FakeClients, schema drift messages in docs).

- [ ] **Step 2: Manual UI smoke (optional if LLM configured)**

1. Ensure book JSON + taxonomy JSON imported.
2. Generate a valid output-prediction question → detail shows Deterministic ✓ and LLM dimensions.
3. Generate/force an invalid executable question → Deterministic ✗, LLM panel `skipped` / `deterministic_failed`.

- [ ] **Step 3: Write completion report in the PR/chat** covering:

- Judge rubric (`pedagogical-judge@1` + dimension list)
- Structured schema summary
- Precedence logic (GenerationService skip vs judge)
- Files changed
- Tests/results
- UI test flow

- [ ] **Step 4: Final commit only if Step 1 required fixes**

---

## Self-review (plan vs spec)

| Spec requirement | Task |
| ---------------- | ---- |
| Separate from deterministic validation | Tasks 1–2 package; Task 4 orchestration; Task 5 UI |
| Skip when deterministic fails; store skipped | Task 4 |
| Judge not called on fail; GenerationService owns skip | Task 4 |
| 3 attempts then error; status stays passed | Task 2 |
| Dimensions 1–5 + confidence + rationale + issues | Task 1 |
| Unweighted mean summary; dimensions primary | Task 1 + Task 5 |
| Full question artifact + relevant source/taxonomy only | Task 2 prompts/context |
| Persist with model/rubric/timestamp | Tasks 1, 3 |
| Mock judge; malformed; no override | Tasks 1, 2, 4 |
| UI two panels + rationales | Task 5 |
| ADR | Task 6 |

No TBD/placeholder steps. Types consistent: `JudgeModelResponse` / `PedagogicalEvaluation` / `PedagogicalJudge.evaluate` used the same way across tasks.
