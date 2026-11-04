"""The tutorial block generator (Phase 5, Task 21)."""

from __future__ import annotations

import json
from typing import Any

import book_documents as docs
import pytest
from llm_fakes import as_live
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.enums import GuidanceLevel, TutorialBlockStatus, TutorialRenderer
from app.errors import DomainRuleError, MalformedModelOutputError
from app.persistence.models import CurriculumVersionRow, SubtopicRow, TopicRow
from app.retrieval.chunks import RetrievedChunk
from app.tutorials.generator import BlockRequest, generate_block, get_recipes
from app.tutorials.html_check import HtmlCheckUnavailable
from app.tutorials.renderers import StepperDraft, payload_problems
from app.tutorials.tools.python_trace import python_trace

PROGRAM = "total = 0\nfor n in [2, 3]:\n    total = total + n\nprint(total)\n"


class QueuedClient:
    """Answers each structured call with the next queued reply (a dict, or an exception)."""

    description = "fake/tutor"

    def __init__(self, *replies: dict[str, Any] | Exception) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
        history: tuple[tuple[str, str], ...] = (),
    ) -> BaseModel:
        self.calls.append({"prompt": prompt, "history": history, "model": response_model})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return as_live(response_model.model_validate(reply))


class BookRetriever:
    """Returns every chunk of the stored book, as ``for_subtopic`` would rank them."""

    def __init__(self, book: Any) -> None:
        self.book = book

    def for_subtopic(self, subtopic_id: int, *, top_k: int = 5) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                book_id=chunk.book_id,
                book_title="Think Python",
                heading_path=list(chunk.heading_path),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                score=1.0,
                snippet=chunk.text[:300],
            )
            for chunk in self.book.chunks[:top_k]
        ]


class NoChunks:
    def for_subtopic(self, subtopic_id: int, *, top_k: int = 5) -> list[RetrievedChunk]:
        return []


@pytest.fixture
def setting(session: Session) -> tuple[SubtopicRow, BookRetriever]:
    book = docs.chunked_book(session, docs.think_python())
    version = CurriculumVersionRow(label="Intro")
    topic = TopicRow(name="Loops", subtopics=[SubtopicRow(name="for loops")])
    version.topics.append(topic)
    session.add(version)
    session.commit()
    return topic.subtopics[0], BookRetriever(book)


def _generate(session: Session, setting: Any, client: QueuedClient, **request: Any) -> Any:
    subtopic, retriever = setting
    request.setdefault("guidance_level", GuidanceLevel.WORKED)
    return generate_block(
        session,
        BlockRequest(subtopic_id=subtopic.id, **request),
        client=client,
        retriever=retriever,
    )


def test_markdown_block_is_saved_with_its_chunks(session: Session, setting: Any) -> None:
    client = QueuedClient({"markdown": "**Misconception:** `range(3)` includes 3."})
    block = _generate(session, setting, client, recipe_id="py.misconception_line")
    assert block.status is TutorialBlockStatus.DRAFT
    assert block.renderer is TutorialRenderer.MARKDOWN
    assert block.payload == {"markdown": "**Misconception:** `range(3)` includes 3."}
    assert block.chunk_ids == [chunk.chunk_id for chunk in setting[1].for_subtopic(0, top_k=4)]
    assert block.model == "fake/tutor"
    (call,) = client.calls
    assert "Guidance level: WORKED" in call["prompt"]
    assert "Loops - for loops" in call["prompt"]
    assert "Book excerpts:" in call["prompt"] and "[1] " in call["prompt"]


def test_the_stepper_embeds_the_recorded_trace_not_the_models(
    session: Session, setting: Any
) -> None:
    # The model may try to supply its own run; the draft has no place for one, and the
    # payload's trace is exactly python_trace's.
    client = QueuedClient(
        {
            "title": "Adding up a list",
            "code": PROGRAM,
            "notes": [{"line": 3, "note": "Adds n to the running total."}],
            "trace": [{"line": 99, "event": "line", "function": "x", "locals": {"total": "42"}}],
        }
    )
    block = _generate(session, setting, client, recipe_id="py.code_trace_stepper")
    assert client.calls[0]["model"] is StepperDraft
    assert block.status is TutorialBlockStatus.DRAFT
    recorded = [step.model_dump() for step in python_trace(PROGRAM).steps]
    assert block.payload["trace"] == recorded
    assert block.payload["code"] == PROGRAM
    html = block.payload["html"]
    embedded = html.split('<script type="application/json" id="data">', 1)[1].split("</script>")[0]
    assert json.loads(embedded)["trace"] == recorded
    assert "42" not in embedded
    assert payload_problems(TutorialRenderer.HTML, block.payload) == []


def test_given_code_is_traced_before_the_call_and_the_models_code_ignored(
    session: Session, setting: Any
) -> None:
    client = QueuedClient(
        {"title": "T", "code": "print('other')\n", "notes": [{"line": 4, "note": "Prints 5."}]}
    )
    block = _generate(session, setting, client, recipe_id="py.code_trace_stepper", code=PROGRAM)
    assert block.payload["code"] == PROGRAM
    assert "Use exactly this program" in client.calls[0]["prompt"]
    assert "  4| print(total)" in client.calls[0]["prompt"]


