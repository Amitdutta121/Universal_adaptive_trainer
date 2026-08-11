# Professor Feedback Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a professor approve, reject, or edit a generated question from the detail page, persist immutable review records (with structured reasons and full edit snapshots), and show a feedback dashboard — without ever overwriting `original_*`.

**Architecture:** Extend the existing `app/feedback` boundary. `submit_review` loads the question, enforces decision rules in the service, updates current question fields + status on Edit/Approve/Reject, and appends a `ProfessorReviewRow`. Jinja form POSTs to `/questions/{id}/review`. Dashboard aggregates come from the review repository.

**Tech Stack:** Pydantic v2, SQLAlchemy 2.0, FastAPI `Form`, Jinja2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-11-professor-feedback-design.md`

## Global Constraints

- Professor feedback is authoritative for preference (ADR-006); do not touch `app/personalization` beyond reading reviews later.
- Generated originals are never overwritten (ADR-003); only `apply_professor_edit` / equivalent field updates on current columns.
- Reviews are append-only; never UPDATE an existing review row.
- Status mapping: Approve → `APPROVED`; Reject → `REJECTED`; Edit → `APPROVED`. Do **not** add `QuestionStatus.EDITED`.
- Reasons required (≥1) for Reject; optional for Edit; empty for Approve.
- On Edit, store **all three** `edited_*` strings on the review; derive `changed_fields_json` in the service (never from the form).
- Diff-from-current check lives in the service, not in a cross-row Pydantic validator.
- Edit surface: `prompt`, `reference_solution`, `tests` only (not `content_json`).
- No auth → `professor_id` always `None` this milestone.
- No post-edit re-validation or re-judge.
- Server-rendered forms only (ADR-007); no SPA / no JS build.
- Book/taxonomy remain structured JSON uploads; do not touch ingestion.
- Python 3.12, `from __future__ import annotations`, ruff line length 100.
- Tests use temp SQLite via fixtures; never write developer `data/`.
- Existing local DBs missing new columns fail `verify_schema` and must be deleted/recreated (ADR-008).
- Commands: `.\.venv\Scripts\python.exe -m pytest <target> -v` then full pytest + ruff before commit.
- Do not edit `.cursor/plans/` files.

## File structure

| Path | Responsibility |
| ---- | -------------- |
| `app/domain/enums.py` | Add `RejectionReason` StrEnum |
| `app/domain/feedback.py` | Extend `ProfessorReview`; JSON encode/decode helpers; reason labels |
| `app/feedback/service.py` | `submit_review` write path |
| `app/feedback/__init__.py` | Re-export `submit_review`; keep/retire thin `record_review` |
| `app/persistence/models.py` | New columns on `ProfessorReviewRow` |
| `app/persistence/repositories.py` | Decision counts + reason distribution |
| `app/web/routes/pages.py` | Spec on detail; `POST /questions/{id}/review`; dashboard context |
| `app/web/templates/question_detail.html` | Spec panel + review form |
| `app/web/templates/feedback.html` | Counts, reason distribution, reasons column |
| `tests/test_feedback_service.py` | Service rules + original preservation |
| `tests/test_feedback_pages.py` | HTTP approve/reject/edit + dashboard |
| `tests/test_persistence.py` | Update callers of old `record_review` |

## Interfaces (locked)

```python
# app/domain/enums.py
class RejectionReason(StrEnum):
    TECHNICALLY_INCORRECT = "technically_incorrect"
    INCORRECT_ANSWER = "incorrect_answer"
    INCORRECT_TESTS = "incorrect_tests"
    NOT_GROUNDED_IN_SOURCE = "not_grounded_in_source"
    WRONG_TOPIC_SUBTOPIC = "wrong_topic_subtopic"
    TOO_EASY = "too_easy"
    TOO_DIFFICULT = "too_difficult"
    AMBIGUOUS = "ambiguous"
    POOR_WORDING = "poor_wording"
    POOR_DISTRACTORS = "poor_distractors"
    POOR_TESTS = "poor_tests"
    NOT_PEDAGOGICALLY_USEFUL = "not_pedagogically_useful"
    TOO_SIMILAR_REPETITIVE = "too_similar_repetitive"
    OTHER = "other"

# app/domain/feedback.py
REJECTION_REASON_LABELS: dict[RejectionReason, str]  # human labels for UI

def encode_reasons(reasons: list[RejectionReason]) -> str: ...
def decode_reasons(raw: str | None) -> list[RejectionReason]: ...
def encode_changed_fields(fields: list[str]) -> str: ...
def decode_changed_fields(raw: str | None) -> list[str]: ...

