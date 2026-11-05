"""The ``video_clip`` renderer contract and the clip recipe (Phase 7, Task 31)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.enums import GuidanceLevel, TutorialBlockStatus, TutorialRenderer, VideoAvailability
from app.errors import DomainRuleError, LLMRequestError
from app.ingestion.youtube import Segment, YouTubeImportService
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    SubtopicRow,
    TopicRow,
    TutorialBlockRow,
)
from app.persistence.repositories import ChunkRepository
from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever
from app.tutorials.clips import CLIP_PAD_SECONDS, clip_payload, course_has_video, playable
from app.tutorials.generator import BlockRequest, generate_block
from app.tutorials.renderers import payload_problems
from app.tutorials.schema import TutorialRecipe
from app.tutorials.serving import servable_recipes
from tests.conftest import TEST_PROFESSOR_ID

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "lecture_transcript.json").read_text(encoding="utf-8")
)
SEGMENTS = [Segment(s["start"], s["duration"], s["text"]) for s in FIXTURE["segments"]]
VIDEO_ID = FIXTURE["video_id"]
CLIP = {"provider": "youtube", "video_id": VIDEO_ID, "start": 10.0, "end": 42.5}


# ------------------------------------------------------------------ contracts


def test_a_clip_payload_names_a_video_and_a_range() -> None:
    assert payload_problems(TutorialRenderer.VIDEO_CLIP, CLIP) == []
    assert payload_problems(TutorialRenderer.VIDEO_CLIP, {**CLIP, "end": 10.0})
    assert payload_problems(TutorialRenderer.VIDEO_CLIP, {**CLIP, "start": -1})
    assert payload_problems(TutorialRenderer.VIDEO_CLIP, {**CLIP, "video_id": 'x" onload=1'})
    assert payload_problems(TutorialRenderer.VIDEO_CLIP, {**CLIP, "provider": "vimeo"})


def _recipe(**fields) -> TutorialRecipe:
    base = {
        "id": "py.x",
        "subject": "intro_python",
        "name": "x",
        "summary": "x",
        "renderer": "video_clip",
        "tool": "video_clip",
        "fits": ["concept"],
        "guidance_levels": ["worked"],
        "inputs": ["subtopic", "chunks"],
    }
    return TutorialRecipe.model_validate({**base, **fields})


def test_the_clip_renderer_and_tool_go_together_and_take_no_prompt() -> None:
    assert _recipe().prompt == ""
    for bad in (
        {"prompt": "Write something."},
        {"tool": None},
        {"renderer": "markdown"},
        {"renderer": "markdown", "tool": None},  # an ordinary recipe still needs its prompt
    ):
        with pytest.raises(ValidationError):
            _recipe(**bad)


# ------------------------------------------------------------------ the clip recipe


class LoopEmbedder:
    VOCAB = ("while", "range", "accumulator", "total", "condition", "for")
    model = "loop-v1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(t.lower().count(word)) + 0.01 for word in self.VOCAB] for t in texts]


class NoModel:
    description = "never/called"

    def complete_structured(self, **_kwargs):
        raise AssertionError("the model must not be called here")


class LectureModel:
    """Writes the clip's lecture-style query; records each prompt."""

    description = "fake/lecture"
    PASSAGE = "So a while loop checks its condition, and while the condition holds it runs again."

    def __init__(self, before_call=None) -> None:
        self.prompts: list[str] = []
        self.before_call = before_call

    def complete_structured(self, *, prompt: str, response_model, **_kwargs):
        if self.before_call is not None:
            self.before_call()
        self.prompts.append(prompt)
        return response_model(text=self.PASSAGE)


class DownModel:
    description = "fake/down"

    def complete_structured(self, **_kwargs):
        raise LLMRequestError("The model provider could not be reached.")


class SpyEmbedder(LoopEmbedder):
    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return super().embed(texts)


def _video(session: Session, availability=VideoAvailability.AVAILABLE):
    book = YouTubeImportService(
        session, fetch=lambda _id: SEGMENTS, check=lambda _id: (availability, "Loops")
    ).import_video(VIDEO_ID)
    session.commit()
    return book


def _subtopic(session: Session) -> SubtopicRow:
    version = CurriculumVersionRow(label="Intro")
    topic = TopicRow(
        name="Loops",
        subtopics=[SubtopicRow(name="while loops", description="the while loop condition")],
    )
    version.topics.append(topic)
    session.add(version)
    session.commit()
    return topic.subtopics[0]


def _generate(
    session: Session, subtopic: SubtopicRow, client=None, embedder=None
) -> TutorialBlockRow:
    return generate_block(
        session,
        BlockRequest(subtopic.id, "py.video_clip", GuidanceLevel.WORKED),
        client=client if client is not None else LectureModel(),
        retriever=ChunkRetriever(session, ChunkEmbeddingStore(session, embedder or LoopEmbedder())),
    )


