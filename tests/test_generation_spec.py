"""The request half and the claim half of the generation contract (ADR-031)."""

from __future__ import annotations

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import ClaimViolation, Difficulty, QuestionType
from app.domain.questions import QuestionCheck
from app.errors import InvalidQuestionSpecError
from app.generation.attempts import _check_instructions, _claim_instructions, build_correction
from app.generation.spec import (
    MAX_CLAIMED_SUBTOPICS,
    build_question_spec,
    check_claimed_taxonomy,
    require_approved_version,
)
from app.ingestion import BookImportService

TAXONOMY = (
    b'{"schema_version":"1","label":"T","topics":['
    b'{"name":"Strings","subtopics":['
    b'{"name":"Immutability"},{"name":"Slicing"},{"name":"Methods"},{"name":"Formatting"}]},'
    b'{"name":"Loops","subtopics":[{"name":"For loops"}]}]}'
)


def _seed(session: Session, settings):
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="tax.json", data=TAXONOMY
    )
    session.commit()
    topic = version.topics[0]
    return version, topic, topic.subtopics[0], book.chapters[0].sections[0].id


# --------------------------------------------------------------- the request half


def test_build_spec_accepts_an_approved_request(session: Session, settings) -> None:
    version, _topic, _sub, section_id = _seed(session, settings)

    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_id],
    )

    assert spec.source_section_ids == [section_id]


def test_the_spec_carries_no_taxonomy(session: Session, settings) -> None:
    """Topic and subtopics are the generator's answer, not part of the request."""
    fields = set(build_question_spec.__annotations__)
    assert "topic_id" not in fields
    assert "subtopic_ids" not in fields


def test_build_spec_rejects_multiple_source_sections(session: Session, settings) -> None:
    version, _topic, _sub, section_id = _seed(session, settings)

    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            question_type=QuestionType.DEBUGGING,
            difficulty=Difficulty.MEDIUM,
            source_section_ids=[section_id, section_id],
        )


def test_rejects_missing_section(session: Session, settings) -> None:
    version, _topic, _sub, _section_id = _seed(session, settings)

    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            question_type=QuestionType.TRUE_FALSE,
            difficulty=Difficulty.HARD,
            source_section_ids=[999999],
        )


def test_rejects_non_approved_curriculum_version(session: Session, settings) -> None:
    from app.domain.enums import CurriculumStatus
    from app.persistence.models import CurriculumVersionRow

    version = CurriculumVersionRow(
        label="draft",
        status=CurriculumStatus.PROPOSED,
        approved_at=None,
    )
    session.add(version)
    session.commit()

    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            source_section_ids=[1],
        )
    with pytest.raises(InvalidQuestionSpecError):
        require_approved_version(session, version.id)


# ----------------------------------------------------------------- the claim half
#
# The claim half reports rather than raises (ADR-032). Every refusal therefore has
# two answers to check: which rules were broken, and how much of the claim can
# still reach a column, since the question is stored either way.


def test_a_valid_claim_is_accepted(session: Session, settings) -> None:
    version, topic, sub, _section_id = _seed(session, settings)

    outcome = check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id])

    assert outcome.accepted
    assert outcome.violations == []
    assert outcome.detail is None
    assert outcome.storable_topic_id == topic.id
    assert outcome.storable_subtopic_ids == [sub.id]


def test_a_claim_may_name_several_subtopics(session: Session, settings) -> None:
    version, topic, _sub, _section_id = _seed(session, settings)
    ids = [subtopic.id for subtopic in topic.subtopics][:2]

    outcome = check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=ids)

    assert outcome.accepted
    assert outcome.storable_subtopic_ids == ids


def test_a_repeated_subtopic_is_collapsed_not_refused(session: Session, settings) -> None:
    """Naming a subtopic twice is still one classification."""
    version, topic, sub, _section_id = _seed(session, settings)

    outcome = check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, sub.id])

    assert outcome.accepted
    assert outcome.storable_subtopic_ids == [sub.id]
    # The claim itself is kept verbatim: it is evidence, not a value to tidy.
    assert outcome.claimed_subtopic_ids == [sub.id, sub.id]


def test_refuses_a_topic_outside_the_version(session: Session, settings) -> None:
    """A topic id that names nothing cannot reach the foreign key at all."""
    version, _topic, sub, _section_id = _seed(session, settings)

    outcome = check_claimed_taxonomy(version, topic_id=999999, subtopic_ids=[sub.id])

    assert not outcome.accepted
    assert ClaimViolation.UNKNOWN_TOPIC in outcome.violations
    assert outcome.storable_topic_id is None
    assert outcome.claimed_topic_id == 999999
    # A real subtopic is still storable, so the row records what the model said
    # about the half of the claim that exists.
    assert outcome.storable_subtopic_ids == [sub.id]


def test_refuses_a_subtopic_from_another_topic(session: Session, settings) -> None:
    """A question spread across two topics has no single home in the taxonomy."""
    version, topic, sub, _section_id = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id

    outcome = check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, foreign])

    assert not outcome.accepted
    assert outcome.violations == [ClaimViolation.FOREIGN_SUBTOPICS]
    # Both rows exist -- only the relationship is wrong -- so both are stored and
    # the deterministic checks refuse the pairing afterwards.
    assert outcome.storable_topic_id == topic.id
    assert outcome.storable_subtopic_ids == [sub.id, foreign]


def test_refuses_an_unknown_subtopic_and_drops_only_that_id(session: Session, settings) -> None:
    version, topic, sub, _section_id = _seed(session, settings)

    outcome = check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, 999999])

    assert not outcome.accepted
    assert outcome.violations == [ClaimViolation.UNKNOWN_SUBTOPICS]
    assert outcome.storable_subtopic_ids == [sub.id]
    assert outcome.claimed_subtopic_ids == [sub.id, 999999]