class ProfessorReview(BaseModel):
    id: int | None = None
    question_id: int | None = None
    decision: ReviewDecision
    reasons: list[RejectionReason] = Field(default_factory=list)
    comment: str | None = None
    edited_prompt: str | None = None
    edited_reference_solution: str | None = None
    edited_tests: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    professor_id: int | None = None
    reviewed_generator_name: str | None = None
    reviewed_generator_version: str | None = None
    created_at: datetime = Field(default_factory=_now)

# app/feedback/service.py
def submit_review(
    session: Session,
    *,
    question_id: int,
    decision: ReviewDecision,
    reasons: list[RejectionReason] | None = None,
    comment: str | None = None,
    prompt: str | None = None,
    reference_solution: str | None = None,
    tests: str | None = None,
    professor_id: int | None = None,
) -> ProfessorReviewRow: ...

# app/persistence/repositories.py  (ProfessorReviewRepository)
def count_by_decision(self) -> dict[str, int]: ...
def reason_counts(self) -> dict[str, int]: ...
```

---

### Task 1: RejectionReason enum + domain review model

**Files:**
- Modify: `app/domain/enums.py`
- Modify: `app/domain/feedback.py`
- Modify: `app/domain/__init__.py` (export `RejectionReason`)
- Test: `tests/test_feedback_domain.py`

**Interfaces:**
- Consumes: existing `ReviewDecision`
- Produces: `RejectionReason`, `REJECTION_REASON_LABELS`, encode/decode helpers, extended `ProfessorReview`

- [ ] **Step 1: Write the failing domain test**

Create `tests/test_feedback_domain.py`:

```python
from __future__ import annotations

from app.domain.enums import RejectionReason, ReviewDecision
from app.domain.feedback import (
    REJECTION_REASON_LABELS,
    ProfessorReview,
    decode_reasons,
    encode_reasons,
)


def test_all_rejection_reasons_have_labels() -> None:
    assert set(REJECTION_REASON_LABELS) == set(RejectionReason)
    assert REJECTION_REASON_LABELS[RejectionReason.OTHER] == "Other"


def test_encode_decode_reasons_round_trip() -> None:
    reasons = [RejectionReason.TOO_EASY, RejectionReason.POOR_WORDING]
    assert decode_reasons(encode_reasons(reasons)) == reasons


def test_decode_reasons_empty() -> None:
    assert decode_reasons(None) == []
    assert decode_reasons("[]") == []


def test_professor_review_defaults() -> None:
    review = ProfessorReview(decision=ReviewDecision.APPROVE)
    assert review.reasons == []
    assert review.edited_prompt is None
    assert review.changed_fields == []
    assert review.professor_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_domain.py -v`  
Expected: FAIL (import / missing `RejectionReason`)

- [ ] **Step 3: Implement enum + domain helpers**

Add to `app/domain/enums.py` after `ReviewDecision`:

```python
class RejectionReason(StrEnum):
    """Structured professor rationale for reject or edit decisions."""

    TECHNICALLY_INCORRECT = "technically_incorrect"
    INCORRECT_ANSWER = "incorrect_answer"
    INCORRECT_TESTS = "incorrect_tests"
    NOT_GROUNDED_IN_SOURCE = "not_grounded_in_source"
    WRONG_TOPIC_SUBTOPIC = "wrong_topic_subtopic"
    TOO_EASY = "too_easy"
    TOO_DIFFICULT = "too_difficult"
    AMBIGUOUS = "ambiguous"
    POOR_WORDING = "poor_wording"
    POOR_DISTRACTORS = "poor_distractors"
    POOR_TESTS = "poor_tests"
    NOT_PEDAGOGICALLY_USEFUL = "not_pedagogically_useful"
    TOO_SIMILAR_REPETITIVE = "too_similar_repetitive"
    OTHER = "other"
