"""Editing a version's tree in place, with soft deletion (ADR-050).

Three rules carry this module.

Removing a row hides it and nothing more: the row, its ids, and everything that points at it
(questions, a student's measured weakness, a frozen set) are left exactly as they were, and the
tree simply stops listing it. The tests assert what stays put as much as what goes.

An edit is judged by the upload's own rules and refused in the upload's words, so a professor
sees one taxonomy contract however they arrived at a tree.

Identity survives the edit: a row that is listed keeps its id and its ``stable_id`` through a
rename or a reorder, and a name that comes back revives the row it left rather than minting a
second one with the same ``stable_id``.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.curriculum import CurriculumLibraryService, CurriculumTreeService, TaxonomyImportService
from app.curriculum.tree_editing import TreeSubtopic, TreeTopic, TreeUpdate
from app.domain.enums import CurriculumItemStatus
from app.errors import InvalidTaxonomyDocumentError, NotFoundError
from app.persistence.models import (
    CurriculumVersionRow,
    QuestionRow,
    QuestionSubtopicRow,
    StudentRow,
    StudentSubtopicWeaknessRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import CurriculumRepository, StudentStateRepository

DOCUMENT = {
    "schema_version": "1",
    "label": "Intro",
    "topics": [
        {
            "name": "Loops",
            "description": "Repeating actions.",
            "subtopics": [
                {"name": "for loops", "description": "Iterating."},
                {"name": "while loops"},
            ],
        },
        {"name": "Functions", "subtopics": [{"name": "Defining"}, {"name": "Return values"}]},
    ],
}


def _import(session: Session, label: str = "Intro") -> CurriculumVersionRow:
    document = json.loads(json.dumps(DOCUMENT))
    document["label"] = label
    version = TaxonomyImportService(session).import_upload(
        filename="taxonomy.json", data=json.dumps(document).encode("utf-8")
    )
    session.commit()
    return version


def _tree(version: CurriculumVersionRow) -> TreeUpdate:
    """The version's current tree as an edit that changes nothing."""
    return TreeUpdate(
        label=version.label,
        topics=[
            TreeTopic(
                id=topic.id,
                name=topic.name,
                description=topic.description or "",
                subtopics=[
                    TreeSubtopic(id=sub.id, name=sub.name, description=sub.description or "")
                    for sub in topic.subtopics
                ],
            )
            for topic in version.topics
        ],
    )


def _apply(session: Session, version_id: int, update: TreeUpdate) -> CurriculumVersionRow:
    version = CurriculumTreeService(session).apply(version_id, update)
    session.commit()
    session.expire_all()
    return version


def _names(version: CurriculumVersionRow) -> list[tuple[str, list[str]]]:
    return [(t.name, [s.name for s in t.subtopics]) for t in version.topics]


class TestAnEditThatChangesNothing:
    def test_it_leaves_every_row_and_id_as_it_was(self, session: Session) -> None:
        version = _import(session)
        before = [(t.id, [s.id for s in t.subtopics]) for t in version.topics]

        edited = _apply(session, version.id, _tree(version))

        assert [(t.id, [s.id for s in t.subtopics]) for t in edited.topics] == before
        assert _names(edited) == [
            ("Loops", ["for loops", "while loops"]),
            ("Functions", ["Defining", "Return values"]),
        ]


