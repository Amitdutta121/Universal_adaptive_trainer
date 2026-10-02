"""The four judge prompts, and the payload each judge is allowed to see.

One judge per metric. Each gets its own system prompt and its own payload, and
the payloads deliberately differ: the generatability judge is never shown the
question, because its subject is the source material and knowing that a question
already exists is exactly the bias that would stop it saying "this chunk could
not support one".

The system prompts are functions of the course's :class:`SubjectProfile`
(phase 2, decision 4). Wording about code, tests and execution, and the test
issue codes, appear only when a chosen question type runs code. The module-level
constants are the Python profile's output -- byte-identical to the shipped text.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.domain.enums import JudgeMetricId, RejectionReason
from app.subjects import PYTHON_PROFILE, SubjectProfile

RUBRIC_VERSION = "question-metrics@1"


@dataclass(frozen=True)
class JudgeContext:
    """Everything the four judges draw on, gathered once per question.

    Held as one object because the judges disagree about what they may see, and
    a single place listing all of it is what makes those differences reviewable
    in :func:`build_user_prompt` instead of scattered across four call sites.
    """

    question_artifact: dict[str, object]
    source_sections: list[dict[str, object]]
    taxonomy: list[dict[str, object]]
    claimed_taxonomy: dict[str, object]
    requested_difficulty: str
    requested_question_type: str | None


#: Issue codes about tests: they exist only for question types that run code.
TEST_ISSUE_CODES: frozenset[RejectionReason] = frozenset(
    {RejectionReason.INCORRECT_TESTS, RejectionReason.POOR_TESTS}
)

#: Issue codes the issues judge may return. The professor's full vocabulary
#: minus what the other three judges own (topic/subtopic, difficulty) and minus
#: ``TOO_SIMILAR_REPETITIVE``, which is a statement about the rest of the bank
#: that a judge looking at one question cannot make. ``OTHER`` is absent because
#: an unnamed problem goes in ``custom_issue`` as prose, where it is readable.
_ALL_ISSUE_CODES: tuple[RejectionReason, ...] = (
    RejectionReason.TECHNICALLY_INCORRECT,
    RejectionReason.INCORRECT_ANSWER,
    RejectionReason.INCORRECT_TESTS,
    RejectionReason.NOT_GROUNDED_IN_SOURCE,
    RejectionReason.POOR_DISTRACTORS,
    RejectionReason.POOR_TESTS,
    RejectionReason.AMBIGUOUS,
    RejectionReason.POOR_WORDING,
    RejectionReason.NOT_PEDAGOGICALLY_USEFUL,
)


def issue_codes_for(profile: SubjectProfile) -> tuple[RejectionReason, ...]:
    """The issue codes the issues judge may return for one subject.

    The test codes are dropped when no chosen type runs code: there are no tests
    to be wrong about.
    """
    if profile.has_code_types:
        return _ALL_ISSUE_CODES
    return tuple(code for code in _ALL_ISSUE_CODES if code not in TEST_ISSUE_CODES)


def _issue_code_guide(profile: SubjectProfile) -> str:
    recall = "tests" if profile.has_code_types else "checks"
    lines: dict[RejectionReason, tuple[str, ...]] = {
        RejectionReason.TECHNICALLY_INCORRECT: (
            f"The question states something false about {profile.name}.",
        ),
        RejectionReason.INCORRECT_ANSWER: (
            "The reference answer is wrong for the question asked.",
        ),
        RejectionReason.INCORRECT_TESTS: ("The tests do not test what the question asks for.",),
        RejectionReason.NOT_GROUNDED_IN_SOURCE: (
            "It assesses material the supplied section does not teach.",
        ),
        RejectionReason.POOR_DISTRACTORS: (
            "Distractors are implausible, trivially eliminable, or",
            "more than one is defensible as correct.",
        ),
        RejectionReason.POOR_TESTS: (
            "Tests run but are weak: they miss the core case or",
            "pass for the wrong reason.",
        ),
        RejectionReason.AMBIGUOUS: ("More than one answer is defensible as written.",),
        RejectionReason.POOR_WORDING: ("Confusing, grammatically broken, or unclear phrasing.",),
        RejectionReason.NOT_PEDAGOGICALLY_USEFUL: (
            "Answerable without exercising the intended skill, or",
            f"{recall} recall of trivia rather than understanding.",
        ),
    }
    rendered: list[str] = []
    for code in issue_codes_for(profile):
        first, *rest = lines[code]
        rendered.append(f"  {code.value:<27}{first}")
        rendered.extend(f"{'':29}{line}" for line in rest)
    return "\n".join(rendered)


def _issues_system(profile: SubjectProfile) -> str:
    if profile.has_code_types:
        checks = (
            "The question has already passed deterministic checks: its code runs and its tests\n"
            "execute. Do not re-check execution, syntax, or whether tests pass."
        )
        item, items, entry, each = "issue code", "codes", "code", "code"
    else:
        checks = """The question has already passed deterministic checks: its answer key is
