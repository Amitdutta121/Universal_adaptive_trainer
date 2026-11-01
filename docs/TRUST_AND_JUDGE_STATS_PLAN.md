# Trust gates and judge stats — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two gaps between the 20-step workflow and the code — trust must include the
professor's accept/reject, and judge rewrites must not silently reset trust — and make step 13
("each judge gets a running record of agreement") visible on the Judges page.

**Architecture:** Trust stays computed on read in `app/evaluation/trust.py`; it gains an
`acceptance` window next to the per-judge windows. A new `app/evaluation/trust_scope.py` answers
"which (taxonomy, style) scopes are trusted under the subject's current judge panel"; judge
learning consults it and pauses while anything is trusted. A read-only
`GET /api/judge-prompts/stats` exposes the per-judge and per-style numbers; the Judges page renders them.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic v2, pytest; Next.js, TanStack Query, Vitest, Biome.

## Global Constraints

- Repo: `C:\Users\amit\orca\workspaces\FInalAdaptiveTrainer\tern`, branch `feature/question-setup-rounds`.
- Python: `.venv\Scripts\python.exe` at the repo root. Tests `python -m pytest`, lint `python -m ruff check app tests`.
- Frontend (in `frontend/`): `npm run typecheck`, `npm run lint`, `npm test`, `npm run api:types` (no server needed).
- Trust thresholds already in `app/config.py`: `judge_trust_min_observations=20`, `judge_trust_min_agreement=0.9`, `judge_trust_window=20`. New acceptance threshold: **0.9**, same window.
- Acceptance means `ReviewDecision.APPROVE` only. `EDIT` (the professor had to fix it) and `REJECT` are not acceptance.
- Judge prompt overrides are **per subject** (`profile.storage_key`), shared by every course of that subject. A rewrite renames the panel (`rubric_version`) for all of them, so the learning pause is subject-wide.
- Manual prompt edits on the Judges page stay allowed (deliberate professor act); the UI warns that they reset trust.
- No new tables or migrations in this plan.
- Match surrounding code: docstrings explain *why*, comments only for constraints the code cannot show.

## Decisions (from the professor, 2026-10-03)

1. Checkpoint-commit the current work in progress first.
2. A style skips review only if, over the same 20-review window, the judges agree **and** the professor accepted at least 90%.
3. While any style is trusted under the current panel, no automatic judge rewrite (review-triggered or the Refresh endpoint).
4. Judges page shows per-judge agreement, disagreements toward the next rewrite, and trust per style.

## File map

| File | Task | Change |
|---|---|---|
| `app/config.py` | 1 | add `judge_trust_min_acceptance` |
| `app/evaluation/trust.py` | 1 | `acceptance` window in `judge_trust` |
| `tests/test_judge_trust.py` | 1 | new tests, one adjusted |
| `app/evaluation/trust_scope.py` (new) | 2 | `StyleTrust`, `style_trust_under_current_panel`, `trusted_scopes` |
| `app/web/routes/api/feedback.py` | 2 | `_relearn_judges` pauses |
| `app/web/routes/api/judge_prompts.py` | 2, 3 | refresh refuses (2); `GET /stats` (3) |
| `tests/test_trust_freeze.py` (new) | 2 | |
| `app/evaluation/judge_learning.py` | 3 | public `held_out_for` |
| `app/web/routes/api/schemas.py` | 3 | `MetricTrustOut`, `StyleTrustOut`, `JudgeStatsOut`, `JudgeStatsResponse` |
| `tests/test_judge_stats.py` (new) | 3 | |
| `frontend/src/lib/api/{schema.d.ts,types.ts,queries.ts}` | 4 | regenerated types, `useJudgeStats` |
| `frontend/src/app/courses/[courseId]/judges/judges-screen.tsx` | 4 | agreement, rewrite progress, trust-by-style card, edit warning |
| `frontend/src/app/courses/[courseId]/judges/judges-screen.test.tsx` (new) | 4 | |

## Execution waves

```
Task 0 (orchestrator)  ->  Task 1 || Task 2  (two worktrees, disjoint files)
                       ->  merge  ->  Task 3  ->  Task 4  ->  Task 5 (orchestrator)
```

Worktrees for wave 1, created by the orchestrator after Task 0:

```powershell
git -C tern worktree add ..\tern-t1 -b trust/acceptance-gate
git -C tern worktree add ..\tern-t2 -b trust/learning-pause
```

A worktree has no `.venv` or `node_modules`. Use the main checkout's interpreter by absolute path
and confirm the worktree's code is the one imported:

```powershell
..\tern\.venv\Scripts\python.exe -c "import app, os; print(os.path.dirname(app.__file__))"
```

Expected: a path inside the worktree. If it prints `tern\app`, run with `$env:PYTHONPATH = (Get-Location).Path`.

---

### Task 0: Baseline and checkpoint commit (orchestrator, not a subagent)

- [ ] **Step 1: Record the baseline**

