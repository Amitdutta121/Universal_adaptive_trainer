"""Type-specific user prompts for textbook-grounded question generation."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.enums import QuestionType
from app.evaluation.prompts import difficulty_bands
from app.generation.principles import common_system
from app.generation.spec import MAX_CLAIMED_SUBTOPICS, QuestionSpec
from app.persistence.models import CurriculumVersionRow, SubtopicRow
from app.styles.schema import QuestionStyle
from app.subjects import PYTHON_PROFILE, SubjectProfile

CLASSIFICATION_INSTRUCTION = f"""Classify your own question.
Choose the one topic it belongs to and set topic_id to that topic's numeric id.
Then set subtopic_ids to the ids of the subtopics your question actually
assesses -- at least one, at most {MAX_CLAIMED_SUBTOPICS}, all of them under the
topic you chose. Use only ids from the taxonomy below.

Write the question the section supports, then classify what you wrote. Do not
bend the question toward a subtopic that reads as a neater fit."""


def base_type_instruction(question_type: QuestionType) -> str:
    """The shipped instruction for a type, before anything is learned (its module's).

    Raises:
        FeatureNotAvailableError: the type is in the enum but its module has not landed.
    """
    from app.errors import FeatureNotAvailableError
    from app.question_types import get_type

    try:
        return get_type(question_type).instruction
    except KeyError as error:
        raise FeatureNotAvailableError(
            f"The {question_type.value} question type is not built yet.",
            detail=str(error),
        ) from error


#: Hex characters of the digest that names one instruction. Short enough to read
#: in a table, wide enough that two instructions will not collide in one bank.
_FINGERPRINT_CHARS = 8


def instruction_fingerprint(instruction: str) -> str:
    """Name the exact instruction text a question was generated from (ADR-040).

    The generator's equivalent of the judges' ``rubric_version`` (ADR-038), and a
    fingerprint for the same reason: the identity has to be the *content*. A
    counter cannot tell two instructions apart when both have been relearned the
    same number of times, and ``updated_at`` says when the text changed without
    saying what it changed to.

    Without this, every question in the bank is stamped ``base@1`` and nothing
    records which instruction produced it -- so "are questions written after that
    refresh approved more often?" has no data behind it.
    """
    return hashlib.sha256(instruction.encode("utf-8")).hexdigest()[:_FINGERPRINT_CHARS]


def render_taxonomy(version: CurriculumVersionRow) -> str:
    """Render the whole approved taxonomy as the id list the model chooses from.

    The entire tree goes into the prompt, not a pre-selected branch: the point of
    letting the generator classify is that nothing upstream has decided where the
    section belongs.
    """
    lines: list[str] = []
    for topic in version.topics:
        lines.append(f"[topic {topic.id}] {topic.name}")
        for subtopic in topic.subtopics:
            description = f" -- {subtopic.description}" if subtopic.description else ""
            lines.append(f"  [subtopic {subtopic.id}] {subtopic.name}{description}")
    return "\n".join(lines)


#: Characters of one accepted example question shown to the generator. Enough to show the
#: level and shape the professor accepted, not so much that it is copied.
EXAMPLE_PROMPT_CHARS = 600


#: Characters of the professor's comment shown with an example or a rejected question.
COMMENT_CHARS = 300


@dataclass(frozen=True)
class ShownExample:
    """An example question with the professor's comment on it, if they left one."""

    text: str
    comment: str | None = None


@dataclass(frozen=True)
class RejectedExample:
    """A similar question the professor rejected, and why (reasons, then comment)."""

    text: str
    because: str


@dataclass(frozen=True)
class RoundExamples:
    """What a round target is shown from memory and the bank (ADR-063 point 3), as prompt text.

    ``accepted``: approved questions of the same type, subtopic and difficulty -- match their
    level. ``style_only``: approved questions of the same type from elsewhere -- match their
    form, not their content or level. Either may carry the professor's comment. ``in_bank``:
    the nearest existing questions of the cell, which the new question must not repeat.
    ``rejected``: at most one similar question the professor rejected, with why. ``avoid``:
    what failed attempts of approved questions of this type and subtopic got wrong.
    """

    accepted: Sequence[str | ShownExample] = ()
    style_only: Sequence[str | ShownExample] = ()
    in_bank: Sequence[str] = ()
    rejected: RejectedExample | None = None
    avoid: Sequence[str] = ()


def _shown(texts: Sequence[str]) -> list[str]:
    return [text.strip()[:EXAMPLE_PROMPT_CHARS] for text in texts if text and text.strip()]


def _shown_examples(items: Sequence[str | ShownExample]) -> list[tuple[str, str | None]]:
    """``(text, comment)`` per non-empty example, both trimmed to their limits."""
    shown = []
    for item in items:
        example = item if isinstance(item, ShownExample) else ShownExample(item)
        for text in _shown([example.text]):
            comment = (example.comment or "").strip()[:COMMENT_CHARS] or None
            shown.append((text, comment))
    return shown


def _with_comment(line: str, comment: str | None) -> list[str]:
    return [line] + ([f"  Professor's comment: {comment}"] if comment else [])


def render_round_target(
    *,
    subtopic: SubtopicRow,
    topic_name: str,
    style: QuestionStyle | None,
    examples: RoundExamples | None = None,
) -> str:
    """The block a round spec adds: the subtopic, the style, examples, what not to repeat.

    A round is aimed (docs/QUESTION_SETUP_PLAN.md): unlike section-only generation, the
    subtopic is part of the request, and the topic judge then checks the question really
    assesses it. The model still classifies its own question; it is told the target id must
    be among the ones it names.
    """
    description = f" -- {subtopic.description}" if subtopic.description else ""
    lines = [
        "--- target ---",
        f"The question must assess this subtopic: [subtopic {subtopic.id}] {subtopic.name}"
        f"{description} (topic: {topic_name}).",
        f"Set topic_id to its topic and include {subtopic.id} in subtopic_ids.",
    ]
    if style is not None:
        lines += [
            "",
            f"Write it in this question style: {style.name}.",
            f"What the student does: {style.summary}",
            f"How the answer is checked: {style.checked_by}",
        ]
    examples = examples or RoundExamples()
    number = 0
    accepted = _shown_examples(examples.accepted)
    if accepted:
        lines += [
            "",
            "The professor accepted these questions for the same subtopic and difficulty. "
            "Match their level and quality; do not copy or paraphrase them.",
        ]
        for number, (text, comment) in enumerate(accepted, start=1):
            lines += _with_comment(f"Example {number}: {text}", comment)
    style_only = _shown_examples(examples.style_only)
    if style_only:
        lines += [
            "",
            "Style only: the professor accepted these questions of the same type for other "
            "subtopics or difficulties. Match their form only, not their content or level.",
        ]
        for offset, (text, comment) in enumerate(style_only, start=1):
            lines += _with_comment(f"Example {number + offset} (style only): {text}", comment)
    rejected = examples.rejected
    rejected_text = _shown([rejected.text]) if rejected else []
    because = rejected.because.strip()[:COMMENT_CHARS] if rejected else ""
    if rejected_text and because:
        lines += [
            "",
            f"The professor rejected a similar question because: {because}",
            "Do not repeat that mistake.",
            f"Rejected: {rejected_text[0]}",
        ]
    avoid = _shown(examples.avoid)
    if avoid:
        lines += [
            "",
            "Earlier drafts for this subtopic failed these checks before a fixed version was "
            "approved. Avoid the same mistakes:",
        ]
        for index, text in enumerate(avoid, start=1):
            lines.append(f"Avoid {index}: {text}")
    in_bank = _shown(examples.in_bank)
    if in_bank:
        lines += [
            "",
            "Already in the bank for this subtopic and difficulty -- assess something "
            "different from each of these:",
        ]
        for index, text in enumerate(in_bank, start=1):
            lines.append(f"Existing {index}: {text}")
    lines.append("--- end target ---")
    return "\n".join(lines)


def build_prompt(
    spec: QuestionSpec,
    *,
    section_text: str,
    citation: str,
    taxonomy: str,
    type_instruction: str | None = None,
    instructor_feedback: str | None = None,
    profile: SubjectProfile = PYTHON_PROFILE,
    target_block: str | None = None,
    follow_up: str | None = None,
) -> tuple[str, str]:
    """Build the shared system instruction and one format-specific user prompt.

    ``type_instruction`` overrides the shipped entry for this type. That slot is
    where personalization lives (ADR-033): the professor's learned requirements
    replace the one-liner rather than arriving as a block appended after the
    prompt. Absent, the shipped text is used, which is what a type nobody has
    reviewed gets.

    ``instructor_feedback`` is present only when an instructor asked for a new
    version of an existing question. It is spliced in after the source text as a
    binding requirement for the rewrite. It is deliberately kept in the immutable
    prompt rather than seeded into the retry loop's ``--- correction ---`` block
    (:mod:`app.generation.attempts`), which is framed as "your previous answer
    was rejected" and is the wrong lifecycle for instructor intent.

    ``target_block`` (:func:`render_round_target`) is set only for a round spec and goes
    after the source text, before classification. Absent, the prompt is byte-for-byte the
    section-only prompt.

    ``follow_up`` is the hard-cell second step: a question that already passed the answer
    check, with the instruction to make it harder. Absent, the prompt is unchanged.
    """
    feedback_block = ""
    if instructor_feedback and instructor_feedback.strip():
        feedback_block = f"""

--- instructor feedback ---
An earlier version of this question was generated and an instructor asked for a
new one, with this feedback. Treat it as a binding requirement, not a
suggestion. Write a NEW question that resolves it while still satisfying every
rule above. Do not reproduce the earlier question.

{instructor_feedback.strip()}
--- end instructor feedback ---"""

    target_text = f"\n\n{target_block}" if target_block else ""
    follow_up_block = ""
    if follow_up and follow_up.strip():
        follow_up_block = f"""

--- make it harder ---
{follow_up.strip()}
--- end make it harder ---"""
    user = f"""Create a {spec.difficulty.value} {spec.question_type.value} question.

Difficulty, for a student who has just studied the section below and nothing beyond it:
{difficulty_bands(profile)}

Source citation: {citation}

Type-specific requirements:
{type_instruction or base_type_instruction(spec.question_type)}

Use this section text as the grounding source:
--- section text ---
{section_text}
--- end section text ---{feedback_block}{target_text}{follow_up_block}

{CLASSIFICATION_INSTRUCTION}

--- taxonomy ---
{taxonomy}
--- end taxonomy ---"""
    return common_system(profile), user