def test_an_invalid_payload_gets_one_repair_retry(session: Session, setting: Any) -> None:
    client = QueuedClient(
        {"mermaid": "A --> B", "caption": "c"},
        {"mermaid": 'flowchart TD\n  A["for"] --> B["body"]', "caption": "c"},
    )
    block = _generate(session, setting, client, recipe_id="py.topic_flow")
    assert block.status is TutorialBlockStatus.DRAFT
    assert len(client.calls) == 2
    retry = client.calls[1]
    assert "must start with a Mermaid diagram type" in retry["prompt"]
    assert [role for role, _ in retry["history"]] == ["user", "assistant"]
    assert "A --> B" in retry["history"][1][1]


def test_escaped_quotes_in_a_diagram_label_are_repaired(session: Session, setting: Any) -> None:
    # Seen live: the model wrote A["\"Literal constants\""], which Mermaid cannot draw.
    client = QueuedClient(
        {"mermaid": 'flowchart TD\n  A["\\"for\\""] --> B["body"]', "caption": "c"},
        {"mermaid": 'flowchart TD\n  A["for"] --> B["body"]', "caption": "c"},
    )
    block = _generate(session, setting, client, recipe_id="py.topic_flow")
    assert block.status is TutorialBlockStatus.DRAFT
    assert 'labels may not contain \\"' in client.calls[1]["prompt"]


def test_a_second_invalid_payload_marks_the_block_failed(session: Session, setting: Any) -> None:
    broken = {"title": "T", "code": "print(1 / 0)\n", "notes": []}
    client = QueuedClient(broken, broken)
    block = _generate(session, setting, client, recipe_id="py.code_trace_stepper")
    assert len(client.calls) == 2
    assert block.status is TutorialBlockStatus.FAILED
    assert block.payload == {}
    assert block.error is not None and "ZeroDivisionError" in block.error
    assert block.chunk_ids  # a failed block still records what it was written from


def test_an_unreadable_reply_counts_as_the_one_retry(session: Session, setting: Any) -> None:
    client = QueuedClient(
        MalformedModelOutputError("bad", detail="not json"), MalformedModelOutputError("bad")
    )
    block = _generate(session, setting, client, recipe_id="py.misconception_line")
    assert len(client.calls) == 2
    assert block.status is TutorialBlockStatus.FAILED
    assert "did not match the requested structure" in (block.error or "")


def test_requests_the_recipe_cannot_serve_are_refused(session: Session, setting: Any) -> None:
    client = QueuedClient()
    with pytest.raises(DomainRuleError, match="worked, faded"):
        _generate(
            session,
            setting,
            client,
            recipe_id="py.code_trace_stepper",
            guidance_level=GuidanceLevel.CUE,
        )
    with pytest.raises(DomainRuleError, match="does not take code"):
        _generate(session, setting, client, recipe_id="py.topic_flow", code=PROGRAM)
    with pytest.raises(DomainRuleError, match="does not run"):
        _generate(session, setting, client, recipe_id="py.code_trace_stepper", code="1/0\n")
    subtopic, _ = setting
    with pytest.raises(DomainRuleError, match="No book text"):
        generate_block(
            session,
            BlockRequest(subtopic.id, "py.topic_flow", GuidanceLevel.CUE),
            client=client,
            retriever=NoChunks(),  # type: ignore[arg-type]
        )
    assert client.calls == []


def test_the_seed_recipes_are_offered_for_intro_python() -> None:
    assert {recipe.id for recipe in get_recipes("intro_python")} == {
        "py.code_trace_stepper",
        "py.topic_flow",
        "py.misconception_line",
        "py.video_clip",
    }
    assert get_recipes("no_such_subject") == []


def test_an_html_block_that_fails_its_check_is_retried_then_failed(
    session: Session, setting: Any
) -> None:
    draft = {"title": "T", "code": PROGRAM, "notes": []}
    client = QueuedClient(draft, draft)
    seen: list[list[Any]] = []

    def failing_check(payload: dict[str, Any], checks: list[Any]) -> list[str]:
        seen.append(checks)
        return ["console error: boom"]

    subtopic, retriever = setting
    block = generate_block(
        session,
        BlockRequest(subtopic.id, "py.code_trace_stepper", GuidanceLevel.WORKED),
        client=client,
        retriever=retriever,
        html_check=failing_check,
    )
    assert len(client.calls) == 2 and len(seen) == 2
    assert [check.value for check in seen[0]] == ["html_loads", "trace_matches"]
    assert block.status is TutorialBlockStatus.FAILED
    assert block.error == "console error: boom"


def test_without_a_browser_an_html_block_fails_without_a_retry(
    session: Session, setting: Any
) -> None:
    def unavailable(payload: dict[str, Any], checks: list[Any]) -> list[str]:
        raise HtmlCheckUnavailable("html blocks cannot be checked: no browser")

    client = QueuedClient({"title": "T", "code": PROGRAM, "notes": []})
    subtopic, retriever = setting
    block = generate_block(
        session,
        BlockRequest(subtopic.id, "py.code_trace_stepper", GuidanceLevel.WORKED),
        client=client,
        retriever=retriever,
        html_check=unavailable,
    )
    assert len(client.calls) == 1
    assert block.status is TutorialBlockStatus.FAILED
    assert block.error == "html blocks cannot be checked: no browser"
