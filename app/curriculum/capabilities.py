"""The boundary of what the app can teach and check, for any course (ADR-077).

The curriculum drafter and the course agent are both given :func:`capabilities_text`. It says
that new tutorial recipes and question styles can be drafted for any course at any time, and
names the fixed parts every recipe and style is built from -- which is the boundary nothing
drafted can cross. A subtopic belongs in a curriculum when some recipe could teach it and some
style could check it, whether or not that recipe and style exist yet; a course's parts outside
the boundary are listed as out of scope instead.

Every list is read from the live catalogue (tutorial renderers and tools, question types built
end to end), so the boundary moves when a new type or renderer ships. Nothing here names a
subject.
"""

from __future__ import annotations

from app.assessment import catalog
from app.domain.enums import TutorialRenderer

#: How each tutorial renderer teaches. A renderer added to the enum without a line here is
#: described by its name, so the boundary never silently leaves it out.
_RENDERER_TEXT: dict[str, str] = {
    "markdown": "a written explanation or worked example (text, formulas, code)",
    "mermaid": "a diagram (flowchart, state machine, tree, sequence, timeline)",
    "chartjs": "a chart of numbers (bar, line, pie, scatter)",
    "html": (
        "a small self-contained interactive page (sliders, step-through animations, "
        "clickable models); it runs with no network and no outside software"
    ),
    "video_clip": "a clip of the course's own lecture video",
}

#: Parts a recipe can add to a block (``app.tutorials.schema.RecipeTool``).
_TOOL_TEXT = ("a step-by-step trace of a real Python run",)

#: Capabilities that mark answers to written prose; while none is offerable, prose is outside.
_PROSE_GRADING = {"text.normalized_match", "semantic.source_grounded"}
_PROSE_TYPES = {"short_answer", "short_explanation"}


def _offerable() -> list[catalog.QuestionTypeSpec]:
    return [spec for spec in catalog.QUESTION_TYPES if catalog.is_offerable(spec.id)]


def question_type_lines() -> list[str]:
    """``label (how the student answers)`` for each question type the app can mark today."""
    lines = []
    for spec in _offerable():
        python = (
            " -- Python code, run to mark it" if "code.python.execute" in spec.also_needs else ""
        )
        lines.append(f"{spec.label} (the student answers with {spec.widget}{python})")
    return lines


def outside_lines() -> list[str]:
    """What no recipe or style can do, given the question types offerable now."""
    lines = [
        "work done in outside software: installing or configuring tools, using an application, "
        "editor, lab instrument or engine, version control, building or deploying a project",
        "physical or practical skills, live performances, demos, projects, presentations and "
        "anything else a person has to watch or mark",
    ]
    offered = {spec.id for spec in _offerable()}
    if not offered & _PROSE_TYPES:
        lines.append("written answers in the student's own words: essays, explanations, proofs")
    lines.append("running code in any language other than Python")
    return lines


def figure_lines() -> list[str]:
    """``Label: what it can show`` for each figure kind a style may ask for today."""
    return [f"{kind.label}: {kind.description}" for kind in catalog.built_figure_kinds()]


def figures_text() -> str:
    """That a question can carry a figure, and the kinds, as one paragraph of a prompt."""
    bullets = "\n".join(f"- {line}" for line in figure_lines())
    return (
        "A style may also give each of its questions a figure the student reads to answer, "
        "when the subtopic's material is something to look at rather than only words: a "
        "structure, a process, a cycle, a dataset, a grid. It is one of:\n"
        f"{bullets}"
    )


def capabilities_text(*, figures: bool = False) -> str:
    """The boundary, as one block of a prompt.

    ``figures`` adds the figure kinds a style can give its questions (ADR-080). The course
    designer and the agent ask for them; the curriculum drafter does not yet, so its prompt
    stays as it was (``tests/golden/python_prompts.json``).
    """
    teaches = [
        _RENDERER_TEXT.get(renderer.value, renderer.value.replace("_", " "))
        for renderer in TutorialRenderer
    ] + list(_TOOL_TEXT)
    bullets = lambda lines: "\n".join(f"- {line}" for line in lines)  # noqa: E731
    return (
        "## What can be made for a course\n"
        "New tutorial recipes (ways of teaching a subtopic) and question styles (ways of asking "
        "about it) can be drafted at any time, in the course's own subject and words, so a "
        "subtopic does not need an existing recipe or style to belong in the curriculum. Every "
        "recipe and style is built from fixed parts, and nothing drafted can go beyond them.\n\n"
        "A recipe teaches with tutorial blocks written from the course's material, each one of:\n"
        f"{bullets(teaches)}\n\n"
        "A style checks with one of these question types:\n"
        f"{bullets(question_type_lines())}\n\n"
        f"{figures_text() + chr(10) * 2 if figures else ''}"
        "Outside the boundary, whatever is drafted:\n"
        f"{bullets(outside_lines())}\n\n"
        "So a subtopic belongs in the curriculum when some recipe could teach it and some style "
        "could check it, whether or not they exist yet: a concept, a fact, a reasoning step, a "
        "calculation, reading or tracing an example, or Python code. The understanding behind a "
        "hands-on activity can be a subtopic; doing the activity cannot. Parts of a course "
        "outside the boundary are listed as out of scope, not made into subtopics."
    )