class TestRenamingAndReordering:
    def test_a_rename_keeps_the_id_and_the_stable_id(self, session: Session) -> None:
        version = _import(session)
        loops = version.topics[0]
        stable = loops.stable_id
        update = _tree(version)
        update.topics[0].name = "Repetition"
        update.topics[0].subtopics[0].name = "for loops over anything"

        edited = _apply(session, version.id, update)

        assert edited.topics[0].id == loops.id
        assert edited.topics[0].name == "Repetition"
        assert edited.topics[0].stable_id == stable  # an identity, not a checksum of the name
        assert edited.topics[0].subtopics[0].name == "for loops over anything"

    def test_the_version_label_is_part_of_the_edit(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.label = "  Intro, second edition  "

        assert _apply(session, version.id, update).label == "Intro, second edition"

    def test_a_blank_description_is_stored_as_none(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics[0].description = ""

        assert _apply(session, version.id, update).topics[0].description is None

    def test_the_order_given_is_the_order_kept(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics.reverse()
        update.topics[1].subtopics.reverse()

        edited = _apply(session, version.id, update)

        assert _names(edited) == [
            ("Functions", ["Defining", "Return values"]),
            ("Loops", ["while loops", "for loops"]),
        ]


class TestAdding:
    def test_new_rows_are_created_beside_the_old_ones(self, session: Session) -> None:
        version = _import(session)
        old_ids = {t.id for t in version.topics}
        update = _tree(version)
        update.topics[0].subtopics.append(TreeSubtopic(name="do-while"))
        update.topics.append(TreeTopic(name="Files", subtopics=[TreeSubtopic(name="open()")]))

        edited = _apply(session, version.id, update)

        assert old_ids <= {t.id for t in edited.topics}
        assert _names(edited)[0][1] == ["for loops", "while loops", "do-while"]
        assert _names(edited)[2] == ("Files", ["open()"])
        files = edited.topics[2]
        assert files.stable_id and files.stable_id.startswith("top-")
        assert files.review_status is CurriculumItemStatus.ACCEPTED
        assert files.subtopics[0].stable_id.startswith("sub-")


class TestSoftDeleting:
    def test_a_row_that_is_no_longer_listed_is_hidden_not_removed(self, session: Session) -> None:
        version = _import(session)
        functions = version.topics[1]
        update = _tree(version)
        update.topics.pop(1)
        update.topics[0].subtopics.pop(1)

        edited = _apply(session, version.id, update)

        assert _names(edited) == [("Loops", ["for loops"])]
        # Still there, still the same row, marked rather than removed.
        row = session.get(TopicRow, functions.id)
        assert row is not None
        assert row.review_status is CurriculumItemStatus.DELETED
        assert row.name == "Functions"
        assert [t.name for t in edited.all_topics] == ["Loops", "Functions"]

    def test_what_points_at_a_deleted_row_is_left_exactly_as_it_was(self, session: Session) -> None:
        """No cleanup, no refusal: the professor removing a topic knows what they are removing."""
        version = _import(session)
        functions = version.topics[1]
        defining = functions.subtopics[0]
        question = QuestionRow(prompt="Q", curriculum_version_id=version.id, topic_id=functions.id)
        student = StudentRow(display_name="Ada")
        session.add_all([question, student])
        session.flush()
        session.add(QuestionSubtopicRow(question_id=question.id, subtopic_id=defining.id))
        StudentStateRepository(session).record_weakness(student.id, defining.id, 0.9)
        session.commit()
        update = _tree(version)
        update.topics.pop(1)

        _apply(session, version.id, update)

        assert session.get(SubtopicRow, defining.id) is not None
        assert session.get(QuestionRow, question.id).topic_id == functions.id
        assert session.scalar(select(func.count()).select_from(QuestionSubtopicRow)) == 1
        weakness = session.scalars(select(StudentSubtopicWeaknessRow)).one()
        assert weakness.subtopic_id == defining.id and weakness.weakness == pytest.approx(0.9)

    def test_deleted_rows_leave_every_count_that_describes_the_tree(self, session: Session) -> None:
        version = _import(session)
        repo = CurriculumRepository(session)
        assert repo.subtopic_count(version.id) == 4
        update = _tree(version)
        update.topics.pop(1)  # takes its two subtopics out of the tree with it
        update.topics[0].subtopics.pop(0)

        _apply(session, version.id, update)

        assert repo.subtopic_count(version.id) == 1
        assert repo.subtopic_counts_for([version.id]) == {version.id: 1}
        assert len(repo.get_with_tree(version.id).topics) == 1

    def test_the_student_progression_walks_only_what_is_left(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics.pop(0)
        update.topics[0].subtopics.pop(0)
        kept = version.topics[1]
        remaining = kept.subtopics[1].id

        _apply(session, version.id, update)

        walk = CurriculumRepository(session).topics_with_subtopics_in_order(version.id)
        assert walk == [(kept.id, [remaining])]

    def test_a_deleted_name_does_not_block_a_rename_to_it(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics.pop(1)
        _apply(session, version.id, update)

        renamed = CurriculumLibraryService(session).update_topic(
            version.topics[0].id, name="Functions"
        )

        assert renamed.name == "Functions"

    def test_the_active_version_can_be_edited_in_place(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics.pop(1)

        edited = _apply(session, version.id, update)

        assert edited.status is version.status
        assert CurriculumRepository(session).get_approved().id == version.id


class TestAddingBackWhatWasDeleted:
    def test_the_same_name_revives_the_row_it_left(self, session: Session) -> None:
        version = _import(session)
        functions = version.topics[1]
        stable = functions.stable_id
        defining = functions.subtopics[0].id
        update = _tree(version)
        update.topics.pop(1)
        _apply(session, version.id, update)

        back = _tree(session.get(CurriculumVersionRow, version.id))
        back.topics.append(
            TreeTopic(
                name="functions",  # spelled differently: the comparison is on the normalised name
                subtopics=[TreeSubtopic(name="Defining"), TreeSubtopic(name="A new one")],
            )
        )
        edited = _apply(session, version.id, back)

        revived = edited.topics[1]
        assert revived.id == functions.id
        assert revived.stable_id == stable
        assert revived.review_status is CurriculumItemStatus.ACCEPTED
        assert [s.name for s in revived.subtopics] == ["Defining", "A new one"]
        assert revived.subtopics[0].id == defining
        # No second row was made for it.
        assert session.scalar(select(func.count()).select_from(TopicRow)) == 2

    def test_a_subtopic_that_is_not_listed_again_stays_hidden(self, session: Session) -> None:
        version = _import(session)
        functions = version.topics[1]
        update = _tree(version)
        update.topics[1].subtopics.pop(1)
        _apply(session, version.id, update)

        again = _apply(session, version.id, _tree(session.get(CurriculumVersionRow, version.id)))

        assert [s.name for s in again.topics[1].subtopics] == ["Defining"]
        assert len(functions.all_subtopics) == 2


class TestRefusals:
    """Refused in the upload's words, and refused whole."""

    def _refusal(self, session: Session, update: TreeUpdate) -> str:
        with pytest.raises(InvalidTaxonomyDocumentError) as raised:
            CurriculumTreeService(session).apply(_import(session).id, update)
        session.rollback()
        return raised.value.detail or ""

    def test_a_duplicate_topic_name_is_refused_as_an_upload_would_be(
        self, session: Session
    ) -> None:
        update = TreeUpdate(
            label="L",
            topics=[
                TreeTopic(name="Loops", subtopics=[TreeSubtopic(name="a")]),
                TreeTopic(name="loops!", subtopics=[TreeSubtopic(name="b")]),
            ],
        )

        assert ": Value error, duplicate topic name 'loops!'" in self._refusal(session, update)

    def test_a_duplicate_subtopic_name_is_refused_on_its_topic(self, session: Session) -> None:
        update = TreeUpdate(
            label="L",
            topics=[
                TreeTopic(name="A", subtopics=[TreeSubtopic(name="x")]),
                TreeTopic(name="B", subtopics=[TreeSubtopic(name="y"), TreeSubtopic(name="Y")]),
            ],
        )

        assert "topics.1: Value error, duplicate subtopic name 'Y'" in self._refusal(
            session, update
        )

    def test_a_topic_without_subtopics_and_a_blank_name_are_refused(self, session: Session) -> None:
        empty = TreeUpdate(label="L", topics=[TreeTopic(name="A", subtopics=[])])
        assert "topics.0.subtopics: List should have at least 1 item" in self._refusal(
            session, empty
        )
        blank = TreeUpdate(
            label="L", topics=[TreeTopic(name="  ", subtopics=[TreeSubtopic(name="x")])]
        )
        assert "topics.0.name: String should have at least 1 character" in self._refusal(
            session, blank
        )

    def test_a_row_that_is_not_in_this_version_is_refused(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics[0].id = 9999

        with pytest.raises(InvalidTaxonomyDocumentError) as raised:
            CurriculumTreeService(session).apply(version.id, update)

        assert raised.value.detail == "topics.0.id: no topic 9999 in this version"

    def test_a_subtopic_cannot_be_moved_to_another_topic(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        moved = update.topics[0].subtopics.pop(0)
        update.topics[1].subtopics.append(moved)

        with pytest.raises(InvalidTaxonomyDocumentError) as raised:
            CurriculumTreeService(session).apply(version.id, update)

        assert "a subtopic cannot be moved to another topic" in (raised.value.detail or "")

    def test_the_same_row_twice_is_refused(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics[1].subtopics.append(update.topics[1].subtopics[0].model_copy(deep=True))
        update.topics[1].subtopics[-1].name = "Another name"

        with pytest.raises(InvalidTaxonomyDocumentError) as raised:
            CurriculumTreeService(session).apply(version.id, update)

        assert "is listed more than once" in (raised.value.detail or "")

    def test_a_refused_edit_changes_nothing(self, session: Session) -> None:
        version = _import(session)
        update = _tree(version)
        update.topics.pop(1)  # a real change...
        update.topics[0].id = 9999  # ...that makes the whole edit invalid

        with pytest.raises(InvalidTaxonomyDocumentError):
            CurriculumTreeService(session).apply(version.id, update)
        session.rollback()

        fresh = CurriculumRepository(session).get_with_tree(version.id)
        assert [t.name for t in fresh.topics] == ["Loops", "Functions"]

    def test_an_unknown_version_is_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            CurriculumTreeService(session).apply(
                999,
                TreeUpdate(
                    label="L", topics=[TreeTopic(name="A", subtopics=[TreeSubtopic(name="x")])]
                ),
            )


class TestDeletingAVersionForGood:
    def test_it_takes_the_hidden_rows_with_it(self, session: Session) -> None:
        old = _import(session, "Old")
        update = _tree(old)
        update.topics.pop(1)
        update.topics[0].subtopics.pop(0)
        _apply(session, old.id, update)
        _import(session, "Newer")  # becomes the active one, so the first can be deleted
        old_id = old.id

        CurriculumLibraryService(session).delete(old_id)
        session.commit()

        assert (
            session.scalar(
                select(func.count())
                .select_from(TopicRow)
                .where(TopicRow.curriculum_version_id == old_id)
            )
            == 0
        )
        subtopics_left = session.scalar(select(func.count()).select_from(SubtopicRow))
        assert subtopics_left == 4  # only the newer version's


class TestOverTheApi:
    def _create(self, client: TestClient) -> dict:
        response = client.post(
            "/api/curriculum/versions",
            files={"file": ("taxonomy.json", json.dumps(DOCUMENT), "application/json")},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def _body(self, detail: dict) -> dict:
        return {
            "label": detail["version"]["label"],
            "topics": [
                {
                    "id": topic["id"],
                    "name": topic["name"],
                    "description": topic["description"] or "",
                    "subtopics": [
                        {"id": s["id"], "name": s["name"], "description": s["description"] or ""}
                        for s in topic["subtopics"]
                    ],
                }
                for topic in detail["topics"]
            ],
        }

    def test_put_returns_the_edited_tree_with_the_ids_a_client_needs(
        self, client: TestClient
    ) -> None:
        created = self._create(client)
        body = self._body(created)
        body["label"] = "Renamed"
        body["topics"].pop(1)
        body["topics"][0]["subtopics"].append({"name": "do-while", "description": ""})

        response = client.put(
            f"/api/curriculum/versions/{created['version']['id']}/tree", json=body
        )

        assert response.status_code == 200, response.text
        edited = response.json()
        assert edited["version"]["label"] == "Renamed"
        assert edited["topic_count"] == 1 and edited["subtopic_count"] == 3
        assert [s["name"] for s in edited["topics"][0]["subtopics"]] == [
            "for loops",
            "while loops",
            "do-while",
        ]
        assert edited["topics"][0]["id"] == created["topics"][0]["id"]
        assert all(s["id"] for s in edited["topics"][0]["subtopics"])
        # And it is what a later read says, not just what the response said.
        again = client.get(f"/api/curriculum/versions/{created['version']['id']}").json()
        assert again["topic_count"] == 1 and again["subtopic_count"] == 3

    def test_the_version_list_counts_what_is_left(self, client: TestClient) -> None:
        created = self._create(client)
        body = self._body(created)
        body["topics"].pop(1)
        client.put(f"/api/curriculum/versions/{created['version']['id']}/tree", json=body)

        row = client.get("/api/curriculum/versions").json()["versions"][0]

        assert row["topic_count"] == 1 and row["subtopic_count"] == 2

    def test_a_refusal_is_a_422_in_the_uploads_wording(self, client: TestClient) -> None:
        created = self._create(client)
        body = self._body(created)
        body["topics"][1]["name"] = "loops"

        response = client.put(
            f"/api/curriculum/versions/{created['version']['id']}/tree", json=body
        )

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "invalid_taxonomy_document"
        assert "duplicate topic name 'loops'" in error["detail"]

    def test_an_unknown_version_is_a_404(self, client: TestClient) -> None:
        response = client.put(
            "/api/curriculum/versions/999/tree",
            json={"label": "L", "topics": [{"name": "A", "subtopics": [{"name": "x"}]}]},
        )

        assert response.status_code == 404

    def test_an_unknown_field_is_refused(self, client: TestClient) -> None:
        created = self._create(client)
        body = self._body(created)
        body["topics"][0]["colour"] = "red"

        response = client.put(
            f"/api/curriculum/versions/{created['version']['id']}/tree", json=body
        )

        assert response.status_code == 422
