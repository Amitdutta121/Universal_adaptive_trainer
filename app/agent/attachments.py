"""Files the professor attaches in the chat, as the agent's model reads them (ADR-076).

The chat uploads each attachment itself before the message is sent (`onUpload` in the panel)
and tags it in the part's ``metadata``:

- ``course_material``: a book, slides or document, imported as the course's material like an
  upload on the Contents page. The part becomes a note naming the file and its import job, so
  the model knows it was added and reads it with ``read_material`` once the import finishes.
  Sent as is, Pydantic AI would hand the provider a URL it cannot fetch.
- ``text_file``: a small text file (a syllabus, a CSV, a style's YAML), sent as base64 data.
  The part becomes its text, so any model can read it.

Images are left alone: the model sees them when it can. Any other tagged or untagged part
passes through unchanged.
"""

from __future__ import annotations

import base64
import binascii

from ag_ui.core import Message, TextInputContent, UserMessage

#: The longest attached text the model is given; the rest is cut, and the note says so.
MAX_TEXT_CHARS = 60_000


def _note_for(metadata: dict, source) -> str | None:
    kind = metadata.get("kind")
    filename = str(metadata.get("filename") or "a file")
    if kind == "course_material":
        job = metadata.get("job_id")
        return (
            f'[Attached "{filename}": uploaded as course material'
            + (f" (import job {job})" if job else "")
            + ". Once imported it is listed in course_overview; read it with read_material.]"
        )
    if kind == "text_file":
        if getattr(source, "type", None) != "data":
            return f'[Attached "{filename}", but its text did not arrive.]'
        try:
            text = base64.b64decode(source.value).decode("utf-8", errors="replace")
        except (binascii.Error, ValueError):
            return f'[Attached "{filename}", but its text could not be read.]'
        cut = len(text) > MAX_TEXT_CHARS
        body = text[:MAX_TEXT_CHARS]
        tail = f"\n[Cut at {MAX_TEXT_CHARS} characters.]" if cut else ""
        return f'[Attached "{filename}":]\n```\n{body}\n```{tail}'
    return None


def describe_attachments(messages: list[Message]) -> list[Message]:
    """The messages with each tagged attachment part replaced by the text the model should read."""
    described: list[Message] = []
    for message in messages:
        if not isinstance(message, UserMessage) or isinstance(message.content, str):
            described.append(message)
            continue
        parts = []
        changed = False
        for part in message.content:
            metadata = getattr(part, "metadata", None)
            note = (
                _note_for(metadata, getattr(part, "source", None))
                if isinstance(metadata, dict) and getattr(part, "type", "text") != "text"
                else None
            )
            if note is None:
                parts.append(part)
            else:
                parts.append(TextInputContent(type="text", text=note))
                changed = True
        described.append(message.model_copy(update={"content": parts}) if changed else message)
    return described
