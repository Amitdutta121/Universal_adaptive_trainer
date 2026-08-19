"""Managing an imported taxonomy: renaming its rows, and deleting a version.

Two rules carry this module.

The first is that a rename moves the display name and nothing else. ``stable_id``
is what a student's measured weakness and a question's tagging hang from, so the
tests here assert it does *not* change -- and assert that it therefore stops
matching a hash of the current name, because that divergence is the design rather
than a bug waiting to be tidied up.

The second is what deletion costs. Unlike a book, whose citations are frozen text,
a curriculum version is named by real columns that SQLite does not enforce and the
ORM cannot see. Deleting one leaves questions, question sets and measured student
state pointing at rows that are gone, so refusing by default -- and refusing
outright in the two cases a professor cannot recover from -- is the point.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.curriculum import EXAMPLE_DOCUMENT, CurriculumLibraryService, TaxonomyImportService
from app.curriculum.taxonomy_ids import subtopic_id_from_names, topic_id_from_name
from app.errors import (
    DomainRuleError,
    NotFoundError,
    ResourceInUseError,
    UnoverridableConflictError,
)
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSetVersionRow,
    QuestionSubtopicRow,
    StudentRow,
    StudentSubtopicWeaknessRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import CurriculumRepository, StudentStateRepository


def _document(label: str = "Introductory Python") -> bytes:
    document = json.loads(json.dumps(EXAMPLE_DOCUMENT))
    document["label"] = label
    return json.dumps(document).encode("utf-8")


def _import(session: Session, label: str = "Introductory Python") -> CurriculumVersionRow:
    version = TaxonomyImportService(session).import_upload(
        filename="taxonomy.json", data=_document(label)
    )
    session.commit()
    return version


def _first_subtopic(version: CurriculumVersionRow) -> SubtopicRow:
    return version.topics[0].subtopics[0]


def _question_tagged_with(session: Session, version_id: int, subtopic_id: int) -> QuestionRow:
    """A question grounded in a version and tagged against one of its subtopics."""
    question = QuestionRow(prompt="What does this print?", curriculum_version_id=version_id)
    session.add(question)
    session.flush()
    session.add(QuestionSubtopicRow(question_id=question.id, subtopic_id=subtopic_id))
    session.commit()
    return question


def _student_measured_on(session: Session, topic_id: int, subtopic_id: int) -> StudentRow:
    student = StudentRow(display_name="Ada")
    session.add(student)
    session.flush()
    state = StudentStateRepository(session)
    state.record_mastery(student.id, topic_id, 0.4)
    state.record_weakness(student.id, subtopic_id, 0.9)
    session.commit()
    return student


def _frozen_set(session: Session, version_id: int) -> QuestionSetVersionRow:
    row = QuestionSetVersionRow(label="Spring 2026", curriculum_version_id=version_id)
    session.add(row)
    session.commit()
    return row


class TestUpdateVersionLabel:
    def test_it_renames_a_version(self, session: Session) -> None:
        version = _import(session)
        updated = CurriculumLibraryService(session).update_version_label(
            version.id, label="  Introductory Python 2e  "
        )
        assert updated.label == "Introductory Python 2e"

    def test_a_blank_label_is_refused(self, session: Session) -> None:
        version = _import(session)
        with pytest.raises(DomainRuleError):
            CurriculumLibraryService(session).update_version_label(version.id, label="   ")

    def test_it_does_not_touch_the_status(self, session: Session) -> None:
        """Which taxonomy is approved changes by uploading one, never by an edit."""
        version = _import(session)
        before = version.status
        updated = CurriculumLibraryService(session).update_version_label(version.id, label="New")
        assert updated.status is before

    def test_an_unknown_version_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            CurriculumLibraryService(session).update_version_label(999, label="New")


class TestRenameKeepsIdentity:
    def test_a_subtopic_rename_leaves_its_stable_id_alone(self, session: Session) -> None:
        version = _import(session)
        subtopic = _first_subtopic(version)
        before = subtopic.stable_id

        renamed = CurriculumLibraryService(session).update_subtopic(
            subtopic.id, name="Binding names to values"
        )

        assert renamed.name == "Binding names to values"
        assert renamed.stable_id == before

    def test_the_stable_id_then_stops_matching_its_name_on_purpose(self, session: Session) -> None:
        """The id is an identity, not a checksum of the label (ADR-021).

        Recomputing it would detach every weakness measured under the old id, so
        the divergence is asserted here rather than left to be found and "fixed".
        """
        version = _import(session)
        subtopic = _first_subtopic(version)
        topic_name = version.topics[0].name

        renamed = CurriculumLibraryService(session).update_subtopic(subtopic.id, name="Rebinding")

        assert renamed.stable_id != subtopic_id_from_names(topic_name, "Rebinding")
        assert renamed.stable_id == subtopic_id_from_names(topic_name, "Assignment and rebinding")

    def test_a_topic_rename_leaves_its_stable_id_alone(self, session: Session) -> None:
        version = _import(session)
        topic = version.topics[0]
        before = topic.stable_id

        renamed = CurriculumLibraryService(session).update_topic(topic.id, name="Names and values")

        assert renamed.stable_id == before
        assert renamed.stable_id != topic_id_from_name("Names and values")

    def test_measured_weakness_survives_a_rename(self, session: Session) -> None:
        """The whole reason the id is left alone.

        Asserted against the stored row rather than through
        ``StudentStateRepository.weaknesses_for``, which defaults an id it finds
        no row for -- it would answer 0.9's replacement just as readily if the
        measurement had been lost.
        """
        version = _import(session)
        subtopic = _first_subtopic(version)
        student = _student_measured_on(session, version.topics[0].id, subtopic.id)

        CurriculumLibraryService(session).update_subtopic(subtopic.id, name="Rebinding")
        session.commit()

        stored = (
            session.query(StudentSubtopicWeaknessRow)
            .filter_by(student_id=student.id, subtopic_id=subtopic.id)
            .one()
        )
        assert stored.weakness == pytest.approx(0.9)


class TestRenameRules:
    def test_a_blank_name_is_refused(self, session: Session) -> None:
        version = _import(session)
        with pytest.raises(DomainRuleError):
            CurriculumLibraryService(session).update_subtopic(
                _first_subtopic(version).id, name="  "
            )

    def test_a_blank_description_clears_it(self, session: Session) -> None:
        version = _import(session)
        updated = CurriculumLibraryService(session).update_subtopic(
            _first_subtopic(version).id, description="   "
        )
        assert updated.description is None

    def test_an_omitted_field_is_left_alone(self, session: Session) -> None:
        version = _import(session)
        subtopic = _first_subtopic(version)
        before = subtopic.description

        updated = CurriculumLibraryService(session).update_subtopic(subtopic.id, name="Rebinding")

        assert updated.description == before

    def test_a_rename_may_not_collide_with_a_sibling(self, session: Session) -> None:
        """The document's own duplicate rule, re-applied where the validator is not."""
        version = _import(session)
        first, second = version.topics[0].subtopics[0], version.topics[0].subtopics[1]

        with pytest.raises(DomainRuleError, match=first.name):
            CurriculumLibraryService(session).update_subtopic(second.id, name=first.name)

    def test_collision_ignores_case_spacing_and_punctuation(self, session: Session) -> None:
        version = _import(session)
        first, second = version.topics[0].subtopics[0], version.topics[0].subtopics[1]

        with pytest.raises(DomainRuleError):
            CurriculumLibraryService(session).update_subtopic(
                second.id, name=f"  {first.name.upper()}!  "
            )

    def test_the_same_name_under_a_different_topic_is_allowed(self, session: Session) -> None:
        """Uniqueness is scoped to the topic, exactly as the document scopes it."""
        version = _import(session)
        borrowed = version.topics[0].subtopics[0].name

        updated = CurriculumLibraryService(session).update_subtopic(
            version.topics[1].subtopics[0].id, name=borrowed
        )

        assert updated.name == borrowed

    def test_the_same_name_in_a_different_version_is_allowed(self, session: Session) -> None:
        """Versions are independent snapshots, so they cannot collide with each other."""
        first = _import(session, label="First")
        second = _import(session, label="Second")

        updated = CurriculumLibraryService(session).update_topic(
            second.topics[0].id, name=first.topics[0].name
        )

        assert updated.name == first.topics[0].name