```powershell
cd C:\Users\amit\orca\workspaces\FInalAdaptiveTrainer\tern
.venv\Scripts\python.exe -m pytest -q 2>&1 | Select -Last 5
cd frontend; npm run typecheck; npm test 2>&1 | Select -Last 6; cd ..
```

Write the pass/fail counts into the commit message. Pre-existing failures are not this plan's to fix,
but every later task must not add new ones.

- [ ] **Step 2: Commit everything except the scratch logs**

```powershell
git add -A -- . ":!backend_fresh_*.log" ":!frontend_fresh_*.log"
git status --short | Select-String "fresh_"   # expect only the four ?? log lines
git commit -m "Question setup F: trust routing, live refill, round review (checkpoint)"
```

---

### Task 1: Acceptance window in trust

**Files:**
- Modify: `app/config.py` (beside `judge_trust_min_agreement`, ~line 108)
- Modify: `app/evaluation/trust.py` (`judge_trust`, lines ~167–303)
- Test: `tests/test_judge_trust.py`

**Interfaces:**
- Produces: `app.evaluation.trust.ACCEPTANCE = "acceptance"`; `TrustReport.metrics["acceptance"]` is a
  `MetricTrust`; `TrustReport.trusted` is now false unless acceptance is also trusted.
  `judge_trust(session, question_row, custom_results=None) -> TrustReport` signature unchanged.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_judge_trust.py`:

```python
def seed_decisions(session, taxonomy, decisions):
    for decision in decisions:
        row = question(session, taxonomy)
        route_generated_question(session, row, [])
        review(session, row, decision=decision)


@pytest.mark.parametrize("rejects,trusted", [(2, True), (3, False)])
def test_rejects_block_trust_even_when_judges_agree(session, taxonomy, rejects, trusted):
    seed_decisions(
        session,
        taxonomy,
        [ReviewDecision.REJECT] * rejects + [ReviewDecision.APPROVE] * (20 - rejects),
    )
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["difficulty"].agreement_rate == 1.0
    assert report.metrics["acceptance"].observations == 20
    assert report.metrics["acceptance"].agreements == 20 - rejects
    assert report.trusted is trusted


def test_an_edit_is_not_an_acceptance(session, taxonomy):
    seed_decisions(session, taxonomy, [ReviewDecision.EDIT] * 3 + [ReviewDecision.APPROVE] * 17)
    report = judge_trust(session, question(session, taxonomy), [])
    assert report.metrics["acceptance"].agreements == 17
    assert not report.trusted


def test_acceptance_window_needs_the_minimum_observations(session, taxonomy):
    seed_decisions(session, taxonomy, [ReviewDecision.APPROVE] * 19)
    report = judge_trust(session, question(session, taxonomy), [])
    assert not report.metrics["acceptance"].trusted
```

- [ ] **Step 2: Adjust the one existing test that iterates every metric**

In `test_null_corrections_are_not_implicit_confirmations`, a decision is always explicit, so acceptance
does have observations. Replace its last assertion with:

```python
    assert all(
        metric.observations == 0
        for name, metric in report.metrics.items()
        if name != "acceptance"
    )
    assert report.metrics["acceptance"].observations == 20
```

- [ ] **Step 3: Run to see them fail**

Run: `python -m pytest tests/test_judge_trust.py -q`
Expected: the new tests FAIL with `KeyError: 'acceptance'`.

- [ ] **Step 4: Add the setting** — in `app/config.py`, directly under `judge_trust_min_agreement`:

```python
    #: Share of the window's questions the professor approved unedited. Judges can agree on
    #: difficulty and topic while the questions are still not worth keeping.
    judge_trust_min_acceptance: float = Field(default=0.9, ge=0.9, le=1.0)
```

- [ ] **Step 5: Implement in `app/evaluation/trust.py`**

Module level, below the imports:

```python
#: The professor's own accept/reject, tracked like a judge so trust needs it too.
ACCEPTANCE = "acceptance"
```

In `judge_trust`, the names list:

```python
    names = ["difficulty", "subtopic", ACCEPTANCE, *(f"custom:{rule.id}" for rule in rules)]
```

Inside the `for event, (review, question) in enumerate(pairs):` loop, right after the
`for name in ("difficulty", "subtopic"):` block:

```python
        if question.id not in seen[ACCEPTANCE]:
            observations[ACCEPTANCE].append((review.decision == ReviewDecision.APPROVE, event))
            seen[ACCEPTANCE].add(question.id)
```

A rejected audit already sets `failed_audit` for every name, acceptance included, so revocation needs
no change. In the `for name, values in observations.items():` loop, choose the threshold per name:

```python
        minimum = (
            settings.judge_trust_min_acceptance
            if name == ACCEPTANCE
            else settings.judge_trust_min_agreement
        )
