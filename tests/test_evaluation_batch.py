"""Bulk judge re-runs and retained evaluation history (ADR-030).

No test here reaches the network. The three transport functions in
``app.llm.batch`` are replaced with fakes, and the assertions are made against
the request payload the real code built on its way to them -- so the wire format
is checked without a provider, and ingest is checked against provider-shaped
responses the fake hands back.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import book_documents as docs
import pytest
from llm_fakes import judged, verdict_for
from sqlalchemy.orm import Session

from app.config import Settings
from app.curriculum import TaxonomyImportService
from app.domain.enums import (
    Difficulty,
    EvaluationTrigger,
    JudgeBatchStatus,
    JudgeMetricId,
    QuestionStatus,
    QuestionType,
)
from app.domain.questions import QuestionCheck, QuestionValidationReport
from app.errors import ConfigurationError, DomainRuleError
from app.evaluation import batch_service
from app.evaluation.batch_service import (
    backfill_generation_history,
    poll_and_ingest,
    record_evaluation,
    submit_bank_rerun,
)
from app.evaluation.prompts import RUBRIC_VERSION
from app.evaluation.schema import RESPONSE_MODEL_FOR, PedagogicalEvalStatus
from app.ingestion import BookImportService
from app.llm import batch as batch_transport
from app.llm.batch import BatchJobState, build_custom_id, parse_custom_id
from app.persistence.models import QuestionRow
from app.persistence.repositories import (
    JudgeBatchRunRepository,
    QuestionEvaluationRepository,
)

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Output","subtopics":[{"name":"Printing","description":"print()"}]}]}'
)


# ----------------------------------------------------------------- fake provider


class FakeProvider:
    """Stands in for OpenRouter's batch API.

    Records the payload each submission built, so tests can assert on the real
    request bodies rather than on a re-implementation of them.
    """

    def __init__(self) -> None:
        self.submissions: list[dict[str, Any]] = []
        self.status: str = "completed"
        self.results_by_batch: dict[str, list[dict[str, Any]]] = {}
        self.job_error: Any = None
        self.status_calls = 0

    # -- the three functions batch_service calls ---------------------------

    def submit_batch(
        self,
        items: Any,
        *,
        response_schema: dict[str, Any],
        settings: Settings,
    ) -> str:
        payload = batch_transport.build_batch_payload(
            items,
            model=settings.judge_batch_route,
            response_schema=response_schema,
            max_output_tokens=settings.llm_max_output_tokens,
        )
        batch_id = f"batch_{len(self.submissions)}"
        self.submissions.append(payload)
        self.results_by_batch.setdefault(batch_id, [])
        return batch_id

    def fetch_status(self, batch_id: str, *, settings: Settings) -> BatchJobState:
        del settings
        self.status_calls += 1
        results = self.results_by_batch.get(batch_id, [])
        return batch_transport.state_from_payload(
            batch_id,
            {
                "id": batch_id,
                "status": self.status,
                "request_counts": {"total": len(results), "completed": len(results), "failed": 0},
                "results": results,
                "error": self.job_error,
            },
        )

    # -- helpers used by the tests -----------------------------------------

    @property
    def custom_ids(self) -> list[str]:
        return [
            request["custom_id"] for payload in self.submissions for request in payload["requests"]
        ]

    def answer_everything_well(self) -> None:
        """Give every submitted request a valid judge response."""
        for index, payload in enumerate(self.submissions):
            self.results_by_batch[f"batch_{index}"] = [
                _ok_result(request["custom_id"]) for request in payload["requests"]
            ]

    def set_results(self, results: list[dict[str, Any]], *, batch_id: str = "batch_0") -> None:
        self.results_by_batch[batch_id] = results


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    fake = FakeProvider()
    monkeypatch.setattr(batch_service.batch_transport, "submit_batch", fake.submit_batch)
    monkeypatch.setattr(batch_service.batch_transport, "fetch_status", fake.fetch_status)
    monkeypatch.setattr(
        batch_service.batch_transport,
        "download_results",
        lambda batch_id, **kwargs: batch_transport.parse_results(
            fake.fetch_status(batch_id, settings=kwargs["settings"]).raw_results
        ),
    )
    return fake


@pytest.fixture
def batch_settings(settings: Settings) -> Settings:
    """Settings with the batch re-run enabled and credentialed."""
    return settings.model_copy(
        update={
            "judge_batch_enabled": True,
            "judge_batch_api_key": _secret("sk-test-batch"),
            "judge_batch_model": "test/judge-model",
        }
    )


def _secret(value: str) -> Any:
    from pydantic import SecretStr

    return SecretStr(value)


# ----------------------------------------------------------------------- seeding


def _ok_result(
    custom_id: str, topic_id: int = 1, subtopic_ids: list[int] | None = None
) -> dict[str, Any]:
    """A provider result carrying a valid answer for that request's metric."""
    metric = JudgeMetricId(parse_custom_id(custom_id)[2])
    content = verdict_for(
        RESPONSE_MODEL_FOR[metric], topic_id, subtopic_ids or [1]
    ).model_dump_json()
    return {
        "id": f"req_{custom_id}",
        "custom_id": custom_id,
        "response": {
            "status_code": 200,
            "request_id": "r1",
            "body": {
                "id": "gen-1",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            },
        },
        "error": None,
    }