def test_the_clip_is_the_chunk_that_explains_the_subtopic_padded(session: Session) -> None:
    book = _video(session)
    block = _generate(session, _subtopic(session))

    assert block.status is TutorialBlockStatus.DRAFT
    assert block.renderer is TutorialRenderer.VIDEO_CLIP
    assert block.model == "fake/lecture"
    (chunk_id,) = block.chunk_ids
    chunk = ChunkRepository(session).get_many([chunk_id])[chunk_id]
    assert chunk.book_id == book.id
    assert "while loop" in chunk.text.lower()
    assert block.payload == {
        "provider": "youtube",
        "video_id": VIDEO_ID,
        "start": round(chunk.start_seconds - CLIP_PAD_SECONDS, 2),
        "end": round(chunk.end_seconds + CLIP_PAD_SECONDS, 2),
        "title": "Loops",
        "transcript": chunk.text,
    }
    # Sentence boundaries: the clip's words start a sentence and end one.
    assert chunk.text[0].isupper() and chunk.text.rstrip()[-1] in ".?!"


def test_the_first_clip_of_a_video_is_not_padded_below_zero(session: Session) -> None:
    book = _video(session)
    first = ChunkRepository(session).list_for_book(book.id)[0]
    first.start_seconds = 0.4

    assert clip_payload(first)["start"] == 0.0


def test_the_search_query_is_the_subtopic_plus_a_lecture_style_passage(
    session: Session,
) -> None:
    _video(session)
    model, embedder = LectureModel(), SpyEmbedder()
    _generate(session, _subtopic(session), client=model, embedder=embedder)

    (prompt,) = model.prompts
    assert "Loops - while loops: the while loop condition" in prompt
    query = embedder.texts[-1]  # the chunks are embedded first, the query last
    assert query == f"Loops - while loops: the while loop condition\n\n{LectureModel.PASSAGE}"


def test_a_failed_model_call_falls_back_to_the_subtopic_text(session: Session) -> None:
    _video(session)
    embedder = SpyEmbedder()
    block = _generate(session, _subtopic(session), client=DownModel(), embedder=embedder)

    assert block.status is TutorialBlockStatus.DRAFT
    assert block.model == ""
    assert embedder.texts[-1] == "Loops - while loops: the while loop condition"


def test_the_lecture_query_holds_no_write_lock(session: Session) -> None:
    """ADR-071: the model call runs with nothing pending, so others can still write."""
    _video(session)
    subtopic = _subtopic(session)
    path = session.get_bind().url.database
    blocked: list[bool] = []

    def probe() -> None:
        other = sqlite3.connect(path, timeout=0.05, isolation_level=None)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.execute("ROLLBACK")
            blocked.append(False)
        except sqlite3.OperationalError:
            blocked.append(True)
        finally:
            other.close()

    _generate(session, subtopic, client=LectureModel(before_call=probe))
    assert blocked == [False]


def test_no_playable_video_means_no_clip_and_no_model_call(session: Session) -> None:
    subtopic = _subtopic(session)
    with pytest.raises(DomainRuleError, match="YouTube"):
        _generate(session, subtopic, client=NoModel())

    # Imported while playable, then flagged by the periodic check.
    _video(session).video_availability = VideoAvailability.NOT_EMBEDDABLE
    session.commit()
    with pytest.raises(DomainRuleError):
        _generate(session, subtopic, client=NoModel())


def test_clips_of_a_video_that_went_away_are_not_served(session: Session) -> None:
    book = _video(session)
    clip = _generate(session, _subtopic(session))
    other = TutorialBlockRow(renderer=TutorialRenderer.MARKDOWN, payload={"markdown": "x"})

    assert playable(session, [clip, other]) == [clip, other]
    book.video_availability = VideoAvailability.UNAVAILABLE
    session.flush()
    assert playable(session, [clip, other]) == [other]


def test_the_clip_recipe_is_served_only_in_a_course_with_a_playable_video(
    session: Session,
) -> None:
    course = CourseRow(name="C", subject="intro_python", owner_id=TEST_PROFESSOR_ID)
    session.add(course)
    session.commit()
    version_id = _subtopic(session).topic.curriculum_version_id

    def served() -> set[str]:
        return set(servable_recipes(session, "intro_python", course.id, version_id))

    assert not course_has_video(session, course.id)
    assert "py.video_clip" not in served()
    assert "py.misconception_line" in served()

    book = _video(session)
    book.course_id = course.id
    session.commit()
    assert "py.video_clip" in served()

    book.video_availability = VideoAvailability.NOT_EMBEDDABLE
    session.commit()
    assert "py.video_clip" not in served()
