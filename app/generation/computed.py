"""Generate a computed-figure question: the LLM writes a program, the executor makes K copies.

ADR-080 point 3, PrairieLearn-style. For a style with ``figure: computed`` the model does not
write the question; it writes a program whose ``generate(seed)`` prints one JSON object with the
question, its figure (an SVG) and its answer fields. The configured executor runs it for K seeds
under a short timeout and an output cap (:mod:`app.figures.computed`); each copy is validated by
the question type's own ``draft_model`` and the deterministic validator, exactly like a written
draft. A program that fails is repaired once with its errors, or rejected -- never stored.

The accepted question stores copy 0 as its ``content`` (so review, judges, dedup and the solver
read it like any question), the program in ``figure_program``, and every copy as a
``question_variants`` row. SVGs are files (:func:`app.figures.storage.save_svg`); rows hold only
the key. A student is served one copy and scored against that copy's key (``app.adaptive``).

:func:`generate_computed_question` is the single entry point, so it can move to a job queue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.enums import QuestionType
from app.domain.questions import (
    GenerationAttempt,
    Question,
    QuestionCheck,
    QuestionValidationReport,
)
from app.errors import DomainRuleError, NotFoundError
from app.figures.computed import ComputedCopy, ProgramRun, RunLimits, run_program
from app.figures.schema import figure_problems
from app.figures.storage import save_svg
from app.generation.attempts import QuestionReview, QuestionValidator, generate_with_retries
from app.generation.base import DESCRIPTOR
from app.generation.schemas import MultipleChoiceDraft, TaxonomyClaim, shuffle_options
from app.generation.spec import QuestionSpec, TaxonomyClaimOutcome
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import CurriculumVersionRow, QuestionRow, QuestionVariantRow
from graders import get_executor
from graders.executors.base import Executor

#: The executor's language id for generated programs.
PROGRAM_LANGUAGE = "python"
#: Standard-library modules a program may import besides ``settings.executor_packages``:
#: computation and text only -- nothing that reaches files, processes, the network or the clock.
STDLIB_MODULES = frozenset(
    {
        "math",
        "cmath",
        "random",
        "statistics",
        "json",
        "io",
        "itertools",
        "functools",
        "collections",
        "heapq",
        "bisect",
        "fractions",
        "decimal",
        "string",
        "re",
        "textwrap",
        "dataclasses",
        "typing",
        "enum",
        "copy",
        "operator",
        "__future__",
    }
)
#: The first call plus one repair with the errors (the user's rule: repaired once or rejected).
MAX_PROGRAM_ATTEMPTS = 2
#: Taxonomy fields come from the reply, never from the program's printed object.
_TAXONOMY_KEYS = ("topic_id", "subtopic_ids")
#: Content keys that are not part of a copy the student answers.
_NOT_PRINTED = frozenset({*_TAXONOMY_KEYS, "figure", "sources", "model", "program"})


class ComputedProgramDraft(TaxonomyClaim):
    """What the model returns for a computed-figure question: a program, not a question."""

    program: str = Field(
        min_length=1,
        description="The complete program text. It defines generate(seed) as instructed.",
    )
    notes: str = Field(
        default="",
        description="Optional: one or two sentences on what varies between seeds.",
    )


@dataclass
class ComputedQuestionResult:
    """What one call produced. ``row`` is ``None`` when the program was rejected."""

    row: QuestionRow | None
    attempts: list[GenerationAttempt]
    #: Why the last attempt was rejected; empty when ``row`` is stored.
    problems: list[str] = field(default_factory=list)
    #: The stored copies, in ordinal order (empty when rejected).
    variants: list[QuestionVariantRow] = field(default_factory=list)


def limits_from_settings(settings: Settings) -> RunLimits:
    return RunLimits(
        language=PROGRAM_LANGUAGE,
        timeout_s=settings.computed_figure_timeout_seconds,
        max_output_bytes=settings.computed_figure_max_output_bytes,
        max_source_chars=settings.computed_figure_max_program_chars,
    )


def copy_seeds(copies: int) -> list[int]:
    """The seeds the copies are made with: fixed, so a program reruns to the same copies."""
    return list(range(1, copies + 1))


def allowed_modules(settings: Settings) -> frozenset[str]:
    return STDLIB_MODULES | frozenset(settings.executor_packages)


def program_instructions(question_type: QuestionType, settings: Settings | None = None) -> str:
    """The contract a computed-figure program must meet, appended to the generation prompt."""
    from app.question_types import get_type

    settings = settings or get_settings()
    schema = get_type(question_type).draft_model.model_json_schema()
    properties = {
        name: prop
        for name, prop in schema.get("properties", {}).items()
        if name not in _NOT_PRINTED
    }
    required = [name for name in schema.get("required", []) if name in properties]
    fields = json.dumps(
        {"properties": properties, "required": required, "$defs": schema.get("$defs", {})},
        ensure_ascii=False,
    )
    seeds = copy_seeds(settings.computed_figure_copies)
    packages = ", ".join(settings.executor_packages) or "none"
    stdlib = ", ".join(sorted(STDLIB_MODULES - {"__future__"}))
    cap_kb = settings.computed_figure_max_output_bytes // 1024
    timeout = settings.computed_figure_timeout_seconds
    return f"""--- computed figure ---