```

and use `rate >= minimum` in place of `rate >= settings.judge_trust_min_agreement`.

- [ ] **Step 6: Run the trust tests, then everything that touches trust**

Run: `python -m pytest tests/test_judge_trust.py tests/test_round_review_safety.py tests/test_live_refill.py tests/test_review_queue.py -q`
Expected: PASS. If a routing test relied on 20 approvals, it still passes (approvals are acceptance).

- [ ] **Step 7: Lint and commit**

```powershell
python -m ruff check app/evaluation/trust.py app/config.py tests/test_judge_trust.py
git add app/config.py app/evaluation/trust.py tests/test_judge_trust.py
git commit -m "Trust: a style skips review only when the professor also accepted 90%"
```

---

### Task 2: Pause judge learning while a style is trusted

**Files:**
- Create: `app/evaluation/trust_scope.py`
- Modify: `app/web/routes/api/feedback.py` (`_relearn_judges`, ~line 131)
- Modify: `app/web/routes/api/judge_prompts.py` (`refresh`, ~line 154)
- Test: `tests/test_trust_freeze.py`

**Interfaces:**
- Consumes: `judge_trust(session, question_row, custom_results=None) -> TrustReport` (unchanged by Task 1).
- Produces:
  - `StyleTrust(curriculum_version_id: int, style_id: str, report: TrustReport)` (frozen dataclass)
  - `style_trust_under_current_panel(session, profile, *, curriculum_version_ids: set[int] | None = None) -> list[StyleTrust]`
  - `trusted_scopes(session, profile) -> list[StyleTrust]`
  - test helper `seed_current_panel(session, taxonomy, *, n=20, disagreements=0)` in `tests/test_trust_freeze.py` (Task 3 imports it)

- [ ] **Step 1: Write the failing tests** — create `tests/test_trust_freeze.py`:

```python
"""Judge rewrites rename the panel and reset trust, so they wait while trust is in use."""

from types import SimpleNamespace

from app.domain.enums import JudgeMetricId
from app.evaluation.judge_prompts import effective_rubric_version
from app.evaluation.trust import route_generated_question
from app.evaluation.trust_scope import trusted_scopes
from app.subjects import profile_for_version
from app.web.routes.api import feedback
from tests.test_judge_trust import question, review, taxonomy  # noqa: F401 -- fixture


def seed_current_panel(session, taxonomy, *, n=20, disagreements=0):
    profile = profile_for_version(session, taxonomy.id)
    rubric = effective_rubric_version(session, profile=profile)
    for index in range(n):
        row = question(session, taxonomy, rubric=rubric)
        route_generated_question(session, row, [])
        review(session, row, agrees=index >= disagreements)
    return profile


def _outcome():
    row = SimpleNamespace(judges_refreshed=None, refresh_error=None)
    return (
        SimpleNamespace(attributed_metrics=[JudgeMetricId.DIFFICULTY], row=row),
        SimpleNamespace(judges_refreshed=None, refresh_error=None),
    )


def test_nothing_is_trusted_in_an_empty_bank(session, taxonomy):
    assert trusted_scopes(session, profile_for_version(session, taxonomy.id)) == []


def test_a_style_is_trusted_under_the_current_panel(session, taxonomy):
    profile = seed_current_panel(session, taxonomy)
    scopes = trusted_scopes(session, profile)
    assert [(s.curriculum_version_id, s.style_id) for s in scopes] == [
        (taxonomy.id, "py.trace_output")
    ]


def test_trust_earned_under_an_old_panel_does_not_count(session, taxonomy):
    for _ in range(20):
        row = question(session, taxonomy, rubric="old-panel")
        route_generated_question(session, row, [])
        review(session, row)
    assert trusted_scopes(session, profile_for_version(session, taxonomy.id)) == []


def test_review_relearning_waits_while_a_style_is_trusted(session, taxonomy, monkeypatch):
    profile = seed_current_panel(session, taxonomy)
    calls = []
    monkeypatch.setattr(feedback, "refresh_judge_prompt", lambda *a, **k: calls.append(a))
    outcome, reported = _outcome()
    feedback._relearn_judges(session, outcome, reported, profile)
    assert calls == []
    assert reported.judges_refreshed == []


def test_review_relearning_runs_when_nothing_is_trusted(session, taxonomy, monkeypatch):
    profile = profile_for_version(session, taxonomy.id)
    calls = []
    monkeypatch.setattr(feedback, "refresh_judge_prompt", lambda *a, **k: calls.append(a))
    outcome, reported = _outcome()
    feedback._relearn_judges(session, outcome, reported, profile)
    assert len(calls) == 1


def test_the_refresh_endpoint_refuses_while_a_style_is_trusted(client, session, taxonomy):
    seed_current_panel(session, taxonomy)
    session.commit()
    response = client.post("/api/judge-prompts/difficulty/refresh")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "domain_rule_violation"
```

If `CourseRow` does not default to the Intro Python subject, the refresh test (which sends no
`X-Course-Id`) must send `headers={"X-Course-Id": str(taxonomy.course_id)}`.

- [ ] **Step 2: Run to see them fail**

Run: `python -m pytest tests/test_trust_freeze.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.evaluation.trust_scope'`.

- [ ] **Step 3: Create `app/evaluation/trust_scope.py`**