```

Replace `app/domain/feedback.py` contents with:

```python
"""Professor feedback entities.

Professor reviews are the authority for professor preference: personalization and
later generator optimization read from these records and never from inferred
signals such as student performance.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RejectionReason, ReviewDecision

REJECTION_REASON_LABELS: dict[RejectionReason, str] = {
    RejectionReason.TECHNICALLY_INCORRECT: "Technically incorrect",
    RejectionReason.INCORRECT_ANSWER: "Incorrect answer",
    RejectionReason.INCORRECT_TESTS: "Incorrect tests",
    RejectionReason.NOT_GROUNDED_IN_SOURCE: "Not grounded in source",
    RejectionReason.WRONG_TOPIC_SUBTOPIC: "Wrong topic/subtopic",
    RejectionReason.TOO_EASY: "Too easy",
    RejectionReason.TOO_DIFFICULT: "Too difficult",
    RejectionReason.AMBIGUOUS: "Ambiguous",
    RejectionReason.POOR_WORDING: "Poor wording",
    RejectionReason.POOR_DISTRACTORS: "Poor distractors",
    RejectionReason.POOR_TESTS: "Poor tests",
    RejectionReason.NOT_PEDAGOGICALLY_USEFUL: "Not pedagogically useful",
    RejectionReason.TOO_SIMILAR_REPETITIVE: "Too similar/repetitive",
    RejectionReason.OTHER: "Other",
}

_CHANGED_FIELD_NAMES = frozenset({"prompt", "reference_solution", "tests"})


def _now() -> datetime:
    return datetime.now(UTC)


def encode_reasons(reasons: list[RejectionReason]) -> str:
    return json.dumps([reason.value for reason in reasons])


def decode_reasons(raw: str | None) -> list[RejectionReason]:
    if not raw:
        return []
    values = json.loads(raw)
    return [RejectionReason(value) for value in values]


def encode_changed_fields(fields: list[str]) -> str:
    return json.dumps(fields)


def decode_changed_fields(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = json.loads(raw)
    return [str(item) for item in values if str(item) in _CHANGED_FIELD_NAMES]


class ProfessorReview(BaseModel):
    """One professor verdict on one generated question.

    Reviews are append-only: a later review of the same question is a new record,
    so the full preference history stays available for generator optimization.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    question_id: int | None = None
    decision: ReviewDecision
    reasons: list[RejectionReason] = Field(default_factory=list)
    comment: str | None = None
    edited_prompt: str | None = None
    edited_reference_solution: str | None = None
    edited_tests: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    professor_id: int | None = None
    reviewed_generator_name: str | None = None
    reviewed_generator_version: str | None = None
    created_at: datetime = Field(default_factory=_now)
```

Export `RejectionReason` from `app/domain/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_domain.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/domain/enums.py app/domain/feedback.py app/domain/__init__.py tests/test_feedback_domain.py
git commit -m "feat(feedback): add RejectionReason and extended review model"
```

---

### Task 2: Persistence columns + repository aggregates

**Files:**
- Modify: `app/persistence/models.py` (`ProfessorReviewRow`)
- Modify: `app/persistence/repositories.py` (`ProfessorReviewRepository`)
- Test: `tests/test_feedback_persistence.py`

**Interfaces:**
- Consumes: new domain fields
- Produces: ORM columns; `count_by_decision()`, `reason_counts()`

- [ ] **Step 1: Write the failing persistence test**

Create `tests/test_feedback_persistence.py`:

```python
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.domain.enums import RejectionReason, ReviewDecision
from app.domain.feedback import encode_reasons
from app.persistence.models import ProfessorReviewRow, QuestionRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository


def test_review_row_stores_reasons_and_edit_snapshot(session: Session) -> None:
    question = QuestionRepository(session).add(
        QuestionRow(prompt="Old prompt.", original_prompt="Old prompt.")
    )
    session.flush()
    review = ProfessorReviewRow(
        question_id=question.id,
        decision=ReviewDecision.EDIT,
        reasons_json=encode_reasons([RejectionReason.POOR_WORDING]),
        comment="Clarify.",
        edited_prompt="New prompt.",
        edited_reference_solution="print(1)",
        edited_tests="",
        changed_fields_json=json.dumps(["prompt"]),
        professor_id=None,
        reviewed_generator_name="base",
        reviewed_generator_version="1",
    )
    ProfessorReviewRepository(session).add(review)
    session.commit()

    loaded = ProfessorReviewRepository(session).list_recent()[0]
    assert loaded.reasons_json is not None
    assert loaded.edited_prompt == "New prompt."
    assert loaded.edited_tests == ""
    assert json.loads(loaded.changed_fields_json) == ["prompt"]


