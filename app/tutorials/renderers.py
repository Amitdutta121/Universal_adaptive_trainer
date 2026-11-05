"""Payload contracts of the trusted renderers, and the code-trace stepper's html (Task 21).

Each renderer draws one payload shape (``frontend/src/components/tutorial/``). The model writes a
*draft*; the generator turns it into the payload and :func:`payload_problems` checks the payload
before it is saved. The stepper's html is not written by the model at all: it is this module's
template, filled with the code, the recorded trace (``python_trace``) and the model's notes as
JSON and drawn with ``textContent``, so no model text is ever parsed as html.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.domain.enums import TutorialRenderer
from app.tutorials.tools.python_trace import TraceStep

# ------------------------------------------------------------------ payloads


class MarkdownPayload(BaseModel):
    markdown: str = Field(min_length=1)


class MermaidPayload(BaseModel):
    #: Mermaid source. The frontend renders it with ``securityLevel: "strict"``.
    mermaid: str = Field(min_length=1)
    caption: str = ""


class ChartDataset(BaseModel):
    label: str
    data: list[float] = Field(min_length=1)


class ChartData(BaseModel):
    labels: list[str] = Field(min_length=1)
    datasets: list[ChartDataset] = Field(min_length=1)


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "pie", "doughnut", "scatter"]
    data: ChartData


class ChartPayload(BaseModel):
    chart: ChartSpec
    caption: str = ""


class HtmlPayload(BaseModel):
    #: A whole html document, run in ``<iframe sandbox="allow-scripts">`` under a CSP that
    #: blocks the network.
    html: str = Field(min_length=1)
    title: str = ""


class LineNote(BaseModel):
    line: int = Field(ge=1)
    note: str = Field(min_length=1)


class StepperPayload(HtmlPayload):
    """An html block of the code-trace stepper: ``html`` is :func:`stepper_html` of the rest."""

    code: str = Field(min_length=1)
    #: Exactly ``python_trace``'s steps, never the model's.
    trace: list[TraceStep] = Field(min_length=1)
    notes: list[LineNote] = Field(default_factory=list)


class VideoClipPayload(BaseModel):
    """A range of a YouTube video, played through the IFrame API (Task 31).

    ``start``/``end`` are seconds, on sentence boundaries of the transcript and padded a little.
    ``transcript`` is what is said in the range; the block never describes what is on screen,
    because nothing here has seen the picture.
    """

    provider: Literal["youtube"] = "youtube"
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    start: float = Field(ge=0)
    end: float
    title: str = ""
    transcript: str = ""

    @model_validator(mode="after")
    def _a_range(self) -> VideoClipPayload:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


_CONTRACTS: dict[TutorialRenderer, type[BaseModel]] = {
    TutorialRenderer.MARKDOWN: MarkdownPayload,
    TutorialRenderer.MERMAID: MermaidPayload,
    TutorialRenderer.CHARTJS: ChartPayload,
    TutorialRenderer.HTML: HtmlPayload,
    TutorialRenderer.VIDEO_CLIP: VideoClipPayload,
}

#: First keyword of every Mermaid diagram type a tutorial may use.
_MERMAID_KINDS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "mindmap",
    "timeline",
)
#: Mermaid directives that reach outside the diagram: links, callbacks, init overrides.
_MERMAID_FORBIDDEN = re.compile(r"^\s*(click|%%\{)|javascript:|<script", re.IGNORECASE | re.M)


def payload_problems(renderer: TutorialRenderer, payload: dict[str, Any]) -> list[str]:
    """Why ``payload`` cannot be drawn by ``renderer``, as plain sentences; ``[]`` if it can."""
    try:
        _CONTRACTS[renderer].model_validate(payload)
    except ValidationError as exc:
        return [
            f"field '{'.'.join(str(part) for part in error['loc'])}': {error['msg']}"
            for error in exc.errors()
        ]
    problems: list[str] = []
    if renderer is TutorialRenderer.MERMAID:
        source = payload["mermaid"].strip()
        first = source.split(None, 1)[0] if source else ""
        if first not in _MERMAID_KINDS:
            problems.append(
                f"the diagram must start with a Mermaid diagram type ({', '.join(_MERMAID_KINDS)})"
            )
        if _MERMAID_FORBIDDEN.search(source):
            problems.append("the diagram may not use click, init directives, links or scripts")
        if '\\"' in source:
            # Mermaid has no backslash escapes: A["\"x\""] does not parse, and the student
            # would see the source instead of the diagram.
            problems.append(
                'labels may not contain \\" (Mermaid has no escapes); write A["label"], '
                "and #quot; for a quote inside a label"
            )
    return problems


# ------------------------------------------------------------------ drafts (what the model writes)


class StepperDraft(BaseModel):
    """What the model writes for the stepper. ``code`` is ignored when the caller gave code."""

    title: str = Field(min_length=1)
    code: str = Field(default="", description="The Python program, when no code was given.")
    notes: list[LineNote] = Field(
        default_factory=list, description="One-sentence notes on the lines worth explaining."
    )


def stepper_problems(
    code: str, trace_error: str | None, steps: int, notes: list[LineNote]
) -> list[str]:
    """Why a stepper cannot be built from this code, run and notes."""
    problems: list[str] = []
    if trace_error is not None:
        problems.append(
            f"the code must run to the end without errors; running it gave: {trace_error}"
        )
    elif steps == 0:
        problems.append("the code must run at least one line")
    lines = len(code.splitlines())
    for note in notes:
        if note.line > lines:
            problems.append(f"a note is on line {note.line} but the code has {lines} lines")
    return problems


# ------------------------------------------------------------------ the stepper's html

_STEPPER_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  body { font: 14px/1.45 system-ui, sans-serif; margin: 0; padding: 12px; color: #1f2328; }
  h1 { font-size: 15px; margin: 0 0 8px; }
  .grid { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 12px; }
  ol#code { font: 13px/1.5 ui-monospace, monospace; margin: 0; padding: 6px 0 6px 2.6em;
    overflow-x: auto;
    background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; }
  ol#code li { white-space: pre; padding: 0 6px; }
  ol#code li.current { background: #fff8c5; outline: 1px solid #d4a72c; }
  table { border-collapse: collapse; width: 100%; font: 13px ui-monospace, monospace; }
  td, th { border-bottom: 1px solid #d0d7de; padding: 2px 6px; text-align: left; }
  pre#stdout { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px;
    padding: 6px; min-height: 2em; margin: 0; white-space: pre-wrap; }
  .controls { display: flex; gap: 8px; align-items: center; margin: 8px 0; }
  #note { min-height: 1.4em; color: #59636e; }
  h2 { font-size: 12px; text-transform: uppercase; color: #59636e; margin: 8px 0 4px; }
  @media (max-width: 520px) { .grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<h1 id="title"></h1>
<div class="controls">
  <button id="prev" type="button">Back</button>
  <button id="next" type="button">Next</button>
  <span id="position" aria-live="polite"></span>
</div>
<p id="note"></p>
<div class="grid">
  <ol id="code"></ol>
  <div>
    <h2>Variables</h2>
    <table><tbody id="locals"></tbody></table>
    <h2>Output</h2>
    <pre id="stdout"></pre>
  </div>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("data").textContent);
  var steps = data.trace, notes = {}, i = 0;
  data.notes.forEach(function (n) { notes[n.line] = n.note; });
  document.getElementById("title").textContent = data.title;
  var code = document.getElementById("code");
  data.code.split("\\n").forEach(function (text, n) {
    var li = document.createElement("li");
    li.textContent = text || " ";
    li.setAttribute("data-line", String(n + 1));
    code.appendChild(li);
  });
  function describe(step) {
    if (step.event === "call") return "Calling " + step.function + "()";
    if (step.event === "return") return step.function + "() returns " + step.value;
    if (step.event === "exception") return "Error: " + step.value;
    if (step.event === "end") return "The program has finished";
    return notes[step.line] || "";
  }
  function show() {
    var step = steps[i];
    var position = document.getElementById("position");
    position.textContent = "Step " + (i + 1) + " of " + steps.length + ", line " + step.line;
    position.setAttribute("data-step", String(i));
    position.setAttribute("data-line", String(step.line));
    Array.prototype.forEach.call(code.children, function (li) {
      li.className = li.getAttribute("data-line") === String(step.line) ? "current" : "";
    });
    var body = document.getElementById("locals");
    body.textContent = "";
    Object.keys(step.locals).forEach(function (name) {
      var tr = document.createElement("tr");
      var k = document.createElement("td"), v = document.createElement("td");
      k.textContent = name; v.textContent = step.locals[name];
      tr.setAttribute("data-name", name);
      tr.appendChild(k); tr.appendChild(v); body.appendChild(tr);
    });
    document.getElementById("stdout").textContent = step.stdout;
    document.getElementById("note").textContent = describe(step);
    document.getElementById("prev").disabled = i === 0;
    document.getElementById("next").disabled = i === steps.length - 1;
    resize();
  }
  function resize() {
    if (window.parent !== window) {
      var height = document.documentElement.scrollHeight;
      window.parent.postMessage({ type: "tutorial-block-resize", height: height }, "*");
    }
  }
  document.getElementById("prev").addEventListener("click", function () {
    if (i > 0) { i--; show(); }
  });
  document.getElementById("next").addEventListener("click", function () {
    if (i < steps.length - 1) { i++; show(); }
  });
  window.addEventListener("resize", resize);
  show();
})();
</script>
</body>
</html>
"""


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stepper_html(title: str, code: str, trace: list[TraceStep], notes: list[LineNote]) -> str:
    """The stepper document for this code, its recorded trace and the notes."""
    data = {
        "title": title,
        "code": code.rstrip("\n"),
        "trace": [step.model_dump() for step in trace],
        "notes": [note.model_dump() for note in notes],
    }
    # ``</`` and ``<!--`` inside a script element would end it early; ``<`` reads the same.
    encoded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    values = {"TITLE": _html_escape(title), "DATA": encoded}
    # One pass, so a title that happens to contain a placeholder is not filled in turn.
    return re.sub(r"__(TITLE|DATA)__", lambda match: values[match.group(1)], _STEPPER_TEMPLATE)