well-formed. Do not re-check its format or whether an answer is present."""
        item, items, entry, each = "issue", "issues", "entry", "issue"
    return f"""You review one {profile.phrase} assessment question and report which known
problems it has. You do not decide whether to accept it.

{checks}

Select every {item} that genuinely applies, and only from this list:
{_issue_code_guide(profile)}

Report only problems a professor would act on. An imperfect but usable question
has no issues. Do not report an issue you cannot point to in the question text.
Do not judge topic, subtopic, or difficulty -- other reviewers cover those.

If you find a real, actionable problem that no {entry} above describes, leave
issue_codes for what does apply and put that problem in custom_issue as one
sentence. Otherwise leave custom_issue null.

Return the selected {items}, custom_issue, and one rationale of at most two
sentences naming the specific text that triggered each {each}. If nothing is
wrong, return an empty list and say why the question is sound."""


def _subtopic_system(profile: SubjectProfile) -> str:
    if profile.has_code_types:
        example = """questions combine skills; incidental use of a loop in a question about string
methods is normal."""
    else:
        example = (
            "questions combine skills; incidental use of one idea in a question about another\n"
            "is normal."
        )
    return f"""You check one {profile.phrase} assessment question against the topic and
subtopics it was tagged with. The tags were chosen by the generator that wrote
the question, not by a human, so treat them as a claim to be checked.

You are given the question, the tags it claims, the full approved taxonomy, and
the textbook section it was generated from.

Ask one question: to answer this correctly, must a student exercise the skills
named by the claimed subtopics?

Return the topic id and subtopic ids you would assign. If the claim is right,
return exactly what was claimed. If it is wrong, return the correct ids from the
taxonomy: one topic, and every subtopic under that topic the question actually
assesses.

Do not re-tag a question merely because it also touches other subtopics. Real
{example} A claim is right when the claimed subtopics are the skills
being assessed, even if they are not the only skills present.

Also return one rationale of at most two sentences. If you changed the tags, say
what the question actually assesses."""


def _difficulty_system(profile: SubjectProfile) -> str:
    if profile.has_code_types:
        expert = "a professional programmer"
        hard = """  hard    Several taught ideas composed, or careful reasoning about an edge case,
          execution order, or a subtle behaviour -- while still using only what
          the section teaches."""
        surface = "the amount of code shown, or unfamiliar variable names."
    else:
        expert = "an expert in the field"
        hard = """  hard    Several taught ideas composed, or careful reasoning about an edge case
          or a subtle effect -- while still using only what the section
          teaches."""
        surface = "the amount of detail shown, or unfamiliar names."
    return f"""You check whether one {profile.phrase} assessment question matches its
requested difficulty: easy, medium, or hard.

Judge relative to a student who has just studied the supplied textbook section
and nothing beyond it -- not relative to {expert}.

  easy    One taught step, applied directly. The student recalls or applies a
          single idea from the section with no composition.
  medium  Two or three taught ideas combined, or one idea applied to a case the
          section did not walk through directly.
{hard}

Difficulty comes from the reasoning the question demands, not from its length,
{surface}

Return the difficulty you would assign. When the question sits near the boundary
between two levels, return the requested one: only a clear mismatch, a full
level away, is worth reporting.

Also return one rationale of at most two sentences. If you disagree, say what
makes it the level you chose."""


def _generatability_system(profile: SubjectProfile) -> str:
    if profile.has_code_types:
        mismatch = """  - the requested question type does not fit the content, such as asking for
    output prediction from a section with no executable code."""
    else:
        mismatch = """  - the requested question type does not fit the content, such as asking for
    a numeric answer from a section with no quantities to work with."""
    return f"""You judge source material, not a question.