```python
"""Which (taxonomy, style) scopes are trusted under a subject's current judge panel.

Trust is only counted for evaluations made under the same ``rubric_version``. A judge rewrite
renames the panel for every course of the subject, so callers that would rewrite a judge ask
this module first. Trust is computed on read; the newest question of each scope under the
current panel stands in for "a question of this scope judged now".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.judge_prompts import effective_rubric_version
from app.evaluation.trust import TrustReport, judge_trust
from app.persistence.models import QuestionRow
from app.subjects import SubjectProfile
from app.subjects.resolve import key_of_version, storage_keys_by_version


@dataclass(frozen=True)
class StyleTrust:
    curriculum_version_id: int
    style_id: str
    report: TrustReport


def style_trust_under_current_panel(
    session: Session,
    profile: SubjectProfile,
    *,
    curriculum_version_ids: set[int] | None = None,
) -> list[StyleTrust]:
    """Trust per (taxonomy, style) of this subject, judged under the panel in force now."""
    rubric = effective_rubric_version(session, profile=profile)
    stmt = select(QuestionRow).where(
        QuestionRow.style_id.is_not(None),
        QuestionRow.curriculum_version_id.is_not(None),
    )
    if curriculum_version_ids is not None:
        stmt = stmt.where(QuestionRow.curriculum_version_id.in_(curriculum_version_ids))
    rows = list(session.scalars(stmt.order_by(QuestionRow.created_at.desc(), QuestionRow.id.desc())))
    keys = storage_keys_by_version(session, {row.curriculum_version_id for row in rows})
    newest: dict[tuple[int, str], QuestionRow] = {}
    for row in rows:
        if key_of_version(keys, row.curriculum_version_id) != profile.storage_key:
            continue
        if (row.pedagogical_eval or {}).get("rubric_version") != rubric:
            continue
        newest.setdefault((row.curriculum_version_id, row.style_id), row)
    return [
        StyleTrust(version_id, style_id, judge_trust(session, row, None))
        for (version_id, style_id), row in sorted(newest.items())
    ]


def trusted_scopes(session: Session, profile: SubjectProfile) -> list[StyleTrust]:
    """The scopes whose questions skip professor review under the current panel."""
    return [item for item in style_trust_under_current_panel(session, profile) if item.report.trusted]
```

- [ ] **Step 4: Pause review-triggered learning** — in `app/web/routes/api/feedback.py` add
`from app.evaluation.trust_scope import trusted_scopes` and, in `_relearn_judges`, right after
`if not outcome.attributed_metrics: return`:

```python
    trusted = trusted_scopes(session, profile)
    if trusted:
        # A rewrite renames the panel and every trusted style would fall back to review.
        logger.info(
            "Judge learning paused: %s style(s) trusted under the current panel.", len(trusted)
        )
        outcome.row.judges_refreshed = []
        reported.judges_refreshed = []
        return
```

Add one sentence to the `_relearn_judges` docstring: "Paused while any style of this subject is
trusted under the current panel (docs/TRUST_AND_JUDGE_STATS_PLAN.md)."

- [ ] **Step 5: Refuse the manual Refresh** — in `app/web/routes/api/judge_prompts.py` import
`DomainRuleError` from `app.errors` and `trusted_scopes`, and at the top of `refresh`:

```python
    trusted = trusted_scopes(session, profile)
    if trusted:
        raise DomainRuleError(
            "Judge learning is paused while questions skip review.",
            detail=(
                f"{len(trusted)} style(s) are trusted under the current judges. A rewrite would "
                "send them all back to review; edit the prompt by hand if that is intended."
            ),
        )
```

- [ ] **Step 6: Run the new and the neighbouring tests**

Run: `python -m pytest tests/test_trust_freeze.py tests/test_judge_learning.py tests/test_review_outcomes.py tests/test_judge_trust.py -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```powershell
python -m ruff check app/evaluation/trust_scope.py app/web/routes/api/feedback.py app/web/routes/api/judge_prompts.py tests/test_trust_freeze.py
git add app/evaluation/trust_scope.py app/web/routes/api/feedback.py app/web/routes/api/judge_prompts.py tests/test_trust_freeze.py
git commit -m "Judges: pause automatic rewrites while a style is trusted"
```

---

### Merge wave 1 (orchestrator)

```powershell
cd tern
git merge --no-ff trust/acceptance-gate
git merge --no-ff trust/learning-pause
.venv\Scripts\python.exe -m pytest tests/test_judge_trust.py tests/test_trust_freeze.py -q
```

Expected: both merges clean (disjoint files); tests PASS. With Task 1 merged, the freeze tests
still pass because their seeds approve every question.

---

### Task 3: `GET /api/judge-prompts/stats`

**Files:**
- Modify: `app/evaluation/judge_learning.py` (add `held_out_for` after `agreements_for`)
- Modify: `app/web/routes/api/schemas.py` (after `JudgePromptListResponse`, ~line 1532)
- Modify: `app/web/routes/api/judge_prompts.py`
- Test: `tests/test_judge_stats.py`

**Interfaces:**
- Consumes: `style_trust_under_current_panel`, `trusted_scopes`, `StyleTrust` (Task 2); `ACCEPTANCE` (Task 1);
  `disagreements_for(session, metric, *, profile)`; `get_library(storage_key)` from `app.styles`.
- Produces (JSON shape Task 4 renders):

```text
JudgeStatsResponse {
  rubric_version: str
  judges: [JudgeStatsOut { metric, observations, agreements, agreement_rate: float|null,
                           learnable_disagreements, disagreements_needed }]   # difficulty, subtopic
  styles: [StyleTrustOut { curriculum_version_id, style_id, style_name: str|null, trusted,
                           metrics: {name: MetricTrustOut { observations, agreements,
                                     agreement_rate, trusted, audit_revoked }} }]
  held_out_pairs, held_out_needed: int
  learning_enabled, learning_paused: bool
  trusted_style_count: int
  min_observations: int, min_agreement: float, min_acceptance: float
}
```

- [ ] **Step 1: Write the failing tests** — create `tests/test_judge_stats.py`:

```python
"""The Judges page numbers: per-judge agreement, rewrite progress, trust per style."""

