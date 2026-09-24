"""Editing a version's tree in place: rename, add, reorder, and soft-delete (ADR-050).

Until ADR-050 a saved taxonomy could only be renamed; changing its shape meant making a new
version (ADR-046). This is the other half. A professor hands over the tree as they now want it,
each row carrying the id it already has (or none, if it is new), and the version is brought to
match:

* a row that is listed keeps its id, takes the new name, description and position, and is
  restored if it had been deleted;
* a row that is new is created, unless a deleted row in the same place had the same name, in
  which case that row comes back, because two rows cannot share a ``stable_id``;
* a row that is no longer listed is **soft-deleted**: its ``review_status`` becomes ``DELETED``
  and nothing else about it changes. ``version.topics`` and ``topic.subtopics`` leave it out,
  but a question, a student's measured weakness or a frozen question set that points at it still
  resolves. Nothing here checks for those, or clears them: the professor removing a topic knows
  what they are removing.

A subtopic is never moved to another topic by this: a subtopic id has to arrive under the topic
that owns it. (Moving one would change what every question and measurement recorded against it
means, which is exactly the thing soft deletion is not for.)

The rules that make a taxonomy valid -- a name on everything, no duplicate names among siblings,
at least one subtopic per topic, the length limits -- are the upload's, applied by building the
document the edit describes and validating that, so an edit is refused in the same words an
upload would be.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.curriculum.stable_ids import normalize_label
from app.curriculum.taxonomy_ids import subtopic_id_from_names, topic_id_from_name
from app.curriculum.taxonomy_schema import (
    DESCRIPTION_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SCHEMA_VERSION,
    TaxonomyTopic,
    validate_taxonomy_payload,
)
from app.domain.enums import CurriculumItemStatus
from app.errors import InvalidTaxonomyDocumentError
from app.persistence.models import CurriculumVersionRow, SubtopicRow, TopicRow
from app.persistence.repositories import CurriculumRepository

logger = logging.getLogger(__name__)

Row = TypeVar("Row", TopicRow, SubtopicRow)


class TreeSubtopic(BaseModel):
    """One subtopic as the professor now wants it. ``id`` is absent for a new one."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    name: str = Field(max_length=NAME_MAX_LENGTH + 100)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH + 100)


class TreeTopic(BaseModel):
    """One topic as the professor now wants it, with its subtopics in the order they should read."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    name: str = Field(max_length=NAME_MAX_LENGTH + 100)
    description: str = Field(default="", max_length=DESCRIPTION_MAX_LENGTH + 100)
    subtopics: list[TreeSubtopic]


class TreeUpdate(BaseModel):
    """The whole tree of a version as it should be after the edit, and its label.

    The size limits here are deliberately looser than the schema's: they only stop an absurd body
    from being read, and the real limits are applied by the taxonomy document, so that the
    refusal reads exactly as an upload's would.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = Field(max_length=LABEL_MAX_LENGTH + 100)
    topics: list[TreeTopic]


def _refuse(path: str, message: str) -> InvalidTaxonomyDocumentError:
    return InvalidTaxonomyDocumentError(
        "The taxonomy edit did not satisfy the schema.", detail=f"{path}: {message}"
    )