def _fail_every_request(provider: FakeProvider, message: str) -> None:
    """Make every submitted request come back as a provider error."""
    for index, payload in enumerate(provider.submissions):
        provider.results_by_batch[f"batch_{index}"] = [
            {"custom_id": request["custom_id"], "error": {"message": message}}
            for request in payload["requests"]
        ]


def _passing_report() -> QuestionValidationReport:
    return QuestionValidationReport(checks=[QuestionCheck(name="syntax", passed=True)])


def _failing_report() -> QuestionValidationReport:
    return QuestionValidationReport(checks=[QuestionCheck(name="syntax", passed=False)])


def _seed_bank(
    session: Session,
    settings: Settings,
    *,
    passing: int = 2,
    failing: int = 1,
    unvalidated: int = 1,
) -> dict[str, list[int]]:
    """Create a question bank spanning every validation outcome."""
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=TAXONOMY
    )
    session.commit()
    section = book.chapters[0].sections[0]
    topic = version.topics[0]
    subtopic = topic.subtopics[0]

    made: dict[str, list[int]] = {"passing": [], "failing": [], "unvalidated": []}
    plan = (
        [("passing", _passing_report())] * passing
        + [("failing", _failing_report())] * failing
        + [("unvalidated", None)] * unvalidated
    )
    for bucket, report in plan:
        row = QuestionRow(
            curriculum_version_id=version.id,
            topic_id=topic.id,
            subtopic_ids=[subtopic.id],
            question_type=QuestionType.OUTPUT_PREDICTION,
            difficulty=Difficulty.EASY,
            status=(
                QuestionStatus.VALIDATION_PASSED
                if report is not None and report.passed
                else QuestionStatus.VALIDATION_FAILED
            ),
            prompt="What is printed?",
            reference_solution="3",
            validation_report=report,
            content={
                "prompt": "What is printed?",
                "code": "print(3)",
                "expected_output": "3",
                "sources": [{"section_id": section.id, "citation": "x"}],
            },
            spec={
                "curriculum_version_id": version.id,
                "question_type": "output_prediction",
                "difficulty": "easy",
                "source_section_ids": [section.id],
            },
        )
        session.add(row)
        session.flush()
        made[bucket].append(row.id)
    session.commit()
    return made


# ------------------------------------------------------------------- custom_id


def test_custom_id_round_trips() -> None:
    custom_id = build_custom_id("abc123", 42, "difficulty")

    assert parse_custom_id(custom_id) == ("abc123", 42, "difficulty")


def test_custom_id_rejects_a_value_it_did_not_build() -> None:
    with pytest.raises(ValueError):
        parse_custom_id("no-separator-here")


# -------------------------------------------------------------------- submission