from tests.test_judge_trust import taxonomy  # noqa: F401 -- fixture
from tests.test_trust_freeze import seed_current_panel


def test_stats_on_an_empty_bank(client):
    body = client.get("/api/judge-prompts/stats").json()
    assert body["styles"] == []
    assert [j["metric"] for j in body["judges"]] == ["difficulty", "subtopic"]
    assert body["judges"][0]["observations"] == 0
    assert body["judges"][0]["agreement_rate"] is None
    assert body["learning_paused"] is False
    assert body["judges"][0]["disagreements_needed"] == 5


def test_stats_report_a_trusted_style_and_the_pause(client, session, taxonomy):
    seed_current_panel(session, taxonomy, disagreements=1)
    session.commit()
    body = client.get(
        "/api/judge-prompts/stats", headers={"X-Course-Id": str(taxonomy.course_id)}
    ).json()
    [style] = body["styles"]
    assert style["style_id"] == "py.trace_output"
    assert style["trusted"] is True
    assert style["metrics"]["difficulty"]["agreements"] == 19
    assert style["metrics"]["acceptance"]["observations"] == 20
    difficulty = body["judges"][0]
    assert (difficulty["observations"], difficulty["agreements"]) == (20, 19)
    assert difficulty["agreement_rate"] == 0.95
    assert body["learning_paused"] is True
    assert body["trusted_style_count"] == 1


def test_stats_are_scoped_to_the_course(client, session, taxonomy):
    seed_current_panel(session, taxonomy)
    session.commit()
    from app.persistence.models import CourseRow

    other = CourseRow(name="Other course")
    session.add(other)
    session.commit()
    body = client.get("/api/judge-prompts/stats", headers={"X-Course-Id": str(other.id)}).json()
    assert body["styles"] == []
    # The pause is subject-wide: the other course shares the judges.
    assert body["learning_paused"] is True
```

- [ ] **Step 2: Run to see them fail**

Run: `python -m pytest tests/test_judge_stats.py -q`
Expected: FAIL with 404/405 on `/api/judge-prompts/stats`.

- [ ] **Step 3: `held_out_for`** — in `app/evaluation/judge_learning.py`, after `agreements_for`:

```python
def held_out_for(session: Session, *, profile: SubjectProfile = PYTHON_PROFILE) -> int:
    """How many reserved pairs of this subject a rewrite could be scored on."""
    rows = ReviewOutcomeRepository(session).list_held_out(limit=_SUBJECT_SCAN)
    return len(_of_subject(session, rows, profile, _SUBJECT_SCAN))
```

- [ ] **Step 4: Schemas** — in `app/web/routes/api/schemas.py`, after `JudgePromptListResponse`:

```python
class MetricTrustOut(BaseModel):
    observations: int
    agreements: int
    agreement_rate: float
    trusted: bool
    audit_revoked: bool


class StyleTrustOut(BaseModel):
    """One (taxonomy, style) scope: whether its questions skip review, and why not."""

    curriculum_version_id: int
    style_id: str
    style_name: str | None
    trusted: bool
    #: ``difficulty``, ``subtopic``, ``acceptance`` and ``custom:<id>`` windows.
    metrics: dict[str, MetricTrustOut]


class JudgeStatsOut(BaseModel):
    """Step 13: how often the professor agreed with one judge, pooled over styles' windows."""

    metric: JudgeMetricId
    observations: int
    agreements: int
    agreement_rate: float | None
    #: Disagreements a rewrite could learn from now (held-out third excluded).
    learnable_disagreements: int
    disagreements_needed: int


class JudgeStatsResponse(BaseModel):
    rubric_version: str
    judges: list[JudgeStatsOut]
    styles: list[StyleTrustOut]
    held_out_pairs: int
    held_out_needed: int
    learning_enabled: bool
    #: True while any style of this subject is trusted; automatic rewrites wait.
    learning_paused: bool
    trusted_style_count: int
    min_observations: int
    min_agreement: float
    min_acceptance: float