You are given a textbook section and a generation request: a difficulty and a
question type. Decide whether a sound assessment question matching that request
could be written from this section alone.

Answer false when the section cannot support the request, for example:
  - it is too thin to assess at all (a heading, a cross-reference, a fragment);
  - it teaches its material but cannot support the requested difficulty, because
    a harder question would need material the section does not contain;
{mismatch}

Answer true when a competent question is possible, even if you would find it
difficult to write.

No question is shown to you and you must not assume one exists or judge its
quality. You are deciding only whether this material affords the request.

Also return one rationale of at most two sentences naming the specific gap when
you answer false."""


_BUILDERS = {
    JudgeMetricId.ISSUES: _issues_system,
    JudgeMetricId.SUBTOPIC: _subtopic_system,
    JudgeMetricId.DIFFICULTY: _difficulty_system,
    JudgeMetricId.GENERATABILITY: _generatability_system,
}


def system_prompt_for(metric: JudgeMetricId, profile: SubjectProfile) -> str:
    """One judge's shipped system prompt for one subject."""
    return _BUILDERS[metric](profile)


def system_prompts_for(profile: SubjectProfile) -> dict[JudgeMetricId, str]:
    """All four judges' shipped system prompts for one subject."""
    return {metric: system_prompt_for(metric, profile) for metric in JudgeMetricId}


#: The Python profile's output: what every caller used before subjects existed.
JUDGE_ISSUE_CODES: tuple[RejectionReason, ...] = issue_codes_for(PYTHON_PROFILE)
ISSUES_SYSTEM = _issues_system(PYTHON_PROFILE)
SUBTOPIC_SYSTEM = _subtopic_system(PYTHON_PROFILE)
DIFFICULTY_SYSTEM = _difficulty_system(PYTHON_PROFILE)
GENERATABILITY_SYSTEM = _generatability_system(PYTHON_PROFILE)

SYSTEM_PROMPT_FOR: dict[JudgeMetricId, str] = {
    JudgeMetricId.ISSUES: ISSUES_SYSTEM,
    JudgeMetricId.SUBTOPIC: SUBTOPIC_SYSTEM,
    JudgeMetricId.DIFFICULTY: DIFFICULTY_SYSTEM,
    JudgeMetricId.GENERATABILITY: GENERATABILITY_SYSTEM,
}


def rubric_version_for(profile: SubjectProfile) -> str:
    """Name one subject's shipped judge panel.

    The Python panel keeps :data:`RUBRIC_VERSION`. Any other subject's prompts
    differ, so its panel gets a fingerprint of them: calibration must never pool
    two subjects' judges under one name (ADR-035).
    """
    prompts = system_prompts_for(profile)
    if prompts == SYSTEM_PROMPT_FOR:
        return RUBRIC_VERSION
    digest = hashlib.sha256(
        "\n\x00".join(prompts[metric] for metric in JudgeMetricId).encode("utf-8")
    ).hexdigest()[:10]
    return f"{RUBRIC_VERSION}+{digest}"


def build_user_prompt(metric: JudgeMetricId, context: JudgeContext) -> str:
    """Serialize exactly what one judge is allowed to see, as JSON."""
    payload: dict[str, object]
    match metric:
        case JudgeMetricId.ISSUES:
            payload = {
                "question": context.question_artifact,
                "source_sections": context.source_sections,
            }
        case JudgeMetricId.SUBTOPIC:
            payload = {
                "question": context.question_artifact,
                "claimed_taxonomy": context.claimed_taxonomy,
                "taxonomy": context.taxonomy,
                "source_sections": context.source_sections,
            }
        case JudgeMetricId.DIFFICULTY:
            payload = {
                "question": context.question_artifact,
                "requested_difficulty": context.requested_difficulty,
                "source_sections": context.source_sections,
            }
        case JudgeMetricId.GENERATABILITY:
            payload = {
                "requested_difficulty": context.requested_difficulty,
                "requested_question_type": context.requested_question_type,
                "source_sections": context.source_sections,
            }
    return json.dumps(payload, ensure_ascii=False)
