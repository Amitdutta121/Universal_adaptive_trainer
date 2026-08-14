"""Type-specific user prompts for textbook-grounded question generation."""

from __future__ import annotations

import hashlib

from app.domain.enums import QuestionType
from app.generation.principles import COMMON_SYSTEM
from app.generation.spec import MAX_CLAIMED_SUBTOPICS, QuestionSpec
from app.persistence.models import CurriculumVersionRow

#: How the validator runs the tests a draft declares. Stated for every executable
#: type because the model consistently got it wrong without it: it would write a
#: solution that only *defines* functions, then declare a ``stdout`` expectation
#: as though the function had been called and printed. Four of six hard debugging
#: questions failed that way; spelling out the contract took them to six of six,
#: with declared stdout cases falling from 14 to 1.
_EXECUTABLE_CONTRACT = """
How your tests will be run:
* reference_solution is written to a file and executed as a whole program.
* For each test, its `assert` code is APPENDED to the end of your solution and
  runs after it, in the same scope.
* Its `stdin` is piped to the program as standard input. It is NOT executed as
  Python -- never put code in stdin.
* A test passes if the program exits cleanly and, when `stdout` is set, its
  printed output matches exactly.
So: if your solution only defines functions and prints nothing, leave `stdout`
unset and put every check in `assert`. Only set `stdout` if the program really
prints that text when run. Before answering, run your reference_solution against
every test in your head and confirm it does what you declared."""

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
        "and executable test cases." + _EXECUTABLE_CONTRACT
    ),
    QuestionType.DEBUGGING: (
        "Provide buggy code, ask the learner to diagnose or fix it, and provide a correct "
        "reference_solution plus executable test cases.\n"
        "The code must contain exactly one defect, and one a learner plausibly writes. "
        "reference_solution is the complete corrected program, runnable as-is -- code, never "
        "an explanation of the fix." + _EXECUTABLE_CONTRACT
    ),
    QuestionType.PARSONS: (
        "Create a Parsons puzzle. Each block must have an id, text, and correct indent level; "
        "correct_order must list the block ids in solution order."
    ),
    QuestionType.CODING: (
        "Ask for a small implementation, then provide a complete reference_solution and "
        "executable test cases. Name the function, its parameters and what it returns, so "
        "one correct implementation is obvious in shape." + _EXECUTABLE_CONTRACT
    ),
}

CLASSIFICATION_INSTRUCTION = f"""Classify your own question.
Choose the one topic it belongs to and set topic_id to that topic's numeric id.
Then set subtopic_ids to the ids of the subtopics your question actually
assesses -- at least one, at most {MAX_CLAIMED_SUBTOPICS}, all of them under the
topic you chose. Use only ids from the taxonomy below.

Write the question the section supports, then classify what you wrote. Do not
bend the question toward a subtopic that reads as a neater fit."""


def base_type_instruction(question_type: QuestionType) -> str:
    """The shipped instruction for a type, before anything is learned."""
    return _TYPE_INSTRUCTIONS[question_type]


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
) -> tuple[str, str]:
    """Build the shared system instruction and one format-specific user prompt.

    ``type_instruction`` overrides the shipped entry for this type. That slot is
    where personalization lives (ADR-033): the professor's learned requirements
    replace the one-liner rather than arriving as a block appended after the
    prompt. Absent, the shipped text is used, which is what a type nobody has
    reviewed gets.
    """
    user = f"""Create a {spec.difficulty.value} {spec.question_type.value} question.

Source citation: {citation}

Type-specific requirements:
{type_instruction or _TYPE_INSTRUCTIONS[spec.question_type]}

Use this section text as the grounding source:
--- section text ---
{section_text}
--- end section text ---

{CLASSIFICATION_INSTRUCTION}

--- taxonomy ---
{taxonomy}
--- end taxonomy ---"""
    return COMMON_SYSTEM, user