```

- [ ] **Step 5: Route** — in `app/web/routes/api/judge_prompts.py`. Imports to add:
`from sqlalchemy import select`, `from app.config import get_settings`,
`from app.evaluation.judge_learning import held_out_for`,
`from app.evaluation.trust_scope import style_trust_under_current_panel`,
`from app.persistence.models import CurriculumVersionRow`, `from app.styles import get_library`,
`CourseScope` from `deps`, and the four new schemas. Then:

```python
SHOWN_JUDGES = (JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC)


@router.get("/stats", response_model=JudgeStatsResponse)
def judge_stats(
    session: DbSession, profile: CourseProfile, course: CourseScope
) -> JudgeStatsResponse:
    """Agreement per judge and trust per style under the panel in force now.

    Styles are this course's; the learning pause is the subject's, because a rewrite renames
    the panel for every course that shares these judges.
    """
    settings = get_settings()
    version_ids = (
        set(
            session.scalars(
                select(CurriculumVersionRow.id).where(CurriculumVersionRow.course_id == course)
            )
        )
        if course is not None
        else None
    )
    scoped = style_trust_under_current_panel(session, profile, curriculum_version_ids=version_ids)
    subject_wide = (
        scoped if version_ids is None else style_trust_under_current_panel(session, profile)
    )
    names = {style.id: style.name for style in get_library(profile.storage_key)}

    judges = []
    for metric in SHOWN_JUDGES:
        windows = [
            item.report.metrics[metric.value]
            for item in scoped
            if metric.value in item.report.metrics
        ]
        observations = sum(window.observations for window in windows)
        agreements = sum(window.agreements for window in windows)
        judges.append(
            JudgeStatsOut(
                metric=metric,
                observations=observations,
                agreements=agreements,
                agreement_rate=agreements / observations if observations else None,
                learnable_disagreements=len(disagreements_for(session, metric, profile=profile)),
                disagreements_needed=settings.judge_repair_min_disagreements,
            )
        )
    trusted_count = sum(item.report.trusted for item in subject_wide)
    return JudgeStatsResponse(
        rubric_version=effective_rubric_version(session, profile=profile),
        judges=judges,
        styles=[
            StyleTrustOut(
                curriculum_version_id=item.curriculum_version_id,
                style_id=item.style_id,
                style_name=names.get(item.style_id),
                trusted=item.report.trusted,
                metrics={
                    name: MetricTrustOut(
                        observations=value.observations,
                        agreements=value.agreements,
                        agreement_rate=value.agreement_rate,
                        trusted=value.trusted,
                        audit_revoked=value.audit_revoked,
                    )
                    for name, value in item.report.metrics.items()
                },
            )
            for item in scoped
        ],
        held_out_pairs=held_out_for(session, profile=profile),
        held_out_needed=settings.judge_repair_min_scoring_pairs,
        learning_enabled=settings.judge_learning_enabled,
        learning_paused=trusted_count > 0,
        trusted_style_count=trusted_count,
        min_observations=settings.judge_trust_min_observations,
        min_agreement=settings.judge_trust_min_agreement,
        min_acceptance=settings.judge_trust_min_acceptance,
    )
```

Place it above `@router.put("/{metric}")` so the static path reads first.

- [ ] **Step 6: Run**

Run: `python -m pytest tests/test_judge_stats.py tests/test_judge_prompts.py tests/test_trust_freeze.py -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```powershell
python -m ruff check app/evaluation/judge_learning.py app/web/routes/api/schemas.py app/web/routes/api/judge_prompts.py tests/test_judge_stats.py
git add app/evaluation/judge_learning.py app/web/routes/api/schemas.py app/web/routes/api/judge_prompts.py tests/test_judge_stats.py
git commit -m "Judges: GET /api/judge-prompts/stats with agreement, rewrite progress and trust per style"
```

---

### Task 4: Judges page shows the numbers

**Files:**
- Modify: `frontend/src/lib/api/schema.d.ts` (regenerated), `frontend/src/lib/api/types.ts` (~line 76), `frontend/src/lib/api/queries.ts` (`qk.judgePrompts` ~line 83, judge prompts section ~line 1001)
- Modify: `frontend/src/app/courses/[courseId]/judges/judges-screen.tsx`
- Test: `frontend/src/app/courses/[courseId]/judges/judges-screen.test.tsx`

**Interfaces:**
- Consumes: `GET /api/judge-prompts/stats` (Task 3 shape).
- Produces: `useJudgeStats()`, types `JudgeStats`, `JudgeStat`, `StyleTrust`.

- [ ] **Step 1: Regenerate types** (from `frontend/`): `npm run api:types`. Expected: `API types regenerated.`
  and `schema.d.ts` gains `JudgeStatsResponse`, `JudgeStatsOut`, `StyleTrustOut`, `MetricTrustOut`.

- [ ] **Step 2: Types and hook**

`types.ts`, after `JudgePrompt`:

```ts
export type JudgeStats = Schemas["JudgeStatsResponse"];
export type JudgeStat = Schemas["JudgeStatsOut"];
export type StyleTrust = Schemas["StyleTrustOut"];
```