def test_count_by_decision_and_reason_counts(session: Session) -> None:
    q = QuestionRepository(session).add(
        QuestionRow(prompt="Q", original_prompt="Q")
    )
    session.flush()
    repo = ProfessorReviewRepository(session)
    repo.add(
        ProfessorReviewRow(
            question_id=q.id,
            decision=ReviewDecision.APPROVE,
            reasons_json="[]",
        )
    )
    repo.add(
        ProfessorReviewRow(
            question_id=q.id,
            decision=ReviewDecision.REJECT,
            reasons_json=encode_reasons(
                [RejectionReason.TOO_EASY, RejectionReason.AMBIGUOUS]
            ),
        )
    )
    repo.add(
        ProfessorReviewRow(
            question_id=q.id,
            decision=ReviewDecision.EDIT,
            reasons_json=encode_reasons([RejectionReason.TOO_EASY]),
            edited_prompt="Q2",
            edited_reference_solution="",
            edited_tests="",
            changed_fields_json='["prompt"]',
        )
    )
    session.commit()

    assert repo.count_by_decision() == {"approve": 1, "reject": 1, "edit": 1}
    assert repo.reason_counts() == {"too_easy": 2, "ambiguous": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_persistence.py -v`  
Expected: FAIL (unknown column / missing methods)

- [ ] **Step 3: Extend `ProfessorReviewRow` and repository**

Update `ProfessorReviewRow` in `app/persistence/models.py`:

```python
class ProfessorReviewRow(TimestampMixin, Base):
    """Append-only professor verdict on a question."""

    __tablename__ = "professor_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    decision: Mapped[ReviewDecision] = mapped_column(String(16))
    reasons_json: Mapped[str | None] = mapped_column(Text, default="[]")
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    edited_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    edited_reference_solution: Mapped[str | None] = mapped_column(Text, default=None)
    edited_tests: Mapped[str | None] = mapped_column(Text, default=None)
    changed_fields_json: Mapped[str | None] = mapped_column(Text, default=None)
    professor_id: Mapped[int | None] = mapped_column(Integer, default=None)
    reviewed_generator_name: Mapped[str | None] = mapped_column(String(200), default=None)
    reviewed_generator_version: Mapped[str | None] = mapped_column(String(50), default=None)

    question: Mapped[QuestionRow] = relationship(back_populates="reviews")
```

Ensure `Integer` is imported from `sqlalchemy` if not already.

Extend `ProfessorReviewRepository`:

```python
def count_by_decision(self) -> dict[str, int]:
    stmt = select(ProfessorReviewRow.decision, func.count()).group_by(
        ProfessorReviewRow.decision
    )
    return {str(decision): count for decision, count in self._session.execute(stmt)}

def reason_counts(self) -> dict[str, int]:
    """Count structured reasons across all reviews (Python-side JSON parse)."""
    from app.domain.feedback import decode_reasons

    counts: dict[str, int] = {}
    rows = self._session.scalars(select(ProfessorReviewRow.reasons_json)).all()
    for raw in rows:
        for reason in decode_reasons(raw):
            key = reason.value
            counts[key] = counts.get(key, 0) + 1
    return counts
```

- [ ] **Step 4: Run persistence tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_persistence.py -v`  
Expected: PASS  
Note: delete outdated local `data/adaptive_trainer.db` if `verify_schema` fails when running the app later.

- [ ] **Step 5: Commit**

```bash
git add app/persistence/models.py app/persistence/repositories.py tests/test_feedback_persistence.py
git commit -m "feat(feedback): persist review reasons and edit snapshots"
```

---

### Task 3: `submit_review` service (core write path)

**Files:**
- Create: `app/feedback/service.py`
- Modify: `app/feedback/__init__.py`
- Test: `tests/test_feedback_service.py`
- Modify: `tests/test_persistence.py` (replace `record_review` usages)

**Interfaces:**
- Consumes: `QuestionRepository`, `ProfessorReviewRepository`, `apply_professor_edit` semantics
- Produces: `submit_review(...)` → `ProfessorReviewRow`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_feedback_service.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import RejectionReason, ReviewDecision, QuestionStatus
from app.domain.feedback import decode_changed_fields, decode_reasons
from app.errors import DomainRuleError, NotFoundError
from app.feedback import submit_review
from app.persistence.models import QuestionRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository


def _question(session: Session, **overrides: object) -> QuestionRow:
    values = {
        "prompt": "Write a loop.",
        "original_prompt": "Write a loop.",
        "reference_solution": "pass",
        "original_reference_solution": "pass",
        "tests": "assert True",
        "original_tests": "assert True",
        "generator_name": "base-gen",
        "generator_version": "1",
        "status": QuestionStatus.VALIDATION_PASSED,
    }
    values.update(overrides)
    row = QuestionRepository(session).add(QuestionRow(**values))
    session.commit()
    assert row.id is not None
    return row


def test_approve_sets_status_and_empty_reasons(session: Session) -> None:
    q = _question(session)
    review = submit_review(
        session, question_id=q.id, decision=ReviewDecision.APPROVE, comment="Good"
    )
    session.commit()
    session.refresh(q)
    assert q.status == QuestionStatus.APPROVED
    assert decode_reasons(review.reasons_json) == []
    assert review.edited_prompt is None
    assert review.comment == "Good"
    assert review.reviewed_generator_name == "base-gen"


def test_reject_requires_reasons_and_stores_many(session: Session) -> None:
    q = _question(session)
    with pytest.raises(DomainRuleError):
        submit_review(session, question_id=q.id, decision=ReviewDecision.REJECT)

    review = submit_review(
        session,
        question_id=q.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY, RejectionReason.OTHER],
        comment="custom note",
    )
    session.commit()
    session.refresh(q)
    assert q.status == QuestionStatus.REJECTED
    assert decode_reasons(review.reasons_json) == [
        RejectionReason.TOO_EASY,
        RejectionReason.OTHER,
    ]
    assert review.comment == "custom note"