Do not write the question itself. Write a program that writes it, and put the program in
`program`; put topic_id and subtopic_ids in your reply beside it.

The program defines a top-level function `generate(seed)`. It is run once for each of the seeds
{seeds}. Each call must:
- make its own data from the seed (`rng = random.Random(seed)` or
  `numpy.random.default_rng(seed)`), so every seed gives a different version of equal difficulty;
- draw the figure from that data, and compute the answer fields from the same data, so the key
  always matches the figure;
- print exactly ONE line: `print(json.dumps(result))`, and print nothing else. `result` is an
  object with "prompt", "figure": {{"svg": <the SVG text>, "alt": <what the figure shows, in
  words, with the values a reader needs, without stating the answer>, "caption": <short or "">}},
  "explanation", and the answer fields below.

Answer fields of the printed object (JSON Schema):
{fields}

Limits -- a program that breaks one is rejected:
- Imports: only {packages}, and the standard modules {stdlib}.
- No network, no files (no open(), never savefig to a path), no subprocesses, no sleeping, no
  input.
- Each call must finish within {timeout:g} seconds: no large loops or simulations; keep data
  small (at most a few hundred values).
- Output at most {cap_kb} KB: draw with matplotlib (`matplotlib.use("Agg")`,
  `plt.rcParams["svg.fonttype"] = "none"`), save with
  `fig.savefig(buffer, format="svg")` into an `io.StringIO`, then `plt.close(fig)`; few points,
  no embedded images. Label every axis, series and node the question refers to.
