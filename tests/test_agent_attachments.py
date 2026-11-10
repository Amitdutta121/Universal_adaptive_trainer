"""Files attached in the chat, as the agent's model receives them (ADR-076)."""

from __future__ import annotations

import base64
import json

from ag_ui.core import UserMessage

from app.agent.attachments import MAX_TEXT_CHARS, describe_attachments
from app.web.routes.api.agent import CopilotKitAGUIAdapter


def _user(*parts: dict) -> UserMessage:
    return UserMessage.model_validate({"id": "m1", "role": "user", "content": list(parts)})


TEXT = {"type": "text", "text": "Use this for the curriculum."}
MATERIAL = {
    "type": "document",
    "source": {"type": "url", "value": "/courses/3/books", "mimeType": "application/pdf"},
    "metadata": {"kind": "course_material", "job_id": "book-7", "filename": "Think Python.pdf"},
}


def _text_file(text: str) -> dict:
    return {
        "type": "document",
        "source": {
            "type": "data",
            "value": base64.b64encode(text.encode()).decode(),
            "mimeType": "text/plain",
        },
        "metadata": {"kind": "text_file", "filename": "syllabus.txt"},
    }


def test_course_material_becomes_a_note_naming_the_file_and_its_import() -> None:
    [message] = describe_attachments([_user(TEXT, MATERIAL)])
    texts = [part.text for part in message.content]
    assert texts[0] == TEXT["text"]
    assert '"Think Python.pdf"' in texts[1] and "book-7" in texts[1]
    assert "course_overview" in texts[1]


def test_a_text_file_becomes_its_text_cut_at_the_limit() -> None:
    [short] = describe_attachments([_user(_text_file("Week 1: variables"))])
    assert "Week 1: variables" in short.content[0].text

    [long] = describe_attachments([_user(_text_file("x" * (MAX_TEXT_CHARS + 10)))])
    assert long.content[0].text.split("```")[1].strip() == "x" * MAX_TEXT_CHARS
    assert "Cut at" in long.content[0].text


def test_images_and_plain_messages_pass_through() -> None:
    image = {
        "type": "image",
        "source": {"type": "data", "value": "aGk=", "mimeType": "image/png"},
    }
    plain = UserMessage(id="m2", role="user", content="hello")
    first, second = describe_attachments([_user(TEXT, image), plain])
    assert first.content[1].type == "image"
    assert second is plain


def test_the_agent_route_rewrites_attachments_before_the_run() -> None:
    body = json.dumps(
        {
            "threadId": "t1",
            "runId": "r1",
            "state": {},
            "messages": [{"id": "m1", "role": "user", "content": [TEXT, MATERIAL]}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }
    ).encode()
    run_input = CopilotKitAGUIAdapter.build_run_input(body)
    assert [part.type for part in run_input.messages[0].content] == ["text", "text"]