def test_edit_preserves_originals_and_snapshots_all_fields(session: Session) -> None:
    q = _question(session)
    review = submit_review(
        session,
        question_id=q.id,
        decision=ReviewDecision.EDIT,
        reasons=[RejectionReason.POOR_WORDING],
        prompt="Write a for-loop over a list.",
        reference_solution="pass",
        tests="assert True",
    )
    session.commit()
    session.refresh(q)
    assert q.status == QuestionStatus.APPROVED
    assert q.prompt == "Write a for-loop over a list."
    assert q.original_prompt == "Write a loop."
    assert q.original_reference_solution == "pass"
    assert q.original_tests == "assert True"
    assert review.edited_prompt == "Write a for-loop over a list."
    assert review.edited_reference_solution == "pass"
    assert review.edited_tests == "assert True"
    assert decode_changed_fields(review.changed_fields_json) == ["prompt"]


def test_edit_with_no_changes_errors(session: Session) -> None:
    q = _question(session)
    with pytest.raises(DomainRuleError):
        submit_review(
            session,
            question_id=q.id,
            decision=ReviewDecision.EDIT,
            prompt="Write a loop.",
            reference_solution="pass",
            tests="assert True",
        )


def test_reviews_remain_append_only(session: Session) -> None:
    q = _question(session)
    first = submit_review(session, question_id=q.id, decision=ReviewDecision.APPROVE)
    second = submit_review(
        session,
        question_id=q.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.AMBIGUOUS],
    )
    session.commit()
    assert first.id != second.id
    assert ProfessorReviewRepository(session).count() == 2


