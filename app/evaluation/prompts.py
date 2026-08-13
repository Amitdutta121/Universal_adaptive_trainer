"""The four judge prompts, and the payload each judge is allowed to see.

One judge per metric. Each gets its own system prompt and its own payload, and
the payloads deliberately differ: the generatability judge is never shown the
question, because its subject is the source material and knowing that a question
already exists is exactly the bias that would stop it saying "this chunk could
not support one".
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.domain.enums import JudgeMetricId, RejectionReason

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


#: Issue codes the issues judge may return. The professor's full vocabulary
#: minus what the other three judges own (topic/subtopic, difficulty) and minus
#: ``TOO_SIMILAR_REPETITIVE``, which is a statement about the rest of the bank
#: that a judge looking at one question cannot make. ``OTHER`` is absent because
#: an unnamed problem goes in ``custom_issue`` as prose, where it is readable.
JUDGE_ISSUE_CODES: tuple[RejectionReason, ...] = (
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

_ISSUE_CODE_GUIDE = """\
  technically_incorrect      The question states something false about Python.
  incorrect_answer           The reference answer is wrong for the question asked.
  incorrect_tests            The tests do not test what the question asks for.
  not_grounded_in_source     It assesses material the supplied section does not teach.
  poor_distractors           Distractors are implausible, trivially eliminable, or
                             more than one is defensible as correct.
  poor_tests                 Tests run but are weak: they miss the core case or
                             pass for the wrong reason.
  ambiguous                  More than one answer is defensible as written.
  poor_wording               Confusing, grammatically broken, or unclear phrasing.
  not_pedagogically_useful   Answerable without exercising the intended skill, or
                             tests recall of trivia rather than understanding."""

ISSUES_SYSTEM = f"""You review one introductory-Python assessment question and report which known
problems it has. You do not decide whether to accept it.

The question has already passed deterministic checks: its code runs and its tests
execute. Do not re-check execution, syntax, or whether tests pass.

Select every issue code that genuinely applies, and only from this list:
{_ISSUE_CODE_GUIDE}

Report only problems a professor would act on. An imperfect but usable question
has no issues. Do not report an issue you cannot point to in the question text.
Do not judge topic, subtopic, or difficulty -- other reviewers cover those.

If you find a real, actionable problem that no code above describes, leave
issue_codes for what does apply and put that problem in custom_issue as one
sentence. Otherwise leave custom_issue null.

Return the selected codes, custom_issue, and one rationale of at most two
sentences naming the specific text that triggered each code. If nothing is
wrong, return an empty list and say why the question is sound."""

SUBTOPIC_SYSTEM = """You check one introductory-Python assessment question against the topic and
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
questions combine skills; incidental use of a loop in a question about string
methods is normal. A claim is right when the claimed subtopics are the skills
being assessed, even if they are not the only skills present.

Also return one rationale of at most two sentences. If you changed the tags, say
what the question actually assesses."""

DIFFICULTY_SYSTEM = """You check whether one introductory-Python assessment question matches its
requested difficulty: easy, medium, or hard.

Judge relative to a student who has just studied the supplied textbook section
and nothing beyond it -- not relative to a professional programmer.

  easy    One taught step, applied directly. The student recalls or applies a
          single idea from the section with no composition.
  medium  Two or three taught ideas combined, or one idea applied to a case the
          section did not walk through directly.
  hard    Several taught ideas composed, or careful reasoning about an edge case,
          execution order, or a subtle behaviour -- while still using only what
          the section teaches.

Difficulty comes from the reasoning the question demands, not from its length,
the amount of code shown, or unfamiliar variable names.

Return the difficulty you would assign. When the question sits near the boundary
between two levels, return the requested one: only a clear mismatch, a full
level away, is worth reporting.

Also return one rationale of at most two sentences. If you disagree, say what
makes it the level you chose."""

GENERATABILITY_SYSTEM = """You judge source material, not a question.

You are given a textbook section and a generation request: a difficulty and a
question type. Decide whether a sound assessment question matching that request
could be written from this section alone.

Answer false when the section cannot support the request, for example:
  - it is too thin to assess at all (a heading, a cross-reference, a fragment);
  - it teaches its material but cannot support the requested difficulty, because
    a harder question would need material the section does not contain;
  - the requested question type does not fit the content, such as asking for
    output prediction from a section with no executable code.

Answer true when a competent question is possible, even if you would find it
difficult to write.

No question is shown to you and you must not assume one exists or judge its
quality. You are deciding only whether this material affords the request.

Also return one rationale of at most two sentences naming the specific gap when
you answer false."""

SYSTEM_PROMPT_FOR: dict[JudgeMetricId, str] = {
    JudgeMetricId.ISSUES: ISSUES_SYSTEM,
    JudgeMetricId.SUBTOPIC: SUBTOPIC_SYSTEM,
    JudgeMetricId.DIFFICULTY: DIFFICULTY_SYSTEM,
    JudgeMetricId.GENERATABILITY: GENERATABILITY_SYSTEM,
}


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
