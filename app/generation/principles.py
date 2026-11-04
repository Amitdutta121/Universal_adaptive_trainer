"""Shared grounding rules for structured base-question generation."""

from __future__ import annotations

from app.subjects import PYTHON_PROFILE, SubjectProfile

#: Question types whose answers are numbers or formulas; their courses write math in LaTeX.
MATH_TYPES = frozenset({"numeric_response", "equation_response"})


def common_system(profile: SubjectProfile) -> str:
    """The generator's system prompt for one subject.

    Code-only wording (variable names, language features, tests) appears only when
    a chosen question type runs code. The Python profile gives the shipped text.
    """
    if profile.has_code_types:
        grounding = f"""You create one accurate {profile.phrase} assessment question.
Ground the assessed skill in the supplied textbook section. You may use fresh
variable names, literals, and examples, but do not assess an untaught {profile.code_language}
feature or claim the section says something it does not. Keep the requested
difficulty within the taught skill. The question must contain everything a student
needs to answer it. Any code you show -- in the prompt, an option, or a snippet --
must behave exactly as the question and its answer claim: code meant to run must
run, and code meant to fail must fail in the way the answer says. If code reads
input, state the exact text the user types; do not replace the input call with a
fixed value.
Return only the requested structured fields; ensure the reference answer,
explanation, and any tests agree with the question."""
    else:
        grounding = f"""You create one accurate {profile.phrase} assessment question.
Ground the assessed skill in the supplied textbook section. You may use fresh
names, values, and examples, but do not assess an untaught idea or claim the
section says something it does not. Keep the requested difficulty within the
taught skill. The question must contain everything a student needs to answer it.
Return only the requested structured fields; ensure the reference answer and
explanation agree with the question."""
    return f"{grounding}\n\n{prompt_style(profile)}"


def prompt_style(profile: SubjectProfile) -> str:
    """How to write the student-facing ``prompt`` field, which is rendered as Markdown.

    The general rules hold for any course; backtick and LaTeX rules are added only for
    courses whose question types need them, so a history course is never told about either.
    """
    rules = [
        "State the task in one short sentence and ask one thing.",
        "If the question needs a scenario, data, or a passage, give it in its own paragraph "
        "before the task: data as a Markdown table, a quoted source as a > blockquote.",
        "If the task has several requirements, list them as - bullets after the task; "
        "otherwise do not use bullets.",
        "Do not restate what the answer options or answer area already show.",
        "Do not use headings, bold, or HTML. Write a dollar amount as \\$5.",
    ]
    if profile.has_code_types:
        rules.append(
            "Put identifiers, literal values, and expressions in `backticks`. When the "
            "structured fields have a separate code field, put the snippet only there; "
            "otherwise put a multi-line snippet in a fenced ```python block."
        )
    if MATH_TYPES & set(profile.question_types):
        rules.append(
            "Write formulas, variables, and units in LaTeX: $...$ inline, $$...$$ for a "
            "formula on its own line."
        )
    bullets = "\n".join(f"- {rule}" for rule in rules)
    return f"Write the prompt field in light Markdown; it is rendered for the student.\n{bullets}"


COMMON_SYSTEM = common_system(PYTHON_PROFILE)
