"""Type-specific user prompts for textbook-grounded question generation."""

from __future__ import annotations

from app.domain.enums import QuestionType
from app.generation.principles import COMMON_SYSTEM
from app.generation.spec import QuestionSpec

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


def build_prompt(
    spec: QuestionSpec,
    *,
    section_text: str,
    citation: str,
    topic_name: str,
    subtopic_names: list[str],
) -> tuple[str, str]:
    """Build the shared system instruction and one format-specific user prompt."""
    subtopics = ", ".join(subtopic_names)
    user = f"""Create a {spec.difficulty.value} {spec.question_type.value} question.

Topic: {topic_name}
Subtopic(s): {subtopics}
Source citation: {citation}

Type-specific requirements:
{_TYPE_INSTRUCTIONS[spec.question_type]}

Use this section text as the grounding source:
--- section text ---
{section_text}
--- end section text ---"""
    return COMMON_SYSTEM, user