def test_submission_includes_only_validation_passed_questions(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """ADR-024: the judge never ran on failed or unvalidated questions."""
    ids = _seed_bank(session, batch_settings)

    result = submit_bank_rerun(session, settings=batch_settings)

    assert result.submitted == len(ids["passing"])
    submitted_question_ids = {parse_custom_id(cid)[1] for cid in provider.custom_ids}
    assert submitted_question_ids == set(ids["passing"])
    # One request per metric per question.
    assert len(provider.custom_ids) == len(ids["passing"]) * len(JudgeMetricId)
    assert submitted_question_ids.isdisjoint(ids["failing"])
    assert submitted_question_ids.isdisjoint(ids["unvalidated"])


def test_submitted_payload_carries_the_shared_prompts_and_schema(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """The batch path must reuse the judges' prompts, not fork them."""
    from app.evaluation.prompts import SYSTEM_PROMPT_FOR

    _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)

    submit_bank_rerun(session, settings=batch_settings)

    payload = provider.submissions[0]
    # The provider stream-parses the body, so key order is part of the contract.
    assert list(payload) == ["endpoint", "model", "requests"]
    assert payload["endpoint"] == "/v1/chat/completions"
    assert payload["model"] == "test/judge-model"

    body = payload["requests"][0]["body"]
    system = body["messages"][0]["content"]
    metric = JudgeMetricId(parse_custom_id(payload["requests"][0]["custom_id"])[2])
    assert system.startswith(SYSTEM_PROMPT_FOR[metric])
    # No per-request model: the provider rejects one that differs from the batch.
    assert "model" not in body
    assert body["provider"] == {"data_collection": "deny"}
    # The schema is stated in the system message, matching Instructor's Mode.JSON.
    assert RESPONSE_MODEL_FOR[metric].__name__ in system or "rationale" in system


def test_each_metric_is_submitted_as_its_own_job(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """A provider job carries one response schema, and the four verdicts differ."""
    _seed_bank(session, batch_settings, passing=2, failing=0, unvalidated=0)

    submit_bank_rerun(session, settings=batch_settings)

    assert len(provider.submissions) == len(JudgeMetricId)
    for payload in provider.submissions:
        metrics = {parse_custom_id(r["custom_id"])[2] for r in payload["requests"]}
        assert len(metrics) == 1


def test_the_request_asks_for_json_object_not_a_strict_schema(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """Regression: ``strict: true`` over a Pydantic schema fails the whole batch.

    OpenAI's strict mode requires ``additionalProperties: false`` on every
    object and every property marked required; ``model_json_schema()`` produces
    neither, so a strict request is rejected upstream at validation and every
    result in the batch comes back as an error. Real submission
    ``batch-1786508645`` failed exactly this way on all six requests.
    """
    _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)

    submit_bank_rerun(session, settings=batch_settings)

    body = provider.submissions[0]["requests"][0]["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert "json_schema" not in body["response_format"]
    assert "strict" not in json.dumps(body["response_format"])


def test_a_large_bank_is_split_into_jobs_that_share_one_run_id(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    _seed_bank(session, batch_settings, passing=5, failing=0, unvalidated=0)
    narrow = batch_settings.model_copy(update={"judge_batch_max_requests_per_job": 2})

    result = submit_bank_rerun(session, settings=narrow)

    # Five questions per metric, capped at two per job: 3 jobs x 4 metrics.
    assert len(provider.submissions) == 3 * len(JudgeMetricId)
    assert len(result.run.provider_batch_ids) == 3 * len(JudgeMetricId)
    run_ids = {parse_custom_id(cid)[0] for cid in provider.custom_ids}
    assert run_ids == {result.run.run_id}
    assert result.run.question_count == 5


def test_submission_is_refused_when_batch_runs_are_disabled(
    session: Session, settings: Settings, provider: FakeProvider
) -> None:
    _seed_bank(session, settings)

    with pytest.raises(ConfigurationError):
        submit_bank_rerun(session, settings=settings)

    assert provider.submissions == []


def test_submission_is_refused_when_nothing_is_eligible(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    _seed_bank(session, batch_settings, passing=0, failing=1, unvalidated=1)

    with pytest.raises(DomainRuleError):
        submit_bank_rerun(session, settings=batch_settings)

    assert provider.submissions == []


# ---------------------------------------------------------------------- backfill


def test_backfill_records_existing_evaluations_once(
    session: Session, batch_settings: Settings
) -> None:
    """The seven-evaluation case: nothing recorded before this table existed is lost."""
    ids = _seed_bank(session, batch_settings, passing=2, failing=0, unvalidated=0)
    stamped = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    for question_id in ids["passing"]:
        row = session.get(QuestionRow, question_id)
        assert row is not None
        evaluation = judged(question_id=question_id, judge_model="legacy/model").model_copy(
            update={"created_at": stamped}
        )
        row.pedagogical_eval = evaluation.model_dump(mode="json")
    session.commit()

    first = backfill_generation_history(session)
    session.commit()
    second = backfill_generation_history(session)
    session.commit()

    assert first == 2
    assert second == 0, "a second pass must write nothing"
    repository = QuestionEvaluationRepository(session)
    assert repository.count() == 2
    recorded = repository.list_for_question(ids["passing"][0])
    assert len(recorded) == 1
    assert recorded[0].trigger is EvaluationTrigger.GENERATION
    assert recorded[0].judge_model == "legacy/model"
    # The stored timestamp is preserved, not replaced with today's date.
    assert recorded[0].created_at.replace(tzinfo=UTC) == stamped


def test_submission_backfills_before_it_can_overwrite_anything(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    ids = _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    row = session.get(QuestionRow, ids["passing"][0])
    assert row is not None
    row.pedagogical_eval = judged(question_id=row.id, judge_model="legacy/model").model_dump(
        mode="json"
    )
    session.commit()

    result = submit_bank_rerun(session, settings=batch_settings)

    assert result.backfilled == 1
    history = QuestionEvaluationRepository(session).list_for_question(ids["passing"][0])
    assert [entry.judge_model for entry in history] == ["legacy/model"]


# ------------------------------------------------------------------------ ingest


def test_successful_ingest_appends_history_and_updates_the_current_evaluation(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    ids = _seed_bank(session, batch_settings, passing=2, failing=0, unvalidated=0)
    run = submit_bank_rerun(session, settings=batch_settings).run
    provider.answer_everything_well()

    result = poll_and_ingest(session, run.run_id, settings=batch_settings)

    assert result.ingested == 2
    assert result.failed == 0
    assert result.status is JudgeBatchStatus.COMPLETED
    for question_id in ids["passing"]:
        history = QuestionEvaluationRepository(session).list_for_question(question_id)
        assert len(history) == 1
        assert history[0].trigger is EvaluationTrigger.BATCH_RERUN
        assert history[0].eval_status == PedagogicalEvalStatus.COMPLETED.value
        assert history[0].rubric_version == RUBRIC_VERSION
        # The current evaluation is the newest history row, not something else.
        row = session.get(QuestionRow, question_id)
        assert row is not None
        assert row.pedagogical_eval == history[0].evaluation


def test_history_keeps_the_earlier_evaluation_alongside_the_new_one(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    ids = _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    question_id = ids["passing"][0]
    row = session.get(QuestionRow, question_id)
    assert row is not None
    row.pedagogical_eval = (
        judged(question_id=question_id, judge_model="legacy/model")
        .model_copy(update={"created_at": datetime.now(UTC) - timedelta(days=1)})
        .model_dump(mode="json")
    )
    session.commit()

    run = submit_bank_rerun(session, settings=batch_settings).run
    provider.answer_everything_well()
    poll_and_ingest(session, run.run_id, settings=batch_settings)

    history = QuestionEvaluationRepository(session).list_for_question(question_id)
    assert len(history) == 2
    assert history[0].trigger is EvaluationTrigger.BATCH_RERUN
    assert history[1].judge_model == "legacy/model"


def test_a_malformed_line_becomes_an_error_and_the_others_still_land(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    ids = _seed_bank(session, batch_settings, passing=2, failing=0, unvalidated=0)
    run = submit_bank_rerun(session, settings=batch_settings).run
    spoiled = sorted(provider.custom_ids)[0]
    spoiled_question_id = parse_custom_id(spoiled)[1]
    provider.answer_everything_well()
    for batch_id, results in provider.results_by_batch.items():
        provider.results_by_batch[batch_id] = [
            result
            if result["custom_id"] != spoiled
            else {
                "custom_id": spoiled,
                "response": {
                    "status_code": 200,
                    "body": {"choices": [{"message": {"content": "not json at all"}}]},
                },
                "error": None,
            }
            for result in results
        ]

    result = poll_and_ingest(session, run.run_id, settings=batch_settings)

    # One reviewer failed on one question: that question lands partial, the
    # other lands whole, and neither is lost.
    assert result.ingested == 2
    assert result.failed == 0
    repository = QuestionEvaluationRepository(session)
    statuses = {
        question_id: repository.list_for_question(question_id)[0].eval_status
        for question_id in ids["passing"]
    }
    assert sorted(statuses.values()) == [
        PedagogicalEvalStatus.COMPLETED.value,
        PedagogicalEvalStatus.PARTIAL.value,
    ]
    stored = repository.list_for_question(spoiled_question_id)[0]
    assert stored.gate is None
    assert stored.evaluation is not None


def test_a_provider_error_line_is_recorded_as_an_error_evaluation(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    ids = _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    run = submit_bank_rerun(session, settings=batch_settings).run
    _fail_every_request(provider, "rate limited")

    result = poll_and_ingest(session, run.run_id, settings=batch_settings)

    assert result.failed == 1
    stored = QuestionEvaluationRepository(session).list_for_question(ids["passing"][0])[0]
    assert stored.eval_status == PedagogicalEvalStatus.ERROR.value


def test_repolling_a_completed_run_is_a_no_op(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    _seed_bank(session, batch_settings, passing=2, failing=0, unvalidated=0)
    run = submit_bank_rerun(session, settings=batch_settings).run
    provider.answer_everything_well()

    first = poll_and_ingest(session, run.run_id, settings=batch_settings)
    total_after_first = QuestionEvaluationRepository(session).count()
    second = poll_and_ingest(session, run.run_id, settings=batch_settings)

    assert first.ingested == 2
    assert second.ingested == 0
    assert second.already_recorded == 2
    assert QuestionEvaluationRepository(session).count() == total_after_first
    assert JudgeBatchRunRepository(session).get(run.run_id).completed_count == 2


def test_a_still_running_job_records_nothing_and_stays_pollable(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    run = submit_bank_rerun(session, settings=batch_settings).run
    provider.status = "in_progress"

    result = poll_and_ingest(session, run.run_id, settings=batch_settings)

    assert result.status is JudgeBatchStatus.IN_PROGRESS
    assert result.ingested == 0
    assert QuestionEvaluationRepository(session).count() == 0


@pytest.mark.parametrize(
    ("provider_status", "expected"),
    [
        ("expired", JudgeBatchStatus.EXPIRED),
        ("failed", JudgeBatchStatus.FAILED),
        ("cancelled", JudgeBatchStatus.FAILED),
    ],
)
def test_a_terminal_provider_failure_is_recorded_on_the_run(
    session: Session,
    batch_settings: Settings,
    provider: FakeProvider,
    provider_status: str,
    expected: JudgeBatchStatus,
) -> None:
    _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    run = submit_bank_rerun(session, settings=batch_settings).run
    provider.status = provider_status
    provider.job_error = {"message": "the job did not finish"}

    result = poll_and_ingest(session, run.run_id, settings=batch_settings)

    assert result.status is expected
    stored = JudgeBatchRunRepository(session).get(run.run_id)
    assert stored.status is expected
    assert stored.completed_at is not None
    assert "did not finish" in (stored.error_detail or "")

    # A run that gave up is not re-asked about on the next poll.
    calls_before = provider.status_calls
    poll_and_ingest(session, run.run_id, settings=batch_settings)
    assert provider.status_calls == calls_before


def test_a_run_is_not_complete_while_one_of_its_jobs_is_not(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """Reporting completion with part of the bank unjudged would misstate coverage.

    Each metric is split across two jobs; the first job of each metric finishes
    and the second does not. So two questions have all four reviewers and land,
    and the third has none and waits -- a question is never recorded from a
    subset of its reviewers while its run is still going.
    """
    _seed_bank(session, batch_settings, passing=3, failing=0, unvalidated=0)
    narrow = batch_settings.model_copy(update={"judge_batch_max_requests_per_job": 2})
    run = submit_bank_rerun(session, settings=narrow).run

    calls: list[str] = []
    # The full-size chunk of each metric, plus the first metric's remainder. So
    # the third question has exactly one of its four reviewers back.
    finished_ids = {
        f"batch_{index}"
        for index, payload in enumerate(provider.submissions)
        if len(payload["requests"]) == 2
    } | {"batch_1"}

    def mixed_status(batch_id: str, *, settings: Settings) -> BatchJobState:
        del settings
        calls.append(batch_id)
        finished = batch_id in finished_ids
        index = int(batch_id.removeprefix("batch_"))
        results = (
            [
                _ok_result(request["custom_id"])
                for request in provider.submissions[index]["requests"]
            ]
            if finished
            else []
        )
        return batch_transport.state_from_payload(
            batch_id,
            {
                "id": batch_id,
                "status": "completed" if finished else "in_progress",
                "results": results,
            },
        )

    batch_service.batch_transport.fetch_status = mixed_status  # type: ignore[assignment]
    try:
        result = poll_and_ingest(session, run.run_id, settings=narrow)
    finally:
        batch_service.batch_transport.fetch_status = provider.fetch_status  # type: ignore[assignment]

    assert len(calls) == len(provider.submissions)
    assert result.status is JudgeBatchStatus.IN_PROGRESS
    assert result.ingested == 2, "fully answered questions are recorded even mid-run"
    assert result.pending == 1, "the part-answered question waits for its other reviewers"


def test_record_evaluation_writes_history_and_the_current_value_together(
    session: Session, batch_settings: Settings
) -> None:
    ids = _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    question_id = ids["passing"][0]
    evaluation = judged(question_id=question_id, judge_model="fake/model")

    record_evaluation(
        session,
        question_id,
        evaluation,
        run_id="run-1",
        trigger=EvaluationTrigger.GENERATION,
    )
    session.commit()

    row = session.get(QuestionRow, question_id)
    assert row is not None
    stored = QuestionEvaluationRepository(session).list_for_question(question_id)[0]
    assert row.pedagogical_eval == stored.evaluation
    assert evaluation.gate is not None
    assert stored.gate == evaluation.gate.value


def test_result_parsing_drops_a_line_with_no_custom_id() -> None:
    lines = batch_transport.parse_results(
        [_ok_result("run:1:issues"), {"response": {"status_code": 200, "body": {}}}]
    )

    assert [line.custom_id for line in lines] == ["run:1:issues"]


def test_a_failed_http_line_carries_an_error_not_content() -> None:
    lines = batch_transport.parse_results(
        [{"custom_id": "run:1", "response": {"status_code": 429, "body": {}}}]
    )

    assert lines[0].content is None
    assert "429" in (lines[0].error or "")


def test_submitted_bodies_are_json_serialisable_in_key_order(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """The provider stream-parses the body, so the dumped text must order keys."""
    _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)

    submit_bank_rerun(session, settings=batch_settings)

    dumped = json.dumps(provider.submissions[0], ensure_ascii=False)
    assert dumped.index('"endpoint"') < dumped.index('"model"') < dumped.index('"requests"')


# ------------------------------------------------------- generation writes history


def test_generation_records_its_evaluation_into_history(session: Session, settings: Any) -> None:
    """Generation must go through the same recorder, or history starts incomplete."""
    from llm_fakes import MetricJudgeClient

    from app.generation.service import GenerationService
    from tests.test_generation_base import _debugging_draft, _seed

    version, topic, subtopic, section_ids = _seed(session, settings)

    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))
    rows = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_ids[0]],
    )

    history = QuestionEvaluationRepository(session).list_for_question(rows[0].id)
    assert len(history) == 1
    assert history[0].trigger is EvaluationTrigger.GENERATION
    assert history[0].evaluation == rows[0].pedagogical_eval


def test_generated_questions_need_no_backfill(session: Session, settings: Any) -> None:
    """The backfill exists for pre-existing rows, not for ones just written."""
    from llm_fakes import MetricJudgeClient

    from app.generation.service import GenerationService
    from tests.test_generation_base import _debugging_draft, _seed

    version, topic, subtopic, section_ids = _seed(session, settings)
    client = MetricJudgeClient(draft=_debugging_draft(topic.id, [subtopic.id]))
    GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_ids[0]],
    )

    assert backfill_generation_history(session) == 0


# ------------------------------------------- a failed re-run must not erase a good one


def test_a_failed_rerun_does_not_replace_a_completed_evaluation(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """Regression: a whole failed batch once blanked every stored judgement.

    ADR-024 already says an ``error`` evaluation cannot fail a question that
    passed deterministic checks. The same reasoning applies to the current
    value: a re-run that never reached the model says nothing about the
    question, so it must not overwrite a real judgement with a blank one.
    """
    ids = _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    question_id = ids["passing"][0]
    good = judged(question_id=question_id, judge_model="generation/model")
    row = session.get(QuestionRow, question_id)
    assert row is not None
    row.pedagogical_eval = good.model_dump(mode="json")
    session.commit()

    run = submit_bank_rerun(session, settings=batch_settings).run
    _fail_every_request(provider, "invalid schema")
    result = poll_and_ingest(session, run.run_id, settings=batch_settings)

    assert result.failed == 1
    row = session.get(QuestionRow, question_id)
    assert row is not None
    # The failure is in history...
    history = QuestionEvaluationRepository(session).list_for_question(question_id)
    assert history[0].eval_status == PedagogicalEvalStatus.ERROR.value
    # ...but the completed judgement is still what the question shows.
    assert row.pedagogical_eval is not None
    assert row.pedagogical_eval["status"] == PedagogicalEvalStatus.COMPLETED.value
    assert row.pedagogical_eval["judge_model"] == "generation/model"


def test_a_later_successful_rerun_does_take_over(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """Protecting a completed evaluation must not freeze it forever."""
    ids = _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    question_id = ids["passing"][0]
    row = session.get(QuestionRow, question_id)
    assert row is not None
    row.pedagogical_eval = judged(
        question_id=question_id, judge_model="generation/model"
    ).model_dump(mode="json")
    session.commit()

    run = submit_bank_rerun(session, settings=batch_settings).run
    provider.answer_everything_well()
    poll_and_ingest(session, run.run_id, settings=batch_settings)

    row = session.get(QuestionRow, question_id)
    assert row is not None
    assert row.pedagogical_eval is not None
    assert row.pedagogical_eval["judge_model"] == "test/judge-model (batch)"


def test_an_error_still_becomes_current_when_there_is_nothing_better(
    session: Session, batch_settings: Settings, provider: FakeProvider
) -> None:
    """A question with no completed evaluation should still show the failure."""
    ids = _seed_bank(session, batch_settings, passing=1, failing=0, unvalidated=0)
    question_id = ids["passing"][0]

    run = submit_bank_rerun(session, settings=batch_settings).run
    _fail_every_request(provider, "boom")
    poll_and_ingest(session, run.run_id, settings=batch_settings)

    row = session.get(QuestionRow, question_id)
    assert row is not None
    assert row.pedagogical_eval is not None
    assert row.pedagogical_eval["status"] == PedagogicalEvalStatus.ERROR.value