class CurriculumTreeService:
    """Bring a version's tree to match an edit, soft-deleting what it leaves out."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._curriculum = CurriculumRepository(session)

    def apply(self, version_id: int, update: TreeUpdate) -> CurriculumVersionRow:
        """Apply ``update`` to the version, or change nothing.

        Raises:
            NotFoundError: no such version.
            InvalidTaxonomyDocumentError: the tree breaks a taxonomy rule, or names a row that
                is not in this version, or would move a subtopic to another topic.
        """
        version = self._curriculum.get_version(version_id)
        document = validate_taxonomy_payload(
            {
                "schema_version": SCHEMA_VERSION,
                "label": update.label,
                "topics": [
                    {
                        "name": topic.name,
                        "description": topic.description,
                        "subtopics": [
                            {"name": sub.name, "description": sub.description}
                            for sub in topic.subtopics
                        ],
                    }
                    for topic in update.topics
                ],
            }
        )

        rows = list(version.all_topics)
        visible = {row.id: row for row in rows if _is_visible(row)}
        claimed = {topic.id for topic in update.topics if topic.id is not None}
        by_name = _by_name(rows, claimed)
        kept: set[int] = set()

        for position, (incoming, named) in enumerate(
            zip(update.topics, document.topics, strict=True)
        ):
            topic = self._topic_row(version, visible, by_name, kept, incoming, position)
            topic.name = named.name
            topic.description = named.description or None
            topic.position = position
            self._reconcile_subtopics(topic, incoming, named, position)

        for row in visible.values():
            if row.id not in kept:
                row.review_status = CurriculumItemStatus.DELETED

        version.label = document.label
        self._session.flush()
        logger.info("Edited the tree of curriculum version %s in place", version.id)
        return version

    # ---- topics ---------------------------------------------------------------------------

    def _topic_row(
        self,
        version: CurriculumVersionRow,
        visible: dict[int, TopicRow],
        by_name: dict[str, TopicRow],
        kept: set[int],
        incoming: TreeTopic,
        position: int,
    ) -> TopicRow:
        if incoming.id is not None:
            row = visible.get(incoming.id)
            if row is None or incoming.id in kept:
                raise _refuse(
                    f"topics.{position}.id",
                    f"no topic {incoming.id} in this version"
                    if row is None
                    else f"topic {incoming.id} is listed more than once",
                )
            kept.add(row.id)
            return row

        # No id: this is a new row, unless a row of that name is already there to be reused (a
        # hidden one is brought back; a visible one that this edit does not otherwise claim is
        # simply the same row, and is not deleted only to be created again).
        matched = by_name.pop(normalize_label(incoming.name), None)
        if matched is not None:
            matched.review_status = CurriculumItemStatus.ACCEPTED
            kept.add(matched.id)
            visible[matched.id] = matched
            return matched

        created = TopicRow(
            curriculum_version_id=version.id,
            name=incoming.name,
            position=position,
            stable_id=topic_id_from_name(incoming.name),
            review_status=CurriculumItemStatus.ACCEPTED,
        )
        self._session.add(created)
        self._session.flush()
        kept.add(created.id)
        visible[created.id] = created
        return created

    # ---- subtopics ------------------------------------------------------------------------

    def _reconcile_subtopics(
        self, topic: TopicRow, incoming: TreeTopic, named: TaxonomyTopic, topic_position: int
    ) -> None:
        rows = list(topic.all_subtopics)
        visible = {row.id: row for row in rows if _is_visible(row)}
        claimed = {sub.id for sub in incoming.subtopics if sub.id is not None}
        by_name = _by_name(rows, claimed)
        kept: set[int] = set()

        for position, (sub_in, sub_named) in enumerate(
            zip(incoming.subtopics, named.subtopics, strict=True)
        ):
            path = f"topics.{topic_position}.subtopics.{position}.id"
            if sub_in.id is not None:
                row = visible.get(sub_in.id)
                if row is None or sub_in.id in kept:
                    raise _refuse(
                        path,
                        f"no subtopic {sub_in.id} under this topic (a subtopic cannot be moved "
                        "to another topic)"
                        if row is None
                        else f"subtopic {sub_in.id} is listed more than once",
                    )
            else:
                row = by_name.pop(normalize_label(sub_named.name), None)
                if row is not None:
                    row.review_status = CurriculumItemStatus.ACCEPTED
                else:
                    row = SubtopicRow(
                        topic_id=topic.id,
                        name=sub_named.name,
                        stable_id=subtopic_id_from_names(topic.name, sub_named.name),
                        review_status=CurriculumItemStatus.ACCEPTED,
                        candidate_labels=[],
                    )
                    self._session.add(row)
                    self._session.flush()
            row.name = sub_named.name
            row.description = sub_named.description or None
            row.position = position
            kept.add(row.id)

        for row in visible.values():
            if row.id not in kept:
                row.review_status = CurriculumItemStatus.DELETED


def _is_visible(row: TopicRow | SubtopicRow) -> bool:
    return row.review_status is not CurriculumItemStatus.DELETED


def _by_name(rows: Sequence[Row], claimed: set[int]) -> dict[str, Row]:
    """Rows an edit may reuse for an entry that arrives without an id, by normalised name.

    Rows the edit already names by id are not offered, and a visible row wins over a hidden
    one of the same name.
    """
    hidden = {
        normalize_label(r.name): r for r in rows if not _is_visible(r) and r.id not in claimed
    }
    shown = {normalize_label(r.name): r for r in rows if _is_visible(r) and r.id not in claimed}
    return {**hidden, **shown}


__all__ = ["CurriculumTreeService", "TreeSubtopic", "TreeTopic", "TreeUpdate"]
