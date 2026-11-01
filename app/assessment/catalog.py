"""What the product can assess: capabilities, question types and subject presets (ADR-054).

Three layers, as designed:

- A **capability** is a checking ability, implemented by a grader. Defined once, for every subject.
- A **question type** fixes what the student answers with. It is gradable by any one of its
  ``graded_by`` capabilities and always needs every capability in ``also_needs`` (the code types
  need Run Python to prove their answer when a question is created). Also defined once.
- A **subject preset** is the only per-subject data: which types are ticked by default, which
  groups are shown first, and an example question per type in that subject's language.

A professor creating a course picks a subject, then question types; the capabilities are worked
out from the types (:func:`capabilities_for`), never chosen. A type is offerable only when it is
actually built end to end -- generated, validated and scored by this application. Today that is the
seven Python types; the rest are listed so a professor can see what is coming, and cannot be
picked.

This module is metadata only. Whether a capability is built is read from the isolated graders
package (``graders.available_capabilities``, ADR-055); a type is offerable only when its graders
exist *and* the app can generate, validate and score it (``implemented``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import QuestionType
from graders import available_capabilities


@dataclass(frozen=True)
class Capability:
    id: str
    label: str
    #: What it can check, in the words a professor (and later the AI) is given.
    description: str
    #: False for AI grading: its scores never count toward mastery.
    deterministic: bool

    @property
    def built(self) -> bool:
        """Whether a grader for it exists -- asked of the graders registry, never hand-set."""
        return self.id in available_capabilities()


@dataclass(frozen=True)
class QuestionTypeSpec:
    id: str
    label: str
    #: What the student answers with.
    widget: str
    group: str
    graded_by: tuple[str, ...]
    also_needs: tuple[str, ...] = ()

    @property
    def implemented(self) -> bool:
        """Generated, validated and scored end to end: its ``app/question_types`` module exists."""
        from app.question_types import implemented_types

        return self.id in {question_type.value for question_type in implemented_types()}


@dataclass(frozen=True)
class SubjectPreset:
    id: str
    label: str
    description: str
    #: Ticked when a course is created from this subject (only offerable ones are applied).
    default_types: tuple[str, ...]
    #: Group ids shown open first; the rest go under "More question types".
    primary_groups: tuple[str, ...]
    #: An example question per type, in this subject's terms.
    examples: dict[str, str] = field(default_factory=dict)


GROUPS: dict[str, tuple[str, str]] = {
    "quick": ("Quick checks", "Fast to answer, marked instantly."),
    "code": ("Code", "Marked by running the code."),
    "maths": ("Numbers and maths", "Marked by checking the value or the formula."),
    "written": ("Written answers", "Marked by AI against a rubric."),
}

CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "structured.choice",
        "Choice",
        "Checks which option was picked.",
        deterministic=True,
    ),
    Capability(
        "structured.ordering",
        "Ordering",
        "Checks the order of given pieces, with their indentation.",
        deterministic=True,
    ),
    Capability(
        "text.normalized_match",
        "Exact text",
        "Checks text against the expected answer after normalising line endings.",
        deterministic=True,
    ),
    Capability(
        "code.python.execute",
        "Run Python",
        "Runs Python to prove an answer when a question is created.",
        deterministic=True,
    ),
    Capability(
        "code.python.tests",
        "Python tests",
        "Runs a student's Python against hidden tests, with partial credit.",
        deterministic=True,
    ),
    Capability(
        "quantity.units",
        "Numeric with units",
        "Checks a number within a tolerance, converting units.",
        deterministic=True,
    ),
    Capability(
        "symbolic.expression_equivalence",
        "Equation / expression",
        "Checks that a formula is mathematically equivalent to the expected one.",
        deterministic=True,
    ),
    Capability(
        "semantic.source_grounded",
        "Rubric-graded explanation",
        "An AI grades a short written answer against a rubric and the course's reading.",
        deterministic=False,
    ),
)

_PY = "code.python.execute"

QUESTION_TYPES: tuple[QuestionTypeSpec, ...] = (
    QuestionTypeSpec(
        QuestionType.MULTIPLE_CHOICE.value,
        "Multiple choice",
        "choice buttons",
        "quick",
        ("structured.choice",),
    ),
    QuestionTypeSpec(
        QuestionType.TRUE_FALSE.value,
        "True / false",
        "two buttons",
        "quick",
        ("structured.choice",),
    ),
    QuestionTypeSpec(
        "short_answer", "Short answer", "a text box", "quick", ("text.normalized_match",)
    ),
    QuestionTypeSpec(
        QuestionType.PARSONS.value,
        "Parsons (order the code)",
        "drag to order",
        "code",
        ("structured.ordering",),
        (_PY,),
    ),
    QuestionTypeSpec(
        QuestionType.OUTPUT_PREDICTION.value,
        "Output prediction",
        "a text box",
        "code",
        ("text.normalized_match",),
        (_PY,),
    ),
    QuestionTypeSpec(
        QuestionType.CODE_COMPLETION.value,
        "Code completion",
        "a code editor",
        "code",
        ("code.python.tests",),
        (_PY,),
    ),
    QuestionTypeSpec(
        QuestionType.DEBUGGING.value,
        "Debugging",
        "a code editor",
        "code",
        ("code.python.tests",),
        (_PY,),
    ),
    QuestionTypeSpec(
        QuestionType.CODING.value,
        "Coding",
        "a code editor",
        "code",
        ("code.python.tests",),
        (_PY,),
    ),
    QuestionTypeSpec(
        QuestionType.NUMERIC_RESPONSE.value,
        "Numeric response",
        "a number and unit",
        "maths",
        ("quantity.units",),
    ),
    QuestionTypeSpec(
        QuestionType.EQUATION_RESPONSE.value,
        "Equation response",
        "a maths input",
        "maths",
        ("symbolic.expression_equivalence",),
    ),
    QuestionTypeSpec(
        "short_explanation",
        "Short explanation",
        "a paragraph box",
        "written",
        ("semantic.source_grounded",),
    ),
)

#: Used when a subject has no example of its own for a type.
NEUTRAL_EXAMPLES: dict[str, str] = {
    "multiple_choice": "Pick the one correct option out of four.",
    "true_false": "Decide whether a statement is true or false.",
    "short_answer": "Type a single word or short phrase.",
    "numeric_response": "Give a number, with its unit.",
    "equation_response": "Write an expression or formula.",
    "short_explanation": "Explain an idea in two or three sentences.",
}

SUBJECTS: tuple[SubjectPreset, ...] = (
    SubjectPreset(
        "intro_python",
        "Intro programming (Python)",
        "Choice, Parsons, output prediction and code questions, marked by running Python.",
        default_types=(
            "multiple_choice",
            "true_false",
            "parsons",
            "output_prediction",
            "code_completion",
            "debugging",
            "coding",
        ),
        primary_groups=("quick", "code"),
        examples={
            "multiple_choice": "Which of these is a mutable type? (a) tuple (b) list (c) str",
            "true_false": "True or false: a list can hold values of different types.",
            "short_answer": "What does len('abc') return?",
            "parsons": "Put these lines in order so the loop prints 1 to 5.",
            "output_prediction": "What does this code print?",
            "code_completion": "Fill in the missing line so the function returns the maximum.",
            "debugging": "This loop never stops. Fix it.",
            "coding": "Write factorial(n). Hidden tests give partial credit.",
            "short_explanation": "In two sentences, explain why the loop never ends.",
        },
    ),
    SubjectPreset(
        "physics",
        "Physics",
        "Conceptual choice, numbers with units and equations, each marked automatically.",
        default_types=(
            "multiple_choice",
            "true_false",
            "numeric_response",
            "equation_response",
        ),
        primary_groups=("quick", "maths"),
        examples={
            "multiple_choice": "Which quantity is conserved in an elastic collision?",
            "true_false": "True or false: in free fall, a heavier object accelerates faster.",
            "short_answer": "What is the SI unit of force?",
            "numeric_response": "A ball falls from rest. Its speed after 2 s, in m/s?",
            "equation_response": "Write the kinetic energy of a mass m moving at speed v.",
            "short_explanation": "Explain why a satellite in orbit is in free fall.",
        },
    ),
    SubjectPreset(
        "ml_llms",
        "Machine learning & LLMs",
        "Concepts, worked numbers and formulas; add code questions to run models in Python.",
        default_types=(
            "multiple_choice",
            "true_false",
            "numeric_response",
            "equation_response",
        ),
        primary_groups=("quick", "maths", "code"),
        examples={
            "multiple_choice": "Which transformer layer lets every token attend to every other?",
            "true_false": "True or false: a lower validation loss always means less overfitting.",
            "short_answer": "What does the 'T' in GPT stand for?",
            "numeric_response": "A 7B-parameter model in 16-bit weights needs how many GB?",
            "equation_response": "Write the softmax of z_i over n logits.",
            "output_prediction": "What does this tokenizer call print?",
            "coding": "Write cosine_similarity(a, b) for two lists of floats.",
            "short_explanation": "Explain why temperature 0 makes sampling deterministic.",
        },
    ),
    SubjectPreset(
        "biology",
        "Biology",
        "Conceptual choice and short answers.",
        default_types=("multiple_choice", "true_false", "short_answer"),
        primary_groups=("quick", "written"),
        examples={
            "multiple_choice": "Which organelle produces most of a cell's ATP?",
            "true_false": "True or false: meiosis produces genetically identical cells.",
            "short_answer": "What is the complementary DNA strand of ATGC?",
            "numeric_response": "A 3:1 cross gives 300 offspring. How many are recessive?",
            "short_explanation": "Explain how natural selection changes a population over time.",
        },
    ),
    SubjectPreset(
        "custom",
        "Something else",
        "Start from choice questions and add what your course needs.",
        default_types=("multiple_choice", "true_false"),
        primary_groups=("quick",),
    ),
)

CAPABILITIES_BY_ID: dict[str, Capability] = {item.id: item for item in CAPABILITIES}
TYPES_BY_ID: dict[str, QuestionTypeSpec] = {item.id: item for item in QUESTION_TYPES}
SUBJECTS_BY_ID: dict[str, SubjectPreset] = {item.id: item for item in SUBJECTS}

#: What an existing course is assumed to be: the product was Intro Python before courses existed.
LEGACY_SUBJECT = "intro_python"


def is_offerable(type_id: str) -> bool:
    """Whether a professor may pick this type: built end to end, and its graders exist."""
    spec = TYPES_BY_ID.get(type_id)
    if spec is None or not spec.implemented:
        return False
    built = {cap.id for cap in CAPABILITIES if cap.built}
    return any(cap in built for cap in spec.graded_by) and all(
        cap in built for cap in spec.also_needs
    )


def default_types_for(subject_id: str) -> list[str]:
    """The offerable types a subject ticks by default, in catalogue order."""
    preset = SUBJECTS_BY_ID.get(subject_id)
    if preset is None:
        return []
    wanted = set(preset.default_types)
    return [spec.id for spec in QUESTION_TYPES if spec.id in wanted and is_offerable(spec.id)]


def capabilities_for(type_ids: list[str]) -> list[str]:
    """The capabilities a set of question types needs: one built grader each, plus what it needs.

    The professor never picks these; they follow from the types (ADR-054).
    """
    built = {cap.id for cap in CAPABILITIES if cap.built}
    needed: set[str] = set()
    for type_id in type_ids:
        spec = TYPES_BY_ID.get(type_id)
        if spec is None:
            continue
        grader = next((cap for cap in spec.graded_by if cap in built), None)
        if grader is not None:
            needed.add(grader)
        needed.update(spec.also_needs)
    return [cap.id for cap in CAPABILITIES if cap.id in needed]


def course_question_types(subject: str | None, question_types: list[str] | None) -> list[str]:
    """The question types a course may generate.

    A course saved before it recorded any (created by name only, or by an older client) keeps
    its subject's defaults -- for the legacy subject, all seven Python types -- so nothing it
    could do before is taken away.
    """
    if question_types:
        return [type_id for type_id in question_types if type_id in TYPES_BY_ID]
    return default_types_for(subject or LEGACY_SUBJECT)


def example_for(subject_id: str | None, type_id: str) -> str:
    preset = SUBJECTS_BY_ID.get(subject_id or "")
    if preset is not None and type_id in preset.examples:
        return preset.examples[type_id]
    return NEUTRAL_EXAMPLES.get(type_id, "")