`queries.ts`, in `qk.judgePrompts`:

```ts
    stats: () => ["judge-prompts", "stats"] as const,
```

and after `useJudgePrompts`:

```ts
/** Agreement per judge and trust per style under the current panel (step 13). */
export const judgeStatsQuery = () =>
  queryOptions({
    queryKey: qk.judgePrompts.stats(),
    queryFn: () => unwrap(api.GET("/api/judge-prompts/stats")),
    staleTime: 0,
    refetchOnWindowFocus: true,
  });

export const useJudgeStats = () => useQuery(judgeStatsQuery());
```

`useSubmitReview` already invalidates `qk.judgePrompts.all`, which covers `stats`.

- [ ] **Step 3: Write the failing test** — create `judges-screen.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JudgesScreen } from "./judges-screen";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/app/courses/[courseId]/questions/setup/custom-rules", () => ({
  CustomRules: () => null,
}));

const prompt = (metric: "difficulty" | "subtopic") => ({
  metric,
  label: metric,
  system_prompt: "p",
  shipped_prompt: "p",
  edited: false,
  learned: false,
  rules: [],
  evidence_count: 0,
  available_disagreements: 3,
  revision: 0,
  note: null,
  updated_at: null,
});

const trustWindow = (observations: number, agreements: number, trusted = false) => ({
  observations,
  agreements,
  agreement_rate: observations ? agreements / observations : 0,
  trusted,
  audit_revoked: false,
});

let paused = false;

vi.mock("@/lib/api/queries", () => ({
  useApprovedCurriculum: () => ({ isPending: false, data: { version: { id: 5 } } }),
  useJudgePrompts: () => ({
    isPending: false,
    error: null,
    data: { prompts: [prompt("difficulty"), prompt("subtopic")], rubric_version: "r", shipped_rubric_version: "r" },
  }),
  useJudgeStats: () => ({
    data: {
      rubric_version: "r",
      judges: [
        { metric: "difficulty", observations: 20, agreements: 18, agreement_rate: 0.9, learnable_disagreements: 3, disagreements_needed: 5 },
        { metric: "subtopic", observations: 0, agreements: 0, agreement_rate: null, learnable_disagreements: 0, disagreements_needed: 5 },
      ],
      styles: [
        {
          curriculum_version_id: 5,
          style_id: "py.trace_output",
          style_name: "Predict the output",
          trusted: paused,
          metrics: {
            difficulty: trustWindow(20, 18, paused),
            subtopic: trustWindow(20, 20, paused),
            acceptance: trustWindow(12, 12),
          },
        },
      ],
      held_out_pairs: 2,
      held_out_needed: 5,
      learning_enabled: true,
      learning_paused: paused,
      trusted_style_count: paused ? 1 : 0,
      min_observations: 20,
      min_agreement: 0.9,
      min_acceptance: 0.9,
    },
  }),
  useRevertJudgePrompt: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSaveJudgePrompt: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("JudgesScreen stats", () => {
  it("shows professor agreement and rewrite progress per judge", () => {
    paused = false;
    render(<JudgesScreen />);
    expect(screen.getByText("18/20 agreed (90%)")).toBeInTheDocument();
    expect(screen.getByText("No reviewed questions under this prompt yet")).toBeInTheDocument();
    expect(screen.getAllByText("Next rewrite: 3 of 5 disagreements")[0]).toBeInTheDocument();
  });

  it("lists trust per style with what is still missing", () => {
    paused = false;
    render(<JudgesScreen />);
    expect(screen.getByText("Predict the output")).toBeInTheDocument();
    expect(screen.getByText("Building trust: 12 of 20 reviews")).toBeInTheDocument();
  });

  it("says when rewrites are paused", () => {
    paused = true;
    render(<JudgesScreen />);
    expect(screen.getAllByText("Rewrites paused while 1 style skips review")[0]).toBeInTheDocument();
    expect(screen.getByText("Skips review")).toBeInTheDocument();
  });
});
```

Run: `npx vitest run src/app/courses/[courseId]/judges` — Expected: FAIL (texts not found).

- [ ] **Step 4: Implement in `judges-screen.tsx`**

Import `useJudgeStats` and types `JudgeStat`, `JudgeStats`, `StyleTrust`. Helpers above `JudgeCard`:

```tsx
function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function agreementText(stat: JudgeStat | undefined): string {
  if (!stat || stat.observations === 0 || stat.agreement_rate == null) {
    return "No reviewed questions under this prompt yet";
  }
  return `${stat.agreements}/${stat.observations} agreed (${percent(stat.agreement_rate)})`;
}

function rewriteText(stat: JudgeStat | undefined, stats: JudgeStats | undefined): string | null {
  if (!stat || !stats) return null;
  if (!stats.learning_enabled) return "Automatic rewrites are off";
  if (stats.learning_paused) {
    const n = stats.trusted_style_count;
    return `Rewrites paused while ${n} style${n === 1 ? "" : "s"} skip${n === 1 ? "s" : ""} review`;
  }
  const have = Math.min(stat.learnable_disagreements, stat.disagreements_needed);
  return `Next rewrite: ${have} of ${stat.disagreements_needed} disagreements`;
}

function styleStatus(style: StyleTrust, minimum: number): string {
  if (style.trusted) return "Skips review";
  if (Object.values(style.metrics).some((metric) => metric.audit_revoked)) return "Audit failed";
  const fewest = Math.min(...Object.values(style.metrics).map((metric) => metric.observations));
  if (fewest < minimum) return `Building trust: ${fewest} of ${minimum} reviews`;
  return "Below 90% agreement";
}
```

