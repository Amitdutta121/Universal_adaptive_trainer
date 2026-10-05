"""Judge rewrites rename the panel and reset trust, so they wait while trust is in use."""

from types import SimpleNamespace

from app.domain.enums import JudgeMetricId
from app.evaluation.judge_prompts import effective_rubric_version
from app.evaluation.trust import route_generated_question
from app.evaluation.trust_scope import trusted_scopes
from app.subjects import profile_for_version
from app.web.routes.api import feedback
from tests import test_judge_trust
from tests.test_judge_trust import question, review

taxonomy = test_judge_trust.taxonomy


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
    response = client.post(
        "/api/judge-prompts/difficulty/refresh",
        headers={"X-Course-Id": str(taxonomy.course_id)},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "domain_rule_violation"