def test_refuses_an_empty_claim(session: Session, settings) -> None:
    version, topic, _sub, _section_id = _seed(session, settings)

    outcome = check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[])

    assert not outcome.accepted
    assert outcome.violations == [ClaimViolation.NO_SUBTOPIC]
    assert outcome.storable_subtopic_ids == []


def test_refuses_a_claim_over_the_cap(session: Session, settings) -> None:
    """A question claiming half the taxonomy has classified nothing."""
    version, topic, _sub, _section_id = _seed(session, settings)
    too_many = [subtopic.id for subtopic in topic.subtopics][: MAX_CLAIMED_SUBTOPICS + 1]
    assert len(too_many) == MAX_CLAIMED_SUBTOPICS + 1

    outcome = check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=too_many)

    assert not outcome.accepted
    assert outcome.violations == [ClaimViolation.TOO_MANY_SUBTOPICS]
    # Every id is real, so every id is stored. Nothing about the row would show
    # the cap was broken, which is why the recorded claim is the only witness.
    assert outcome.storable_subtopic_ids == too_many


def test_one_claim_can_break_several_rules(session: Session, settings) -> None:
    """Violations accumulate, so the retry states every problem at once."""
    version, topic, sub, _section_id = _seed(session, settings)
    foreign = version.topics[1].subtopics[0].id

    outcome = check_claimed_taxonomy(
        version, topic_id=topic.id, subtopic_ids=[sub.id, foreign, 999999]
    )

    assert outcome.violations == [
        ClaimViolation.UNKNOWN_SUBTOPICS,
        ClaimViolation.FOREIGN_SUBTOPICS,
    ]
    assert outcome.detail is not None
    assert "999999" in outcome.detail


def test_a_missing_topic_does_not_also_report_foreign_subtopics(session: Session, settings) -> None:
    """Every subtopic of a topic that does not exist is trivially foreign."""
    version, _topic, sub, _section_id = _seed(session, settings)

    outcome = check_claimed_taxonomy(version, topic_id=999999, subtopic_ids=[sub.id])

    assert outcome.violations == [ClaimViolation.UNKNOWN_TOPIC]


# ------------------------------------------------------------- the correction
#
# The retry prompt is the only thing that can change a model's mind, so what it
# says is behaviour, not formatting. A live model given a description of the
# fault ("subtopic 106 is not under topic 11") repeated the same id three times.


def test_the_correction_names_the_offending_id_and_both_resolutions(
    session: Session, settings
) -> None:
    version, topic, sub, _section_id = _seed(session, settings)
    other_topic = version.topics[1]
    foreign = other_topic.subtopics[0].id

    problems = _claim_instructions(
        check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, foreign])
    )
    correction = build_correction(problems, [])

    assert f"Either remove {foreign} from subtopic_ids" in correction
    assert f"set topic_id to {other_topic.id}" in correction
    assert other_topic.name in correction
    # The kept subtopic is not something the model is told to change.
    assert f"remove {sub.id} from subtopic_ids" not in correction


def test_the_correction_tells_the_model_to_drop_an_id_that_does_not_exist(
    session: Session, settings
) -> None:
    """A non-existent id has no owner, so there is only one way out."""
    version, topic, sub, _section_id = _seed(session, settings)

    correction = build_correction(
        _claim_instructions(
            check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=[sub.id, 999999])
        ),
        [],
    )

    assert "Remove subtopic id(s) [999999]" in correction
    assert "No such subtopic exists" in correction
    assert "set topic_id to" not in correction


def test_the_correction_states_the_cap_it_broke(session: Session, settings) -> None:
    version, topic, _sub, _section_id = _seed(session, settings)
    too_many = [subtopic.id for subtopic in topic.subtopics][: MAX_CLAIMED_SUBTOPICS + 1]

    correction = build_correction(
        _claim_instructions(
            check_claimed_taxonomy(version, topic_id=topic.id, subtopic_ids=too_many)
        ),
        [],
    )

    assert f"You named {len(too_many)} subtopics" in correction
    assert f"at most {MAX_CLAIMED_SUBTOPICS} are allowed" in correction


def test_the_correction_reports_an_unknown_topic(session: Session, settings) -> None:
    version, _topic, sub, _section_id = _seed(session, settings)

    outcome = check_claimed_taxonomy(version, topic_id=999999, subtopic_ids=[sub.id])
    correction = build_correction(_claim_instructions(outcome), [])

    assert "Topic id 999999 does not exist" in correction


def test_a_failed_check_becomes_an_instruction_not_a_compliment(session: Session, settings) -> None:
    """A check's detail is its *passing* label, so it must be framed as a failure."""
    failed = [
        QuestionCheck(
            name="debug_reference_parses",
            passed=False,
            detail="Reference solution parses",
            evidence="Test 1: stdout mismatch.",
        )
    ]

    correction = build_correction(_check_instructions(failed), [])

    assert "failed the check 'debug_reference_parses'" in correction
    assert "Test 1: stdout mismatch." in correction


def test_the_correction_carries_earlier_problems_forward(session: Session, settings) -> None:
    """Showing only the latest fault let the model reintroduce the one before it."""
    correction = build_correction(
        ["Options are too long."],
        ["The correct option is the longest.", "Options are too long."],
    )

    assert "Do this:\n- Options are too long." in correction
    assert "Do not reintroduce them:" in correction
    assert "- The correct option is the longest." in correction
    # Already listed as a current problem, so it is not repeated below.
    assert correction.count("Options are too long.") == 1