`JudgeCard` gains props `stat?: JudgeStat; stats?: JudgeStats`, and inside `CardDescription`, first:

```tsx
          <span>{agreementText(stat)}</span>
          {rewriteText(stat, stats) ? <span>{rewriteText(stat, stats)}</span> : null}
```

New card, rendered between the judge cards grid and `<TaxonomyCustomRules />`:

```tsx
function StyleTrustCard({ stats }: { stats: JudgeStats }) {
  return (
    <Card className="review-panel">
      <CardHeader>
        <CardTitle className="text-lg">Trust by style</CardTitle>
        <CardDescription>
          A style skips review once the judges agree with you and you accepted at least{" "}
          {percent(stats.min_acceptance)} of its last {stats.min_observations} questions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {stats.styles.length === 0 ? (
          <p className="text-muted-foreground text-sm">No reviewed round questions yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1">Style</th>
                <th>Difficulty</th>
                <th>Topic</th>
                <th>Accepted</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {stats.styles.map((style) => (
                <tr key={`${style.curriculum_version_id}-${style.style_id}`} className="border-t">
                  <td className="py-1">{style.style_name ?? style.style_id}</td>
                  {(["difficulty", "subtopic", "acceptance"] as const).map((name) => {
                    const metric = style.metrics[name];
                    return (
                      <td key={name}>
                        {metric ? `${metric.agreements}/${metric.observations}` : "–"}
                      </td>
                    );
                  })}
                  <td>
                    <Badge variant={style.trusted ? "secondary" : "outline"}>
                      {styleStatus(style, stats.min_observations)}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
```

In `JudgesScreen`: `const stats = useJudgeStats().data;`, pass
`stat={stats?.judges.find((item) => item.metric === prompt.metric)}` and `stats={stats}` to each
`JudgeCard`, render `{stats ? <StyleTrustCard stats={stats} /> : null}` after the grid, and pass
`trustedStyles={stats?.trusted_style_count ?? 0}` to `JudgeEditDialog`. In the dialog, above the
footer:

```tsx
          {trustedStyles > 0 ? (
            <p className="text-amber-700 text-sm dark:text-amber-300">
              Saving resets trust: {trustedStyles} style{trustedStyles === 1 ? "" : "s"} go back to
              your review until the edited judge earns it again.
            </p>
          ) : null}
```

Update the file's top docblock: the page also shows professor agreement per judge and trust per style
from `GET /api/judge-prompts/stats`.

- [ ] **Step 5: Run and check**

```powershell
npx vitest run src/app/courses/[courseId]/judges src/app/courses/[courseId]/review
npm run typecheck
npm run lint
```

Expected: all PASS / clean.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/lib/api frontend/src/app/courses/[courseId]/judges
git commit -m "Judges page: professor agreement, rewrite progress and trust per style"
```

---

### Task 5: Integrate and verify (orchestrator)

- [ ] **Step 1: Full checks** — `python -m pytest -q`, `python -m ruff check app tests`, and in
  `frontend/` `npm run typecheck`, `npm run lint`, `npm test`. Compare with the Task 0 baseline: no new failures.
- [ ] **Step 2: Browser walkthrough** on the Python sample course (course 8 “Python setup check” in the dev DB):
  open Judges page → note difficulty agreement → review two round questions (one approve, one reject with
  a corrected difficulty) in another tab → return to Judges → numbers changed without reload; Trust by
  style row's Accepted count moved. Screenshot before/after.
- [ ] **Step 3: Record decisions** — add to `docs/QUESTION_SETUP_PLAN.md` § Decisions:
  - "Trust needs 90% professor acceptance (approve, unedited) over the same window, as well as judge agreement."
  - "Automatic judge rewrites pause while any style of the subject is trusted; manual edits warn that they reset trust."
- [ ] **Step 4: Commit** `git commit -am "Docs: trust acceptance gate and learning pause"`; remove the two worktrees
  (`git worktree remove ..\tern-t1`, `..\tern-t2`) and delete their branches after merge.

## Out of scope (noted, not planned)

- Lowering the ~60% drop rate on hard targets (see `docs/QUESTION_SETUP_PLAN.md` § Observed drop rate).
- The stale "Not yet read by the judge service" comment on `judge_metrics_enabled` in `app/config.py`.
- Performance of `style_trust_under_current_panel` on large banks (it reads every styled question once
  per call); fine at current sizes, revisit with an index or a materialized counter if the page slows.
