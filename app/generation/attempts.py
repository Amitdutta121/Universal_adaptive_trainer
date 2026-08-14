"""Generate a question, and retry while it is defective (ADR-032).

Both generators -- base and personalized-context -- run the same steps: call the
model, check what came back, and build a question from it. Only the prompt
differs, so the retry loop lives here rather than in either of them.

Three kinds of defect trigger a retry, and they are treated alike because they
cost the same thing -- a call spent for a question that cannot be used:

* a **refused taxonomy claim**, checked against the approved tree;
* a **failed deterministic check**, from :mod:`app.validation`;
* a **malformed reply** that could not be read as a question at all.

The third is the odd one: nothing was produced to inspect, so there is no draft,
no claim and no report. It is still recorded as an attempt. ADR-020 turns off
Instructor's repair loop so that bad answers are not *silently* re-prompted --
the objection is to the silence, not to the retry, so this one is written onto
the question where it can be counted.

Measured on the second: of six questions that failed validation in the bank,
five failed a deterministic check and were stored broken after a single call,
because validation used to run only after this loop had already returned. Feeding
those failures back fixed them.

What this is *not*: repair. Nothing here edits the model's answer. The defect is
stated and the model writes again, so a corrected question is still its own. A
question still defective after the cap is returned as it stands, because the
caller stores it either way.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from app.domain.enums import ClaimViolation
from app.domain.questions import (
    GenerationAttempt,
    Question,
    QuestionCheck,
    QuestionValidationReport,
)
from app.errors import DomainRuleError, MalformedModelOutputError
from app.generation.schemas import TaxonomyClaim
from app.generation.spec import (
    MAX_CLAIMED_SUBTOPICS,
    TaxonomyClaimOutcome,
    check_claimed_taxonomy,
)
from app.llm import StructuredLLMClient
from app.persistence.models import CurriculumVersionRow

logger = logging.getLogger(__name__)

#: Generation calls one section may cost: the first attempt plus two corrections.
#: Capped because a model that has failed the same check twice is not converging,
#: and an uncapped loop would spend a professor's whole budget on one section.
MAX_GENERATION_ATTEMPTS = 3

#: How much of a provider's malformed-output complaint is kept on the attempt.
#: Enough to recognise the failure, not the whole validation dump.
MALFORMED_DETAIL_CHARS = 400

#: What to say when the reply was not a question. Observed failure: the model
#: returns the JSON *Schema* of the draft -- ``{"description": ..., "properties":
#: ..., "type": "object"}`` -- instead of an instance of it.
MALFORMED_CORRECTION = (
    "Your previous reply was not a question: it did not match the required "
    "structure. Do not repeat or describe the schema. Answer with a single JSON "
    "object whose fields are the question itself, with every required field "
    "filled in."
)


class QuestionValidator(Protocol):
    """The deterministic validator, injected so generation need not import it."""

    def validate(self, question: Question) -> QuestionValidationReport: ...


def _claim_instructions(outcome: TaxonomyClaimOutcome) -> list[str]:
    """Say which id to change, and what to change it to.

    Observed against a live model: stating "subtopic 106 is not under topic 11"
    and asking for a fresh classification produced the same id three times in a
    row. Describing a fault is not the same as naming the id to change.

    A cross-topic claim gets both ways out -- drop the subtopic, or move the topic
    to the one that owns it -- because a model that keeps naming a subtopic may be
    right about the subtopic and wrong about the topic. Which it meant is its
    decision, not this function's.
    """
    instructions: list[str] = []

    if ClaimViolation.UNKNOWN_TOPIC in outcome.violations:
        instructions.append(
            f"Topic id {outcome.claimed_topic_id} does not exist. Choose a topic id that "
            f"appears in the taxonomy above."
        )

    owned_ids = {owner.subtopic_id for owner in outcome.foreign_owners}
    unknown = [sid for sid in outcome.offending_subtopic_ids if sid not in owned_ids]
    if unknown:
        instructions.append(
            f"Remove subtopic id(s) {unknown} from subtopic_ids. No such subtopic exists "
            f"in the taxonomy."
        )

    for owner in outcome.foreign_owners:
        instructions.append(
            f"Subtopic {owner.subtopic_id} ({owner.subtopic_name}) belongs to topic "
            f"{owner.topic_id} ({owner.topic_name}), not to topic "
            f"{outcome.claimed_topic_id}. Either remove {owner.subtopic_id} from "
            f"subtopic_ids, or set topic_id to {owner.topic_id} and name only subtopics "
            f"of that topic."
        )

    if ClaimViolation.TOO_MANY_SUBTOPICS in outcome.violations:
        instructions.append(
            f"You named {len(set(outcome.claimed_subtopic_ids))} subtopics; at most "
            f"{MAX_CLAIMED_SUBTOPICS} are allowed. Keep only the ones the question "
            f"actually assesses."
        )

    if ClaimViolation.NO_SUBTOPIC in outcome.violations:
        instructions.append("Name at least one subtopic of the topic you choose.")

    return instructions


def _check_instructions(failed: list[QuestionCheck]) -> list[str]:
    """Turn failed checks into things to fix.

    A check's ``detail`` is often the *positive* label it would carry when it
    passes ("Reference solution parses"), so it is framed as a failure here
    rather than pasted in raw -- otherwise the correction reads as a list of
    things the model already did right.
    """
    instructions: list[str] = []
    for check in failed:
        instruction = f"Your question failed the check '{check.name}'"
        if check.detail:
            instruction += f" ({check.detail})"
        instruction += "."
        if check.evidence:
            instruction += f" {check.evidence}"
        instructions.append(instruction)
    return instructions


def build_correction(problems: list[str], previously_flagged: list[str]) -> str:
    """State this attempt's problems, and the ones already asked for.

    ``previously_flagged`` exists because the loop used to show only the latest
    attempt's faults. Observed consequence: attempt 1 was too verbose, attempt 2
    fixed the verbosity and unbalanced the options, attempt 3 -- no longer being
    told about verbosity -- became verbose again. Three calls, ending where it
    started. Carrying the history forward is what stops the oscillation.

    The taxonomy and the source text are already in the user prompt, so this block
    carries only the correction; repeating them would push it further from the
    instruction it corrects.
    """
    lines = ["--- correction ---", "Your previous answer was rejected. Do this:"]
    lines.extend(f"- {problem}" for problem in problems)
    outstanding = [item for item in previously_flagged if item not in problems]
    if outstanding:
        lines.append("")
        lines.append("You were already asked to fix these. Do not reintroduce them:")
        lines.extend(f"- {item}" for item in outstanding)
    lines.append("")
    lines.append("Write the question again, satisfying every point above.")
    lines.append("--- end correction ---")
    return "\n".join(lines)


def generate_with_retries(
    client: StructuredLLMClient,
    *,
    system: str,
    prompt: str,
    response_model: type[TaxonomyClaim],
    version: CurriculumVersionRow,
    build_question: Callable[[TaxonomyClaim, TaxonomyClaimOutcome], Question],
    validator: QuestionValidator | None = None,
    max_attempts: int = MAX_GENERATION_ATTEMPTS,
) -> tuple[Question, list[GenerationAttempt]]:
    """Return the final question, carrying its attempts and validation report.

    ``build_question`` turns a draft into an unpersisted
    :class:`~app.domain.questions.Question`; each generator supplies its own
    because only they know what else belongs on it. ``validator`` is injected
    rather than imported so that :mod:`app.generation` does not depend on
    :mod:`app.validation`; without one, only the taxonomy claim is checked.

    Returns as soon as an attempt is clean. After ``max_attempts`` the last
    question is returned with its defects recorded -- the question is real, and
    both what is wrong with it and how it got there are the caller's to store.

    A reply that is not a question at all costs an attempt like any other defect,
    and is recorded as one. Only if *every* attempt was malformed is there no
    question to return, and then the provider's own error is raised.

    Raises:
        DomainRuleError: ``max_attempts`` is below one, which would ask for a
            question without making a single call.
        MalformedModelOutputError: every attempt failed to produce a readable
            draft, so there is nothing to store.
    """
    if max_attempts < 1:
        raise DomainRuleError(
            "Generation needs at least one attempt.",
            detail=f"max_attempts was {max_attempts}.",
        )

    attempts: list[GenerationAttempt] = []
    flagged: list[str] = []
    question: Question | None = None
    correction = ""
    last_malformed: MalformedModelOutputError | None = None

    for number in range(1, max_attempts + 1):
        try:
            draft = client.complete_structured(
                system=system,
                prompt=prompt + correction,
                response_model=response_model,
            )
        except MalformedModelOutputError as exc:
            # The reply could not be read as a question, so there is nothing to
            # check, classify or store -- but it still cost a call, and a silent
            # re-ask would hide how often this happens. Record it and ask again.
            last_malformed = exc
            attempts.append(
                GenerationAttempt(
                    number=number,
                    detail=f"{exc.message} {exc.detail or ''}".strip()[:MALFORMED_DETAIL_CHARS],
                    malformed=True,
                    accepted=False,
                    model=client.description,
                )
            )
            logger.warning(
                "Generation attempt %s/%s was not a readable question: %s",
                number,
                max_attempts,
                exc.detail,
            )
            problem = MALFORMED_CORRECTION
            correction = "\n\n" + build_correction([problem], flagged)
            if problem not in flagged:
                flagged.append(problem)
            continue

        last_malformed = None
        outcome = check_claimed_taxonomy(
            version,
            topic_id=draft.topic_id,
            subtopic_ids=list(draft.subtopic_ids),
        )
        question = build_question(draft, outcome)

        attempt = GenerationAttempt(
            number=number,
            claimed_topic_id=outcome.claimed_topic_id,
            claimed_subtopic_ids=outcome.claimed_subtopic_ids,
            violations=outcome.violations,
            detail=outcome.detail,
            accepted=outcome.accepted,
            model=client.description,
        )
        attempts.append(attempt)
        # Attached before validating: the ``claimed_taxonomy_accepted`` check
        # reads the last recorded attempt, so it has to see this one.
        question.generation_attempts = list(attempts)

        failed: list[QuestionCheck] = []
        if validator is not None:
            report = validator.validate(question)
            question.validation_report = report
            failed = [check for check in report.checks if not check.passed]
            attempt.failed_checks = failed

        problems = _claim_instructions(outcome) + _check_instructions(failed)
        if not problems:
            break

        logger.warning(
            "Generation attempt %s/%s rejected: %s",
            number,
            max_attempts,
            "; ".join(problems),
        )
        correction = "\n\n" + build_correction(problems, flagged)
        for problem in problems:
            if problem not in flagged:
                flagged.append(problem)

    if question is None:
        if last_malformed is not None:
            # Every attempt was unreadable. There is no question to store, so the
            # provider's own error stands rather than being reshaped into a
            # domain one that hides what actually happened.
            raise last_malformed
        raise DomainRuleError(
            "Generation produced no question.",
            detail="The retry loop completed without making a model call.",
        )
    return question, attempts