- The figure must be needed to answer, and must not show the answer.
--- end computed figure ---"""


def _figure_pointer(course_id: int, copy: ComputedCopy) -> dict[str, Any]:
    pointer = {
        "kind": "computed",
        "file": save_svg(course_id, copy.svg),
        "alt": copy.alt,
        "caption": copy.caption,
    }
    problems = figure_problems(pointer)
    if problems:  # pragma: no cover - save_svg returns a valid key
        raise DomainRuleError("A computed figure could not be stored.", detail="; ".join(problems))
    return pointer


@dataclass(frozen=True)
class _Copy:
    """A checked copy ready to store: its content (figure pointer included) and columns."""

    seed: int
    content: dict[str, Any]
    prompt: str
    reference_solution: str | None
    tests: str | None


def _stored_copy(
    copy: ComputedCopy, *, question_type: QuestionType, taxonomy: dict[str, Any], course_id: int
) -> _Copy:
    from app.question_types import get_type

    module = get_type(question_type)
    draft = module.draft_model.model_validate({**copy.fields, **taxonomy})
    if isinstance(draft, MultipleChoiceDraft):
        # As for a written draft: the program's own answer position is not random.
        draft = shuffle_options(draft)
    columns = module.columns_from_draft(draft)
    content = {
        key: value
        for key, value in draft.model_dump(mode="json").items()
        if key not in _TAXONOMY_KEYS
    }
    content["figure"] = _figure_pointer(course_id, copy)
    return _Copy(copy.seed, content, columns.prompt, columns.reference_solution, columns.tests)


def _program_check(run: ProgramRun) -> QuestionCheck:
    return QuestionCheck(
        name="computed_program",
        passed=run.ok,
        detail=f"the program ran for {len(run.copies)} seed(s) and printed valid copies"
        if run.ok
        else "the program must run for every seed and print one valid question",
        evidence=None if run.ok else " ".join(run.problems),
    )


def generate_computed_question(
    session: Session,
    spec: QuestionSpec,
    *,
    version: CurriculumVersionRow,
    system: str,
    prompt: str,
    client: StructuredLLMClient | None = None,
    validator: QuestionValidator | None = None,
    review: QuestionReview | None = None,
    executor: Executor | None = None,
    sources: list[dict[str, object]] | None = None,
    round_id: int | None = None,
    personalization_context: dict[str, object] | None = None,
) -> ComputedQuestionResult:
    """Ask for a ``generate(seed)`` program, make K copies, store the question and its copies.

    ``system`` and ``prompt`` are the ordinary generation prompt for ``spec`` (the caller builds
    them with ``BaseQuestionGenerator.prepare`` as for any question, and passes its ``sources``
    and its ``instruction_stamp`` as ``personalization_context``); the computed-figure
    contract (:func:`program_instructions`) is appended here. ``review`` is the round's judge
    hook, run on copy 0 once the program and every copy pass.

    Stores (flushes, does not commit) only a usable result: a :class:`QuestionRow` with copy 0
    as ``content``, ``status`` from the validation report as for any generated question,
    ``style_id`` / ``round_id`` / ``target_subtopic_id`` from the spec, ``figure_program``, and
    one :class:`QuestionVariantRow` per seed. Judge evaluation and trust routing stay the
    caller's, as in ``GenerationService.generate_round_question``.

    Raises:
        DomainRuleError: the curriculum version belongs to no course (figures are per course).
        graders.ExecutorError: the executor could not run programs at all (not the program's
            fault, so no repair is spent on it).
        MalformedModelOutputError: every reply was unreadable.
    """
    from app.question_types import get_type
    from app.validation import get_question_validator

    if version.course_id is None:
        raise DomainRuleError(
            "Computed figures need a course.",
            detail=f"Curriculum version {version.id} belongs to no course.",
        )
    course_id = version.course_id
    settings = get_settings()
    module = get_type(spec.question_type)
    limits = limits_from_settings(settings)
    seeds = copy_seeds(settings.computed_figure_copies)
    modules = allowed_modules(settings)
    runner = executor or get_executor()
    checker = validator or get_question_validator(session)
    client = client or get_structured_client()
    asking = f"{prompt}\n\n{program_instructions(spec.question_type, settings)}"

    #: The last attempt's run and stored copies; the loop stops on the first clean attempt.
    last: dict[str, Any] = {"run": ProgramRun(problems=["no program was run"]), "copies": []}

    def build(draft: TaxonomyClaim, outcome: TaxonomyClaimOutcome) -> Question:
        assert isinstance(draft, ComputedProgramDraft)
        taxonomy = {"topic_id": draft.topic_id, "subtopic_ids": list(draft.subtopic_ids)}
        run = run_program(
            draft.program,
            seeds=seeds,
            draft_model=module.draft_model,
            taxonomy=taxonomy,
            executor=runner,
            limits=limits,
            allowed_modules=modules,
        )
        copies = (
            [
                _stored_copy(
                    copy, question_type=spec.question_type, taxonomy=taxonomy, course_id=course_id
                )
                for copy in run.copies
            ]
            if run.ok
            else []
        )
        last["run"], last["copies"] = run, copies
        first = copies[0] if copies else None
        content: dict[str, Any] = {**taxonomy, **first.content} if first else {}
        if sources is not None:
            content["sources"] = sources
        content["model"] = client.description
        # Shown back to the model on a repair (``render_draft``); moved to its own column on
        # storage, so it never reaches a student through ``content``.
        content["program"] = draft.program
        return Question(
            curriculum_version_id=spec.curriculum_version_id,
            topic_id=outcome.storable_topic_id,
            subtopic_ids=outcome.storable_subtopic_ids,
            kind=module.kind,
            question_type=spec.question_type,
            difficulty=spec.difficulty,
            # A failed run has no copy; the attempt is recorded and repaired, never stored.
            prompt=first.prompt if first else "(the program made no usable copy)",
            reference_solution=first.reference_solution if first else None,
            tests=first.tests if first else None,
            spec=spec.stored(),
            content=content,
            generator_kind=DESCRIPTOR.kind,
            generator_name=DESCRIPTOR.name,
            generator_version=DESCRIPTOR.version,
            personalization_context=personalization_context,
        )

    class _CopiesValidator:
        """The program check, then the deterministic validator on every copy."""

        def validate(self, question: Question) -> QuestionValidationReport:
            run: ProgramRun = last["run"]
            copies: list[_Copy] = last["copies"]
            if not run.ok or not copies:
                return QuestionValidationReport(checks=[_program_check(run)])
            report = checker.validate(question)
            checks = [_program_check(run), *report.checks]
            for number, copy in enumerate(copies[1:], start=2):
                other = question.model_copy(
                    update={
                        "prompt": copy.prompt,
                        "reference_solution": copy.reference_solution,
                        "tests": copy.tests,
                        "content": {**question.content, **copy.content},
                    }
                )
                for check in checker.validate(other).checks:
                    if not check.passed:
                        checks.append(
                            check.model_copy(
                                update={
                                    "detail": f"copy {number}, seed {copy.seed}: {check.detail}"
                                }
                            )
                        )
            return report.model_copy(update={"checks": checks})

    question, attempts = generate_with_retries(
        client,
        system=system,
        prompt=asking,
        response_model=ComputedProgramDraft,
        version=version,
        build_question=build,
        validator=_CopiesValidator(),
        review=review,
        max_attempts=MAX_PROGRAM_ATTEMPTS,
    )
    run: ProgramRun = last["run"]
    copies: list[_Copy] = last["copies"]
    final = attempts[-1] if attempts else None
    if final is None or not final.usable or not run.ok or not copies:
        problems = list(run.problems)
        if final is not None:
            problems += [
                f"{check.detail or check.name}: {check.evidence}"
                if check.evidence
                else (check.detail or check.name)
                for check in final.failed_checks
                if check.name != "computed_program"
            ]
            if final.detail:
                problems.append(final.detail)
        return ComputedQuestionResult(row=None, attempts=attempts, problems=problems)

    from app.generation.service import GenerationService
    from app.persistence.repositories import QuestionRepository

    content = dict(question.content or {})
    program = content.pop("program")
    question = question.model_copy(update={"content": content})
    row = GenerationService._row_from_question(question)
    row.style_id = spec.style_id
    row.round_id = round_id
    row.target_subtopic_id = spec.target_subtopic_id
    row.figure_program = program
    row = QuestionRepository(session).add(row)
    report = question.validation_report
    if report is not None:
        row.validation_report = report.model_copy(update={"question_id": row.id})
        row.status = report.resulting_status()
    variants = [
        QuestionVariantRow(
            question_id=row.id,
            course_id=course_id,
            seed=copy.seed,
            ordinal=ordinal,
            content=copy.content,
            prompt=copy.prompt,
            reference_solution=copy.reference_solution,
        )
        for ordinal, copy in enumerate(copies)
    ]
    session.add_all(variants)
    session.flush()
    return ComputedQuestionResult(row=row, attempts=attempts, variants=variants)


def regenerate_copy(
    session: Session,
    question_id: int,
    ordinal: int,
    *,
    executor: Executor | None = None,
    validator: QuestionValidator | None = None,
) -> QuestionVariantRow:
    """Replace one copy of a computed-figure question with its program run for a new seed.

    No model call: the stored program runs once more, for a seed none of the copies has used,
    and the new copy passes the same checks as at generation (the type's draft model, then the
    deterministic validator). Updates the copy in place and flushes; the caller commits and
    decides whether the question is judged again. Copy 0 is also the question's ``content``,
    so replacing it updates the question's prompt, key and content too.

    Raises:
        NotFoundError: the question, or its copy ``ordinal``, does not exist.
        DomainRuleError: the question has no program; a student has already been served this
            copy (what they were scored against is kept); or the new copy fails its checks
            (``detail`` lists why).
        graders.ExecutorError: the executor could not run programs at all.
    """
    from app.persistence.models import StudentAttemptRow
    from app.question_types import get_type
    from app.validation import get_question_validator

    row = session.get(QuestionRow, question_id)
    if row is None:
        raise NotFoundError("Question not found.", detail=f"No question {question_id}.")
    if not row.figure_program or row.question_type is None:
        raise DomainRuleError(
            "Only a computed-figure question has copies to regenerate.",
            detail=f"Question {question_id} has no figure program.",
        )
    variants = list(
        session.scalars(
            select(QuestionVariantRow)
            .where(QuestionVariantRow.question_id == question_id)
            .order_by(QuestionVariantRow.ordinal)
        )
    )
    variant = next((v for v in variants if v.ordinal == ordinal), None)
    if variant is None:
        raise NotFoundError(
            "Copy not found.", detail=f"Question {question_id} has no copy {ordinal}."
        )
    served = session.scalar(
        select(StudentAttemptRow.id).where(StudentAttemptRow.variant_id == variant.id).limit(1)
    )
    if served is not None:
        raise DomainRuleError(
            "A student has already answered this copy, so it is kept.",
            detail=f"Copy {ordinal} of question {question_id} was served in attempt {served}.",
        )
    settings = get_settings()
    module = get_type(row.question_type)
    seed = max(v.seed for v in variants) + 1
    taxonomy = {"topic_id": row.topic_id, "subtopic_ids": list(row.subtopic_ids)}
    run = run_program(
        row.figure_program,
        seeds=[seed],
        draft_model=module.draft_model,
        taxonomy=taxonomy,
        executor=executor or get_executor(),
        limits=limits_from_settings(settings),
        allowed_modules=allowed_modules(settings),
    )
    if not run.ok:
        raise DomainRuleError(
            "The program could not make a new copy.", detail=" ".join(run.problems)
        )
    copy = _stored_copy(
        run.copies[0],
        question_type=row.question_type,
        taxonomy=taxonomy,
        course_id=variant.course_id,
    )
    if any(other.content == copy.content for other in variants if other is not variant):
        raise DomainRuleError(
            "The new copy is the same as another copy.",
            detail=f"Seed {seed} reproduced an existing copy of question {question_id}.",
        )
    question = Question.model_validate(row).model_copy(
        update={
            "prompt": copy.prompt,
            "reference_solution": copy.reference_solution,
            "tests": copy.tests,
            "content": {**(row.content or {}), **copy.content},
        }
    )
    failed = [
        check
        for check in (validator or get_question_validator(session)).validate(question).checks
        if not check.passed
    ]
    if failed:
        raise DomainRuleError(
            "The new copy fails its checks.",
            detail="; ".join(check.detail or check.name for check in failed),
        )
    variant.seed = seed
    variant.content = copy.content
    variant.prompt = copy.prompt
    variant.reference_solution = copy.reference_solution
    if ordinal == 0:
        row.prompt = copy.prompt
        row.reference_solution = copy.reference_solution
        row.tests = copy.tests
        row.content = question.content
    session.flush()
    return variant


__all__ = [
    "MAX_PROGRAM_ATTEMPTS",
    "ComputedProgramDraft",
    "ComputedQuestionResult",
    "allowed_modules",
    "copy_seeds",
    "generate_computed_question",
    "limits_from_settings",
    "program_instructions",
    "regenerate_copy",
]
