"""The JSON and enum column types in :mod:`app.persistence.types`.

These columns replaced per-call-site ``json.loads`` plus ``isinstance`` checks,
so the tolerance policy they centralise is asserted here rather than in each
subsystem that reads one.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.domain.books import ExtractionWarning
from app.domain.enums import (
    ExtractionWarningCode,
    PreferenceCategory,
    QuestionStatus,
    RejectionReason,
    ReviewDecision,
    WarningSeverity,
)
from app.domain.questions import QuestionCheck, QuestionValidationReport
from app.persistence.models import (
    BookRow,
    PreferenceStatementRow,
    ProfessorReviewRow,
    QuestionRow,
)


def _question(session: Session, **kwargs: object) -> QuestionRow:
    row = QuestionRow(prompt="Question.", **kwargs)
    session.add(row)
    session.commit()
    session.expire_all()
    return session.get(QuestionRow, row.id)


class TestJsonObjectAndList:
    def test_object_round_trips_as_a_dict(self, session: Session) -> None:
        row = _question(session, spec={"topic_id": 1, "source_section_ids": [4, 5]})

        assert row.spec == {"topic_id": 1, "source_section_ids": [4, 5]}

    def test_absent_object_reads_as_none(self, session: Session) -> None:
        assert _question(session).spec is None

    def test_absent_list_reads_as_empty(self, session: Session) -> None:
        book = BookRow(title="B", original_filename="b.json")
        session.add(book)
        session.commit()
        session.expire_all()

        assert session.get(BookRow, book.id).warnings == []

    def test_non_ascii_survives_the_round_trip(self, session: Session) -> None:
        row = _question(session, content={"prompt": "¿Qué imprime?"})

        assert row.content == {"prompt": "¿Qué imprime?"}


class TestUnreadableValuesAreTolerated:
    """A page a professor came to read must not break on a bad stored value."""

    def test_malformed_object_reads_as_none(self, engine: Engine, session: Session) -> None:
        row = _question(session, spec={"topic_id": 1})
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE questions SET spec_json = 'not-json' WHERE id = :id"),
                {"id": row.id},
            )
        session.expire_all()

        assert session.get(QuestionRow, row.id).spec is None

    def test_object_holding_an_array_reads_as_none(self, engine: Engine, session: Session) -> None:
        row = _question(session, spec={"topic_id": 1})
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE questions SET spec_json = '[1, 2]' WHERE id = :id"),
                {"id": row.id},
            )
        session.expire_all()

        assert session.get(QuestionRow, row.id).spec is None

    def test_report_that_no_longer_validates_reads_as_none(
        self, engine: Engine, session: Session
    ) -> None:
        row = _question(session, validation_report=QuestionValidationReport(checks=[]))
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE questions SET validation_report_json = :bad WHERE id = :id"),
                {"bad": '{"checks": "not-a-list"}', "id": row.id},
            )
        session.expire_all()

        assert session.get(QuestionRow, row.id).validation_report is None


class TestPydanticColumns:
    def test_model_list_round_trips(self, session: Session) -> None:
        book = BookRow(
            title="B",
            original_filename="b.json",
            warnings=[
                ExtractionWarning(
                    code=ExtractionWarningCode.SOURCE_TEXT_UNREADABLE,
                    message="Two pages unreadable.",
                    severity=WarningSeverity.DEFECT,
                )
            ],
        )
        session.add(book)
        session.commit()
        session.expire_all()

        stored = session.get(BookRow, book.id).warnings
        assert [warning.message for warning in stored] == ["Two pages unreadable."]
        assert stored[0].severity is WarningSeverity.DEFECT

    def test_single_model_round_trips(self, session: Session) -> None:
        report = QuestionValidationReport(checks=[QuestionCheck(name="harness_valid", passed=True)])
        row = _question(session, validation_report=report)

        assert row.validation_report is not None
        assert row.validation_report.passed is True
        assert row.validation_report.checks[0].name == "harness_valid"

    def test_items_that_no_longer_validate_are_dropped_individually(
        self, engine: Engine, session: Session
    ) -> None:
        book = BookRow(title="B", original_filename="b.json")
        session.add(book)
        session.commit()
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE books SET warnings_json = :raw WHERE id = :id"),
                {
                    "raw": (
                        '[{"code": "not-a-known-code"}, '
                        '{"code": "source_text_unreadable", "message": "Kept.", '
                        '"severity": "defect"}]'
                    ),
                    "id": book.id,
                },
            )
        session.expire_all()

        assert [w.message for w in session.get(BookRow, book.id).warnings] == ["Kept."]


class TestEnumColumns:
    def test_enum_list_round_trips_as_members(self, session: Session) -> None:
        question = _question(session)
        review = ProfessorReviewRow(
            question_id=question.id,
            decision=ReviewDecision.REJECT,
            reasons=[RejectionReason.TOO_EASY, RejectionReason.AMBIGUOUS],
        )
        session.add(review)
        session.commit()
        session.expire_all()

        assert session.get(ProfessorReviewRow, review.id).reasons == [
            RejectionReason.TOO_EASY,
            RejectionReason.AMBIGUOUS,
        ]

    def test_retired_enum_value_is_dropped_not_raised(
        self, engine: Engine, session: Session
    ) -> None:
        """A removed rejection reason must not turn the feedback page into a 500."""
        question = _question(session)
        review = ProfessorReviewRow(
            question_id=question.id,
            decision=ReviewDecision.REJECT,
            reasons=[RejectionReason.TOO_EASY],
        )
        session.add(review)
        session.commit()
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE professor_reviews SET reasons_json = :raw WHERE id = :id"),
                {"raw": '["too_easy", "reason_we_removed"]', "id": review.id},
            )
        session.expire_all()

        assert session.get(ProfessorReviewRow, review.id).reasons == [RejectionReason.TOO_EASY]

    def test_scalar_enum_reads_back_as_the_member_not_a_string(self, session: Session) -> None:
        """Regression: a ``String``-backed enum column returned a bare ``str``.

        Callers guarded ``.value`` access with ``hasattr`` because a constructed
        row held the member while a loaded row held its value.
        """
        row = PreferenceStatementRow(
            rule_text="Prefer concrete code.",
            category=PreferenceCategory.WORDING,
            supporting_review_ids=[1, 2],
        )
        session.add(row)
        session.commit()
        session.expire_all()

        loaded = session.get(PreferenceStatementRow, row.id)
        assert loaded.category is PreferenceCategory.WORDING
        assert loaded.category.value == PreferenceCategory.WORDING.value

    def test_unknown_scalar_enum_value_is_reported(self, engine: Engine, session: Session) -> None:
        """Unlike display data, a schema/code mismatch here is named, not hidden."""
        question = _question(session, status=QuestionStatus.GENERATED)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE questions SET status = 'no_such_status' WHERE id = :id"),
                {"id": question.id},
            )
        session.expire_all()

        with pytest.raises(ValueError, match="no_such_status"):
            _ = session.get(QuestionRow, question.id).status


def test_rows_written_before_these_column_types_still_read(
    engine: Engine, session: Session
) -> None:
    """The stored representation is unchanged, so an existing database keeps working.

    This is what makes the change safe without a migration tool: the columns are
    still ``TEXT`` holding the same JSON the previous ``json.dumps`` calls wrote.
    """
    row = _question(session)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE questions SET spec_json = :spec, content_json = :content, "
                "personalization_context_json = :ctx WHERE id = :id"
            ),
            {
                "spec": '{"source_section_ids":[7]}',
                "content": '{"sources":[{"section_id":7,"citation":"Book, ch.1"}]}',
                "ctx": '{"preference_ids":[3],"retrieved_review_ids":[9]}',
                "id": row.id,
            },
        )
    session.expire_all()

    loaded = session.get(QuestionRow, row.id)
    assert loaded.spec == {"source_section_ids": [7]}
    assert loaded.content["sources"][0]["citation"] == "Book, ch.1"
    assert loaded.personalization_context == {"preference_ids": [3], "retrieved_review_ids": [9]}