class TestUsage:
    def test_a_fresh_upload_has_nothing_pointing_at_it_but_is_approved(
        self, session: Session
    ) -> None:
        version = _import(session)
        usage = CurriculumLibraryService(session).usage(version.id)

        assert usage.strandable is False
        assert usage.is_approved is True

    def test_it_counts_questions_students_and_sets(self, session: Session) -> None:
        version = _import(session)
        subtopic = _first_subtopic(version)
        _question_tagged_with(session, version.id, subtopic.id)
        _student_measured_on(session, version.topics[0].id, subtopic.id)
        _frozen_set(session, version.id)

        usage = CurriculumLibraryService(session).usage(version.id)

        assert usage.question_count == 1
        assert usage.question_subtopic_link_count == 1
        assert usage.student_count == 1
        assert usage.question_set_count == 1
        assert usage.strandable is True


class TestActivate:
    def test_an_older_approved_version_can_be_made_active_again(self, session: Session) -> None:
        old = _import(session, label="Old")
        new = _import(session, label="New")

        activated = CurriculumLibraryService(session).activate(old.id)
        session.commit()

        assert activated.id == old.id
        assert CurriculumRepository(session).get_approved().id == old.id
        assert old.approved_at is not None
        assert new.approved_at is not None
        assert old.approved_at > new.approved_at

    def test_an_unknown_version_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            CurriculumLibraryService(session).activate(999)


