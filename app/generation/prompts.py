"""Type-specific user prompts for textbook-grounded question generation."""

from __future__ import annotations

from app.domain.enums import QuestionType
from app.generation.principles import COMMON_SYSTEM
from app.generation.spec import MAX_CLAIMED_SUBTOPICS, QuestionSpec
from app.persistence.models import CurriculumVersionRow

_TYPE_INSTRUCTIONS: dict[QuestionType, str] = {
    QuestionType.MULTIPLE_CHOICE: (
        "Write a multiple-choice question with plausible alternatives. "
        "Set correct_option_index to the zero-based index of the one correct option."
    ),
    QuestionType.TRUE_FALSE: (
        "Write one unambiguous true-or-false statement. Set correct_answer to its truth value."
    ),
    QuestionType.OUTPUT_PREDICTION: (
        "Provide a short runnable code snippet and ask for its exact output. "
        "Set expected_output exactly, including line breaks."
    ),
    QuestionType.CODE_COMPLETION: (
        "Provide incomplete code to finish, a complete reference_solution, "
        "and executable test cases."
    ),
    QuestionType.DEBUGGING: (
        "Provide buggy code, ask the learner to diagnose or fix it, and provide a correct "
        "reference_solution plus executable test cases."
    ),
    QuestionType.PARSONS: (
        "Create a Parsons puzzle. Each block must have an id, text, and correct indent level; "
        "correct_order must list the block ids in solution order."
    ),
    QuestionType.CODING: (
        "Ask for a small implementation, then provide a complete reference_solution and "
        "executable test cases."
    ),
}

CLASSIFICATION_INSTRUCTION = f"""Classify your own question.
Choose the one topic it belongs to and set topic_id to that topic's numeric id.
Then set subtopic_ids to the ids of the subtopics your question actually
assesses -- at least one, at most {MAX_CLAIMED_SUBTOPICS}, all of them under the
topic you chose. Use only ids from the taxonomy below.

Write the question the section supports, then classify what you wrote. Do not
bend the question toward a subtopic that reads as a neater fit."""


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
) -> tuple[str, str]:
    """Build the shared system instruction and one format-specific user prompt."""
    user = f"""Create a {spec.difficulty.value} {spec.question_type.value} question.

Source citation: {citation}

Type-specific requirements:
{_TYPE_INSTRUCTIONS[spec.question_type]}

Use this section text as the grounding source:
--- section text ---
{section_text}
--- end section text ---

{CLASSIFICATION_INSTRUCTION}

--- taxonomy ---
{taxonomy}
--- end taxonomy ---"""
    return COMMON_SYSTEM, user
