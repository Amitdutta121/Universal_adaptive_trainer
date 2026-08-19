"""A refused taxonomy claim is retried, kept, and withheld from review (ADR-032).

These are the end-to-end consequences of not raising: what reaches the database,
what the judge is not asked, what the question bank shows, and what survives a
provider failure partway through a batch.
"""

from __future__ import annotations

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from llm_fakes import MalformedThenGoodClient, MetricJudgeClient, SequencedDraftClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import ClaimViolation, Difficulty, QuestionStatus, QuestionType
from app.domain.questions import GenerationAttempt, Question
from app.errors import LLMRequestError, MalformedModelOutputError
from app.evaluation import PedagogicalEvalStatus
from app.generation.attempts import MAX_GENERATION_ATTEMPTS
from app.generation.schemas import OutputPredictionDraft
from app.generation.service import GenerationService
from app.generation.spec import MAX_CLAIMED_SUBTOPICS
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository
from app.validation import get_question_validator

TAXONOMY = (
    b'{"schema_version":"1","label":"Python","topics":['
    b'{"name":"Strings","subtopics":['
    b'{"name":"Immutability"},{"name":"Slicing"},{"name":"Methods"},{"name":"Formatting"}]},'
    b'{"name":"Loops","subtopics":[{"name":"While loops"}]}]}'
)


def _seed(session: Session, settings):
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.think_python())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=TAXONOMY
    )
    session.commit()
    return (
        version,
        version.topics[0],
        version.topics[0].subtopics[0],
        [section.id for chapter in book.chapters for section in chapter.sections],
    )


def _draft(topic_id: int, subtopic_ids: list[int]) -> OutputPredictionDraft:
    """A draft that passes every check except, possibly, its own classification.

    Output prediction, and code whose output really is ``expected_output``: these
    tests are about the claim, so nothing else may be what fails validation.
    """
    return OutputPredictionDraft(
        topic_id=topic_id,
        subtopic_ids=subtopic_ids,
        prompt="What is printed?",
        code="print(3)",
        expected_output="3",
        explanation="It prints 3.",
    )


def _generate(session: Session, version, client, section_ids: list[int]):
    return GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.OUTPUT_PREDICTION,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=section_ids,
    )


# --- what reaches the database --------------------------------------------


def test_a_question_with_a_refused_claim_is_stored_and_marked_failed(
    session: Session, settings
) -> None:
    """The whole point: the run continues and the defective question survives."""
    version, topic, subtopic, section_ids = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id
    client = MetricJudgeClient(draft=_draft(topic.id, [subtopic.id, foreign]))

    rows = _generate(session, version, client, section_ids[:1])

    assert len(rows) == 1
    assert QuestionRepository(session).count() == 1
    assert rows[0].status is QuestionStatus.VALIDATION_FAILED
    assert len(rows[0].generation_attempts) == MAX_GENERATION_ATTEMPTS
    assert rows[0].generation_attempts[-1].violations == [ClaimViolation.FOREIGN_SUBTOPICS]


def test_the_refused_claim_survives_a_reload(session: Session, settings) -> None:
    """The attempts are a column, not a value the service kept in memory."""
    version, topic, subtopic, section_ids = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id
    client = MetricJudgeClient(draft=_draft(topic.id, [subtopic.id, foreign]))

    question_id = _generate(session, version, client, section_ids[:1])[0].id
    session.expunge_all()

    reloaded = QuestionRepository(session).get(question_id)
    assert [attempt.number for attempt in reloaded.generation_attempts] == [1, 2, 3]
    assert reloaded.generation_attempts[0].claimed_subtopic_ids == [subtopic.id, foreign]
    assert reloaded.generation_attempts[0].model == "fake/judge-model"