class TestDelete:
    def test_it_removes_the_version_and_its_tree(self, session: Session) -> None:
        _import(session, label="Keep me")
        version = _import(session, label="Delete me")  # this one is now approved

        CurriculumLibraryService(session).delete(_superseded(session, version).id)
        session.commit()

        assert session.query(CurriculumVersionRow).count() == 1
        assert session.query(TopicRow).count() == 2
        assert session.query(SubtopicRow).count() == 5

    def test_the_approved_version_is_refused_even_with_force(self, session: Session) -> None:
        """Deleting it would re-ground the product without anyone deciding to."""
        version = _import(session)

        for force in (False, True):
            with pytest.raises(UnoverridableConflictError, match="approved curriculum version"):
                CurriculumLibraryService(session).delete(version.id, force=force)

    def test_a_frozen_question_set_is_refused_even_with_force(self, session: Session) -> None:
        """A set cannot be edited or deleted, so its coverage could never recover."""
        old = _import(session, label="Old")
        _import(session, label="New")
        _frozen_set(session, old.id)

        for force in (False, True):
            with pytest.raises(UnoverridableConflictError, match="frozen question set"):
                CurriculumLibraryService(session).delete(old.id, force=force)

    def test_questions_and_students_refuse_by_default_then_yield_to_force(
        self, session: Session
    ) -> None:
        old = _import(session, label="Old")
        _import(session, label="New")
        subtopic = _first_subtopic(old)
        _question_tagged_with(session, old.id, subtopic.id)
        _student_measured_on(session, old.topics[0].id, subtopic.id)

        with pytest.raises(ResourceInUseError, match="1 question"):
            CurriculumLibraryService(session).delete(old.id)

        stranded = CurriculumLibraryService(session).delete(old.id, force=True)
        session.commit()

        assert stranded.question_count == 1
        assert stranded.student_count == 1

    def test_a_refusal_deletes_nothing(self, session: Session) -> None:
        old = _import(session, label="Old")
        _import(session, label="New")
        _question_tagged_with(session, old.id, _first_subtopic(old).id)

        with pytest.raises(ResourceInUseError):
            CurriculumLibraryService(session).delete(old.id)

        assert session.get(CurriculumVersionRow, old.id) is not None
        assert session.query(TopicRow).count() == 4

    def test_a_forced_delete_keeps_the_questions_it_strands(self, session: Session) -> None:
        """Their text is still worth reviewing; only the citation is broken."""
        old = _import(session, label="Old")
        _import(session, label="New")
        _question_tagged_with(session, old.id, _first_subtopic(old).id)

        CurriculumLibraryService(session).delete(old.id, force=True)
        session.commit()

        assert session.query(QuestionRow).count() == 1

    def test_an_unknown_version_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            CurriculumLibraryService(session).delete(999)


def _superseded(session: Session, approved: CurriculumVersionRow) -> CurriculumVersionRow:
    """The version the newest upload replaced, which is the deletable one."""
    versions = CurriculumRepository(session).list_versions()
    return next(row for row in versions if row.id != approved.id)