def test_unknown_question(session: Session) -> None:
    with pytest.raises(NotFoundError):
        submit_review(session, question_id=999, decision=ReviewDecision.APPROVE)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_service.py -v`  
Expected: FAIL (`submit_review` missing)

- [ ] **Step 3: Implement `submit_review`**

Create `app/feedback/service.py`:

```python
"""Write path for professor approve / reject / edit reviews."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus, RejectionReason, ReviewDecision
from app.domain.feedback import encode_changed_fields, encode_reasons
from app.errors import DomainRuleError
from app.persistence.models import ProfessorReviewRow, QuestionRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository

_EDITABLE = ("prompt", "reference_solution", "tests")


def _norm(value: str | None) -> str:
    return "" if value is None else value


def submit_review(
    session: Session,
    *,
    question_id: int,
    decision: ReviewDecision,
    reasons: list[RejectionReason] | None = None,
    comment: str | None = None,
    prompt: str | None = None,
    reference_solution: str | None = None,
    tests: str | None = None,
    professor_id: int | None = None,
) -> ProfessorReviewRow:
    """Append a professor review and update the question's usable status.

    Edit updates current question fields but never touches ``original_*``.
    ``changed_fields`` are derived here by comparing submitted values to the
    persisted question — never trusted from the client.
    """
    question = QuestionRepository(session).get(question_id)
    reason_list = list(reasons or [])
    clean_comment = comment.strip() if comment and comment.strip() else None

    edited_prompt: str | None = None
    edited_reference_solution: str | None = None
    edited_tests: str | None = None
    changed_fields: list[str] = []

    if decision is ReviewDecision.APPROVE:
        reason_list = []
        question.status = QuestionStatus.APPROVED
    elif decision is ReviewDecision.REJECT:
        if not reason_list:
            raise DomainRuleError("Reject requires at least one structured reason.")
        question.status = QuestionStatus.REJECTED
    elif decision is ReviewDecision.EDIT:
        if prompt is None or reference_solution is None or tests is None:
            raise DomainRuleError(
                "Edit requires prompt, reference_solution, and tests "
                "(use empty string when unused)."
            )
        if not prompt.strip():
            raise DomainRuleError("Edited prompt must not be empty.")
        edited_prompt = prompt
        edited_reference_solution = reference_solution
        edited_tests = tests
        current = {
            "prompt": _norm(question.prompt),
            "reference_solution": _norm(question.reference_solution),
            "tests": _norm(question.tests),
        }
        submitted = {
            "prompt": edited_prompt,
            "reference_solution": edited_reference_solution,
            "tests": edited_tests,
        }
        changed_fields = [name for name in _EDITABLE if current[name] != submitted[name]]
        if not changed_fields:
            raise DomainRuleError("Edit requires at least one changed field.")
        question.prompt = edited_prompt
        question.reference_solution = edited_reference_solution
        question.tests = edited_tests
        question.status = QuestionStatus.APPROVED
    else:
        raise DomainRuleError(f"Unsupported review decision: {decision}")

    review = ProfessorReviewRow(
        question_id=question.id,
        decision=decision,
        reasons_json=encode_reasons(reason_list),
        comment=clean_comment,
        edited_prompt=edited_prompt,
        edited_reference_solution=edited_reference_solution,
        edited_tests=edited_tests,
        changed_fields_json=encode_changed_fields(changed_fields) if changed_fields else None,
        professor_id=professor_id,
        reviewed_generator_name=question.generator_name,
        reviewed_generator_version=question.generator_version,
    )
    return ProfessorReviewRepository(session).add(review)
```

Update `app/feedback/__init__.py` to export `submit_review`. Keep a thin deprecated wrapper if needed:

```python
def record_review(
    session: Session,
    *,
    question_id: int,
    decision: ReviewDecision,
    comment: str | None = None,
) -> ProfessorReviewRow:
    """Backward-compatible approve/reject helper for older tests.

    Reject still requires reasons via ``submit_review`` — prefer that API.
    """
    if decision is ReviewDecision.REJECT:
        raise DomainRuleError(
            "record_review no longer supports reject without reasons; use submit_review."
        )
    if decision is ReviewDecision.EDIT:
        raise DomainRuleError("record_review no longer supports edit; use submit_review.")
    return submit_review(
        session, question_id=question_id, decision=decision, comment=comment
    )
```

Update `tests/test_persistence.py` so reject/edit cases call `submit_review` with valid payloads (approve-only `record_review` tests can stay).

- [ ] **Step 4: Run service + persistence tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_feedback_service.py tests/test_persistence.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/feedback/service.py app/feedback/__init__.py tests/test_feedback_service.py tests/test_persistence.py
git commit -m "feat(feedback): implement submit_review with edit snapshots"
```

---

### Task 4: Question detail review UI + POST route

**Files:**
- Modify: `app/web/routes/pages.py`
- Modify: `app/web/templates/question_detail.html`
- Test: `tests/test_feedback_pages.py`

**Interfaces:**
- Consumes: `submit_review`, `REJECTION_REASON_LABELS`
- Produces: `POST /questions/{question_id}/review`; Spec + Review panels

- [ ] **Step 1: Write failing page tests**

Create `tests/test_feedback_pages.py` with helpers that insert a minimal question via the test session/engine (mirror patterns from `tests/test_evaluation_pages.py` if present — otherwise insert through repositories inside a fixture using `engine`).

```python
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import QuestionStatus, RejectionReason, ReviewDecision
from app.persistence.models import QuestionRow
from app.persistence.repositories import ProfessorReviewRepository, QuestionRepository


def _seed_question(session: Session) -> int:
    row = QuestionRepository(session).add(
        QuestionRow(
            prompt="Seed prompt",
            original_prompt="Seed prompt",
            reference_solution="true",
            original_reference_solution="true",
            tests="",
            original_tests="",
            status=QuestionStatus.VALIDATION_PASSED,
            generator_name="base",
            generator_version="1",
            spec_json='{"difficulty":"easy","question_type":"true_false"}',
        )
    )
    session.commit()
    assert row.id is not None
    return row.id


def test_detail_shows_spec_and_review_form(client: TestClient, session: Session) -> None:
    qid = _seed_question(session)
    body = client.get(f"/questions/{qid}").text
    assert "QuestionSpec" in body or "Generation spec" in body
    assert 'name="decision"' in body
    assert "technically_incorrect" in body
    assert 'name="comment"' in body
    assert 'name="prompt"' in body


def test_post_approve(client: TestClient, session: Session) -> None:
    qid = _seed_question(session)
    response = client.post(
        f"/questions/{qid}/review",
        data={"decision": "approve", "comment": "Looks good"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    session.expire_all()
    q = QuestionRepository(session).get(qid)
    assert q.status == QuestionStatus.APPROVED
    review = ProfessorReviewRepository(session).list_recent()[0]
    assert review.decision == ReviewDecision.APPROVE


def test_post_reject_multiple_reasons(client: TestClient, session: Session) -> None:
    qid = _seed_question(session)
    response = client.post(
        f"/questions/{qid}/review",
        data={
            "decision": "reject",
            "reasons": ["too_easy", "ambiguous"],
            "comment": "fix me",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    review = ProfessorReviewRepository(session).list_recent()[0]
    assert review.decision == ReviewDecision.REJECT
    assert "too_easy" in (review.reasons_json or "")
    assert "ambiguous" in (review.reasons_json or "")


def test_post_edit_preserves_original(client: TestClient, session: Session) -> None:
    qid = _seed_question(session)
    response = client.post(
        f"/questions/{qid}/review",
        data={
            "decision": "edit",
            "reasons": ["poor_wording"],
            "prompt": "Improved prompt",
            "reference_solution": "true",
            "tests": "",
            "comment": "Wording",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    session.expire_all()
    q = QuestionRepository(session).get(qid)
    assert q.prompt == "Improved prompt"
    assert q.original_prompt == "Seed prompt"
    assert q.status == QuestionStatus.APPROVED
```

If `session` fixture is not shared with `client`’s DB, use the same pattern as other page tests in this repo (read `tests/test_evaluation_pages.py` and match it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_pages.py -v`  
Expected: FAIL (404 on POST / missing form)

- [ ] **Step 3: Wire route + template**

In `question_detail` context, add:

```python
import json
from contextlib import suppress

spec = None
if question.spec_json:
    with suppress(json.JSONDecodeError, TypeError):
        spec = json.loads(question.spec_json)

# pass:
"spec": spec if isinstance(spec, dict) else None,
"rejection_reasons": list(REJECTION_REASON_LABELS.items()),
```

Add `POST` handler:

```python
@router.post("/questions/{question_id}/review", name="review_question")
def review_question(
    request: Request,
    session: DbSession,
    question_id: int,
    decision: Annotated[str, Form()],
    comment: Annotated[str, Form()] = "",
    reasons: Annotated[list[str] | None, Form()] = None,
    prompt: Annotated[str, Form()] = "",
    reference_solution: Annotated[str, Form()] = "",
    tests: Annotated[str, Form()] = "",
) -> RedirectResponse:
    parsed_reasons = [RejectionReason(value) for value in (reasons or [])]
    decision_enum = ReviewDecision(decision)
    kwargs: dict = {
        "question_id": question_id,
        "decision": decision_enum,
        "reasons": parsed_reasons,
        "comment": comment or None,
        "professor_id": None,
    }
    if decision_enum is ReviewDecision.EDIT:
        kwargs.update(
            prompt=prompt,
            reference_solution=reference_solution,
            tests=tests,
        )
    submit_review(session, **kwargs)
    session.commit()
    return RedirectResponse(
        url=f"/questions/{question_id}", status_code=status.HTTP_303_SEE_OTHER
    )
```

Append to `question_detail.html` (before `{% endblock %}`):

```html
  <section class="panel">
    <h2>Generation spec</h2>
    {% if spec %}
      <dl class="kv">
        {% for key, value in spec.items() %}
          <dt>{{ key }}</dt><dd><code>{{ value }}</code></dd>
        {% endfor %}
      </dl>
    {% else %}
      <p class="empty">No QuestionSpec was retained for this question.</p>
    {% endif %}
  </section>

  <section class="panel">
    <h2>Professor review</h2>
    <form method="post" action="/questions/{{ question.id }}/review" class="stack">
      <fieldset>
        <legend>Decision</legend>
        <label><input type="radio" name="decision" value="approve" required> Approve</label>
        <label><input type="radio" name="decision" value="reject"> Reject</label>
        <label><input type="radio" name="decision" value="edit"> Edit</label>
      </fieldset>

      <fieldset>
        <legend>Reasons (required for Reject; optional for Edit)</legend>
        {% for value, label in rejection_reasons %}
          <label><input type="checkbox" name="reasons" value="{{ value }}"> {{ label }}</label>
        {% endfor %}
      </fieldset>

      <label>Comment (optional)
        <textarea name="comment" rows="3"></textarea>
      </label>

      <fieldset>
        <legend>Edit fields (used only when Decision is Edit)</legend>
        <label>Prompt
          <textarea name="prompt" rows="6">{{ question.prompt }}</textarea>
        </label>
        <label>Reference / answer
          <textarea name="reference_solution" rows="4">{{ question.reference_solution or "" }}</textarea>
        </label>
        <label>Tests
          <textarea name="tests" rows="4">{{ question.tests or "" }}</textarea>
        </label>
      </fieldset>

      <button type="submit">Submit review</button>
    </form>
  </section>
```

Match existing CSS class names where possible; add minimal CSS only if needed.

- [ ] **Step 4: Run page tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_pages.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/pages.py app/web/templates/question_detail.html tests/test_feedback_pages.py
git commit -m "feat(web): add professor review form on question detail"
```

---

### Task 5: Feedback dashboard

**Files:**
- Modify: `app/web/routes/pages.py` (`feedback` view)
- Modify: `app/web/templates/feedback.html`
- Modify: `tests/test_feedback_pages.py` (add dashboard assertions)
- Modify: `tests/test_web.py` only if empty-state copy changes

**Interfaces:**
- Consumes: `count_by_decision()`, `reason_counts()`, `list_recent()`, `decode_reasons`, `REJECTION_REASON_LABELS`
- Produces: dashboard stats on `/feedback`

- [ ] **Step 1: Write failing dashboard test**

Append to `tests/test_feedback_pages.py`:

```python
def test_feedback_dashboard_counts_and_reasons(client: TestClient, session: Session) -> None:
    qid = _seed_question(session)
    client.post(f"/questions/{qid}/review", data={"decision": "approve"})
    client.post(
        f"/questions/{qid}/review",
        data={"decision": "reject", "reasons": ["too_easy", "other"]},
    )
    body = client.get("/feedback").text
    assert "Reviewed" in body or "reviewed" in body.lower()
    assert "approve" in body.lower() or "Approved" in body
    assert "too_easy" in body or "Too easy" in body
```

- [ ] **Step 2: Run to verify fail/incomplete UI**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_feedback_pages.py::test_feedback_dashboard_counts_and_reasons -v`

- [ ] **Step 3: Implement dashboard**

In `feedback` route:

```python
repo = ProfessorReviewRepository(session)
by_decision = repo.count_by_decision()
reviews = repo.list_recent()
reason_counts = repo.reason_counts()
# pass:
"stats": {
    "reviewed": repo.count(),
    "approved": by_decision.get("approve", 0),
    "rejected": by_decision.get("reject", 0),
    "edited": by_decision.get("edit", 0),
},
"reason_distribution": [
    {"code": code, "label": REJECTION_REASON_LABELS[RejectionReason(code)], "count": count}
    for code, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
],
"reviews": reviews,
"decode_reasons": decode_reasons,  # or precompute reasons_display on each review in the route
```

Prefer precomputing in the route (templates stay dumb):

```python
review_rows = [
    {
        "id": r.id,
        "question_id": r.question_id,
        "decision": r.decision,
        "reasons": [REJECTION_REASON_LABELS[x] for x in decode_reasons(r.reasons_json)],
        "comment": r.comment,
        "generator": f"{r.reviewed_generator_name}@{r.reviewed_generator_version}",
        "created_at": r.created_at,
    }
    for r in reviews
]
```

Update `feedback.html` with a stats `dl`/`ul`, a reason distribution list/table, and a Reasons column in the history table. Keep the personalization “planned” deferred block.

- [ ] **Step 4: Run feedback + web smoke tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_feedback_pages.py tests/test_web.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/pages.py app/web/templates/feedback.html tests/test_feedback_pages.py
git commit -m "feat(web): show feedback dashboard counts and reason distribution"
```

---

### Task 6: Full verification + package docstring

**Files:**
- Modify: `app/feedback/__init__.py` (update Status docstring: UI recording implemented)
- Optionally touch `CLAUDE.md` module map line for feedback if it still says “recording implemented” only — keep accurate and minimal

- [ ] **Step 1: Run the full gate**

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Expected: all green. Fix any failures before claiming done.

- [ ] **Step 2: Manual smoke (when a local DB with questions exists)**

1. Delete outdated `data/adaptive_trainer.db` if schema verification fails; restart app.
2. Open `/questions/{id}` — confirm Spec, validation, judge, review form.
3. Approve one, reject one (multiple reasons), edit one.
4. Confirm `/feedback` counts and reason distribution.
5. Inspect SQLite: `original_*` unchanged; review row has `edited_*` + `changed_fields_json` for the edit.

- [ ] **Step 3: Final commit if docstring-only changes remain**

```bash
git add app/feedback/__init__.py
git commit -m "docs(feedback): mark review UI write path as implemented"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| `RejectionReason` enum + labels | Task 1 |
| Extended review fields / JSON helpers | Task 1–2 |
| `submit_review` rules (approve/reject/edit) | Task 3 |
| Edit snapshots + derived `changed_fields` | Task 3 |
| `original_*` preservation | Task 3 (+ page test Task 4) |
| Question status mapping | Task 3 |
| Append-only reviews | Task 3 |
| Detail: Spec + validation/judge + review actions | Task 4 |
| Feedback dashboard counts + reason distribution | Task 5 |
| Tests for approve/reject/multi-reason/comment/edit/retrieval | Tasks 3–5 |
| No personalization / no re-validate / no auth | Global constraints |

## Placeholder / consistency self-review

- No TBD steps; concrete APIs and file paths throughout.
- `submit_review` signature matches the design spec.
- Status mapping and Edit snapshot rules match brainstorming corrections.
- Existing `record_review` callers are explicitly migrated in Task 3.