def test_a_corrected_claim_costs_one_extra_call_and_passes(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id
    client = SequencedDraftClient(
        drafts=[_draft(topic.id, [subtopic.id, foreign]), _draft(topic.id, [subtopic.id])]
    )

    rows = _generate(session, version, client, section_ids[:1])

    assert rows[0].status is QuestionStatus.VALIDATION_PASSED
    assert len(rows[0].generation_attempts) == 2
    assert client.draft_calls == 2
    assert list(rows[0].subtopic_ids) == [subtopic.id]


def test_an_unknown_topic_id_is_stored_as_null_with_the_claim_kept(
    session: Session, settings
) -> None:
    """A foreign key cannot hold an invented id, so the claim lives in evidence."""
    version, _topic, subtopic, section_ids = _seed(session, settings)
    client = MetricJudgeClient(draft=_draft(999999, [subtopic.id]))

    rows = _generate(session, version, client, section_ids[:1])

    assert rows[0].topic_id is None
    assert rows[0].status is QuestionStatus.VALIDATION_FAILED
    assert rows[0].generation_attempts[-1].claimed_topic_id == 999999
    assert rows[0].generation_attempts[-1].violations == [ClaimViolation.UNKNOWN_TOPIC]
    # The raw claim is also in ``content``, because the draft is dumped whole.
    assert rows[0].content is not None
    assert rows[0].content["topic_id"] == 999999


def test_too_many_subtopics_is_refused_even_though_every_id_is_real(
    session: Session, settings
) -> None:
    """Nothing about the stored columns would show the cap was broken."""
    version, topic, _subtopic, section_ids = _seed(session, settings)
    too_many = [subtopic.id for subtopic in topic.subtopics][: MAX_CLAIMED_SUBTOPICS + 1]
    client = MetricJudgeClient(draft=_draft(topic.id, too_many))

    rows = _generate(session, version, client, section_ids[:1])

    assert list(rows[0].subtopic_ids) == too_many
    assert rows[0].status is QuestionStatus.VALIDATION_FAILED
    failed = [
        check.name
        for check in rows[0].validation_report.checks
        if not check.passed and check.deterministic
    ]
    # The pre-existing grounding check cannot see this; only the recorded claim can.
    assert failed == ["claimed_taxonomy_accepted"]


# --- a failed deterministic check retries too ------------------------------


def test_a_failed_check_triggers_a_retry(session: Session, settings) -> None:
    """The claim is fine; the question is not. It still gets another attempt.

    Before ADR-032 widened the loop, validation ran after generation had
    returned, so five of six failed questions in the bank were stored broken
    after a single call.
    """
    version, topic, subtopic, section_ids = _seed(session, settings)
    broken = _draft(topic.id, [subtopic.id])
    broken.expected_output = "this is not what print(3) writes"
    client = MetricJudgeClient(draft=broken)

    rows = _generate(session, version, client, section_ids[:1])

    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    assert rows[0].status is QuestionStatus.VALIDATION_FAILED
    attempts = rows[0].generation_attempts
    assert len(attempts) == MAX_GENERATION_ATTEMPTS
    # The claim was accepted every time -- the retry was driven by the check.
    assert all(attempt.accepted for attempt in attempts)
    assert all(attempt.failed_checks for attempt in attempts)
    assert "expected_output_verified" in {
        check.name for attempt in attempts for check in attempt.failed_checks
    }


def test_a_repaired_check_stops_the_retries(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    broken = _draft(topic.id, [subtopic.id])
    broken.expected_output = "wrong"
    client = SequencedDraftClient(drafts=[broken, _draft(topic.id, [subtopic.id])])

    rows = _generate(session, version, client, section_ids[:1])

    assert rows[0].status is QuestionStatus.VALIDATION_PASSED
    attempts = rows[0].generation_attempts
    assert len(attempts) == 2
    assert attempts[0].failed_checks and not attempts[1].failed_checks
    assert [attempt.usable for attempt in attempts] == [False, True]


def test_the_retry_prompt_states_the_failed_check(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    broken = _draft(topic.id, [subtopic.id])
    broken.expected_output = "wrong"
    client = MetricJudgeClient(draft=broken)

    _generate(session, version, client, section_ids[:1])

    second = client.generation_calls[1]["prompt"]
    assert "--- correction ---" in second
    assert "failed the check 'expected_output_verified'" in second


# --- a malformed reply is retried, not fatal -------------------------------


def test_a_malformed_reply_costs_an_attempt_and_is_retried(session: Session, settings) -> None:
    """The reply was not a question at all, so there is nothing to feed back.

    Observed in production: the model returned the JSON schema of the draft
    instead of an instance, and the whole generation died on the first call.
    """
    version, topic, subtopic, section_ids = _seed(session, settings)
    client = MalformedThenGoodClient(malformed_replies=1, draft=_draft(topic.id, [subtopic.id]))

    rows = _generate(session, version, client, section_ids[:1])

    assert rows[0].status is QuestionStatus.VALIDATION_PASSED
    attempts = rows[0].generation_attempts
    assert len(attempts) == 2
    assert attempts[0].malformed is True
    assert attempts[0].claimed_topic_id is None
    assert attempts[0].usable is False
    assert attempts[1].malformed is False
    assert attempts[1].usable is True


def test_the_retry_tells_the_model_its_reply_was_not_a_question(session: Session, settings) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    client = MalformedThenGoodClient(malformed_replies=1, draft=_draft(topic.id, [subtopic.id]))

    _generate(session, version, client, section_ids[:1])

    second = client.prompts[1]
    assert "--- correction ---" in second
    assert "was not a question" in second
    assert "Do not repeat or describe the schema" in second


def test_every_attempt_malformed_raises_rather_than_storing_nothing(
    session: Session, settings
) -> None:
    """With no readable draft there is no question, so the real error stands."""
    version, topic, subtopic, section_ids = _seed(session, settings)
    client = MalformedThenGoodClient(
        malformed_replies=MAX_GENERATION_ATTEMPTS, draft=_draft(topic.id, [subtopic.id])
    )

    with pytest.raises(MalformedModelOutputError):
        _generate(session, version, client, section_ids[:1])

    assert client.malformed_seen == MAX_GENERATION_ATTEMPTS
    session.rollback()
    assert QuestionRepository(session).count() == 0


# --- the judge is not asked ------------------------------------------------


def test_a_refused_claim_spends_no_judge_calls(session: Session, settings) -> None:
    """ADR-024's existing skip rule, reached without a new rule for claims."""
    version, topic, subtopic, section_ids = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id
    client = MetricJudgeClient(draft=_draft(topic.id, [subtopic.id, foreign]))

    rows = _generate(session, version, client, section_ids[:1])

    assert rows[0].pedagogical_eval is not None
    assert rows[0].pedagogical_eval["status"] == PedagogicalEvalStatus.SKIPPED.value
    # Three generation calls, no judge calls.
    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    assert client.calls == MAX_GENERATION_ATTEMPTS


# --- the validation check is derived from the record ----------------------


def test_a_question_with_no_recorded_attempts_gains_no_claim_check(
    session: Session, settings
) -> None:
    """Questions stored before ADR-032 must validate exactly as they did."""
    version, topic, subtopic, _section_ids = _seed(session, settings)
    question = Question(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[subtopic.id],
        prompt="Anything.",
        question_type=QuestionType.TRUE_FALSE,
    )

    report = get_question_validator(session).validate(question)

    assert "claimed_taxonomy_accepted" not in {check.name for check in report.checks}


def test_the_claim_check_reads_the_last_attempt(session: Session, settings) -> None:
    """A corrected claim is not held against the question that corrected it."""
    version, topic, subtopic, _section_ids = _seed(session, settings)
    question = Question(
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[subtopic.id],
        prompt="Anything.",
        question_type=QuestionType.TRUE_FALSE,
        generation_attempts=[
            GenerationAttempt(
                number=1,
                claimed_topic_id=999999,
                claimed_subtopic_ids=[subtopic.id],
                violations=[ClaimViolation.UNKNOWN_TOPIC],
                detail="Topic 999999 is not in this version.",
                accepted=False,
            ),
            GenerationAttempt(
                number=2,
                claimed_topic_id=topic.id,
                claimed_subtopic_ids=[subtopic.id],
                accepted=True,
            ),
        ],
    )

    report = get_question_validator(session).validate(question)

    claim = next(check for check in report.checks if check.name == "claimed_taxonomy_accepted")
    assert claim.passed


# --- the review queue and the bank ----------------------------------------


def test_a_failed_question_is_never_offered_for_review(
    client: TestClient, session: Session, settings
) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id
    _generate(
        session,
        version,
        MetricJudgeClient(draft=_draft(topic.id, [subtopic.id, foreign])),
        section_ids[:1],
    )

    for mode in ("all", "scoreable"):
        payload = client.get("/api/questions/review-queue", params={"mode": mode}).json()
        assert payload["question"] is None, mode
        # It is not pending either: a question the queue will never offer must not
        # sit in the remainder forever.
        assert (payload["total"], payload["remaining"]) == (0, 0), mode


def test_a_failed_question_is_listed_only_when_asked_for(
    client: TestClient, session: Session, settings
) -> None:
    version, topic, subtopic, section_ids = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id
    _generate(
        session,
        version,
        MetricJudgeClient(draft=_draft(topic.id, [subtopic.id, foreign])),
        section_ids[:1],
    )

    unfiltered = client.get("/api/questions").json()
    assert [q["status"] for q in unfiltered["questions"]] == ["validation_failed"]
    assert unfiltered["status_counts"] == {"validation_failed": 1}

    filtered = client.get(
        "/api/questions", params={"status": QuestionStatus.VALIDATION_PASSED.value}
    ).json()
    assert filtered["questions"] == []
    # The counts still describe the whole bank, so a filtered listing says what it hid.
    assert filtered["status_counts"] == {"validation_failed": 1}
    assert filtered["status"] == "validation_passed"




# --- a provider failure mid-batch ----------------------------------------


class FailAfterNDrafts(MetricJudgeClient):
    """Generates normally, then fails once a given number of drafts is reached."""

    def __init__(self, *, drafts_before_failure: int, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.drafts_before_failure = drafts_before_failure
        self.draft_calls = 0

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: object
    ) -> BaseModel:
        if self.draft is not None and isinstance(self.draft, response_model):
            self.draft_calls += 1
            if self.draft_calls > self.drafts_before_failure:
                raise LLMRequestError("provider unavailable", detail="503")
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )


def test_a_provider_failure_keeps_the_sections_already_generated(
    session: Session, settings
) -> None:
    """Per-section commits: work already paid for is not rolled back."""
    version, topic, subtopic, section_ids = _seed(session, settings)
    client = FailAfterNDrafts(drafts_before_failure=1, draft=_draft(topic.id, [subtopic.id]))

    with pytest.raises(LLMRequestError):
        _generate(session, version, client, section_ids[:2])

    session.rollback()
    assert QuestionRepository(session).count() == 1