class TestOverHttp:
    def _upload(self, client: TestClient, label: str = "Introductory Python") -> dict:
        response = client.post(
            "/api/curriculum/versions",
            files={"file": ("taxonomy.json", _document(label), "application/json")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_a_version_can_be_renamed(self, client: TestClient) -> None:
        version_id = self._upload(client)["version"]["id"]
        response = client.patch(
            f"/api/curriculum/versions/{version_id}", json={"label": "Spring 2026"}
        )
        assert response.status_code == 200
        assert response.json()["version"]["label"] == "Spring 2026"

    def test_an_older_approved_version_can_be_made_active(self, client: TestClient) -> None:
        old = self._upload(client, label="Old")["version"]["id"]
        new = self._upload(client, label="New")["version"]["id"]

        response = client.post(f"/api/curriculum/versions/{old}/activate")

        assert response.status_code == 200
        assert response.json()["version"]["id"] == old
        assert client.get("/api/curriculum/approved").json()["version"]["id"] == old
        assert client.get("/api/curriculum/versions").json()["approved_version_id"] == old
        assert new != old

    def test_a_subtopic_rename_returns_the_same_stable_id(self, client: TestClient) -> None:
        detail = self._upload(client)
        subtopic = detail["topics"][0]["subtopics"][0]

        response = client.patch(
            f"/api/curriculum/subtopics/{subtopic['id']}", json={"name": "Rebinding"}
        )

        assert response.status_code == 200
        assert response.json()["stable_id"] == subtopic["stable_id"]

    @pytest.mark.parametrize(
        "body",
        [{"topic_id": 2}, {"position": 0}, {"stable_id": "sub-abc"}, {"review_status": "rejected"}],
    )
    def test_a_structural_edit_is_not_expressible(self, client: TestClient, body: dict) -> None:
        """Refused by the request model, so the rule cannot be forgotten in a handler."""
        subtopic = self._upload(client)["topics"][0]["subtopics"][0]
        response = client.patch(f"/api/curriculum/subtopics/{subtopic['id']}", json=body)
        assert response.status_code == 422

    def test_a_version_status_edit_is_not_expressible(self, client: TestClient) -> None:
        version_id = self._upload(client)["version"]["id"]
        response = client.patch(
            f"/api/curriculum/versions/{version_id}", json={"status": "proposed"}
        )
        assert response.status_code == 422

    def test_a_blank_name_is_refused(self, client: TestClient) -> None:
        subtopic = self._upload(client)["topics"][0]["subtopics"][0]
        response = client.patch(f"/api/curriculum/subtopics/{subtopic['id']}", json={"name": " "})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "domain_rule_violation"

    def test_renaming_an_unknown_topic_is_404(self, client: TestClient) -> None:
        assert client.patch("/api/curriculum/topics/999", json={"name": "x"}).status_code == 404

    def test_deleting_the_approved_version_is_409_that_force_cannot_clear(
        self, client: TestClient
    ) -> None:
        """A distinct code, so a client knows not to offer "delete anyway"."""
        version_id = self._upload(client)["version"]["id"]
        response = client.delete(f"/api/curriculum/versions/{version_id}", params={"force": True})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict_not_overridable"

    def test_a_frozen_set_is_refused_with_the_same_unoverridable_code(
        self, client: TestClient
    ) -> None:
        assert (
            client.delete(
                f"/api/curriculum/versions/{self._upload(client)['version']['id']}"
            ).json()["error"]["code"]
            == "conflict_not_overridable"
        )

    def test_a_superseded_version_deletes(self, client: TestClient) -> None:
        old_id = self._upload(client, label="Old")["version"]["id"]
        self._upload(client, label="New")

        response = client.delete(f"/api/curriculum/versions/{old_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["deleted_version_id"] == old_id
        assert body["deleted_topic_count"] == 2
        assert body["deleted_subtopic_count"] == 5
        assert client.get(f"/api/curriculum/versions/{old_id}").status_code == 404

    def test_the_version_page_carries_what_deleting_would_cost(self, client: TestClient) -> None:
        """The count is only useful before the decision (ADR-045)."""
        detail = self._upload(client)
        assert detail["usage"]["is_approved"] is True
        assert detail["usage"]["question_count"] == 0

    def test_the_list_carries_topic_and_subtopic_counts(self, client: TestClient) -> None:
        self._upload(client)
        row = client.get("/api/curriculum/versions").json()["versions"][0]
        assert row["topic_count"] == 2
        assert row["subtopic_count"] == 5
