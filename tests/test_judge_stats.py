"""The Judges page numbers: per-judge agreement, rewrite progress, trust per style."""

from app.config import get_settings
from app.persistence.models import CourseRow
from tests import test_trust_freeze

taxonomy = test_trust_freeze.taxonomy
seed_current_panel = test_trust_freeze.seed_current_panel


def test_stats_on_an_empty_bank(client):
    body = client.get("/api/judge-prompts/stats").json()
    assert body["styles"] == []
    assert [j["metric"] for j in body["judges"]] == ["difficulty", "subtopic"]
    assert body["judges"][0]["observations"] == 0
    assert body["judges"][0]["agreement_rate"] is None
    assert body["learning_paused"] is False
    assert (
        body["judges"][0]["disagreements_needed"] == get_settings().judge_repair_min_disagreements
    )


def test_stats_report_a_trusted_style_and_the_pause(client, session, taxonomy):
    seed_current_panel(session, taxonomy, disagreements=1)
    session.commit()
    body = client.get(
        "/api/judge-prompts/stats", headers={"X-Course-Id": str(taxonomy.course_id)}
    ).json()
    [style] = body["styles"]
    assert style["style_id"] == "py.trace_output"
    # Not a library style, so there is no display name to show.
    assert style["style_name"] is None
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
    other = CourseRow(name="Other course")
    session.add(other)
    session.commit()
    body = client.get("/api/judge-prompts/stats", headers={"X-Course-Id": str(other.id)}).json()
    assert body["styles"] == []
    # The pause is subject-wide: the other course shares the judges.
    assert body["learning_paused"] is True
