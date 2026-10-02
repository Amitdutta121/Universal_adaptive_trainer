"""Type-specific user prompts for textbook-grounded question generation."""

from __future__ import annotations

import hashlib

from app.domain.enums import QuestionType
from app.generation.principles import common_system
from app.generation.spec import MAX_CLAIMED_SUBTOPICS, QuestionSpec
from app.persistence.models import CurriculumVersionRow
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


def build_prompt(
    spec: QuestionSpec,
    *,
    section_text: str,
    citation: str,
    taxonomy: str,
    type_instruction: str | None = None,
    instructor_feedback: str | None = None,
    profile: SubjectProfile = PYTHON_PROFILE,
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

    user = f"""Create a {spec.difficulty.value} {spec.question_type.value} question.

Source citation: {citation}

Type-specific requirements:
{type_instruction or base_type_instruction(spec.question_type)}

Use this section text as the grounding source:
--- section text ---
{section_text}
--- end section text ---{feedback_block}

{CLASSIFICATION_INSTRUCTION}

--- taxonomy ---
{taxonomy}
--- end taxonomy ---"""
    return common_system(profile), user
