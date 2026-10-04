"""Custom rule judges: professor-written rules every generated question must pass.

The round generator (docs/QUESTION_SETUP_PLAN.md, agent B) calls :func:`run_custom_judges`
inside its retry loop, so a failing rule triggers a regeneration with ``reason`` as the
correction.

Rules are not :class:`~app.domain.enums.JudgeMetricId` metrics: they are per-taxonomy data
(``CustomJudgeRow``) and their results are stored on ``QuestionEvaluationRow.custom_results``
as ``[CustomJudgeResult.model_dump(mode="json"), ...]`` (see
:func:`app.evaluation.batch_service.record_evaluation`).

Two kinds:

* ``PATTERN`` -- deterministic, no model call. ``pattern`` names what the rule *forbids*:
  a regex (``\\bglobal\\b``), or ``ast:`` plus Python syntax node types (``ast:Global``),
  checked against the question's code. A match fails the question.
* ``LLM`` -- one yes/no structured call per rule, with a one-sentence reason.
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import Iterator, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import CustomJudgeKind
from app.domain.questions import Question
from app.errors import AdaptiveTrainerError
from app.llm import StructuredLLMClient, get_structured_client
from app.persistence.models import CustomJudgeRow
from app.persistence.repositories import CustomJudgeRepository

logger = logging.getLogger(__name__)

#: A ``PATTERN`` rule whose pattern starts with this checks Python syntax instead of text:
#: ``ast:Global,Nonlocal`` fails a question whose code contains either node type.
AST_PREFIX = "ast:"

#: Content keys whose string values are code, wherever they sit in ``Question.content``.
_CODE_KEYS = frozenset({"code", "reference_solution", "solution", "starter_code", "assert"})
#: A fenced code block in a markdown prompt.
_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


class CustomRule(BaseModel):
    """One enabled rule, detached from its row so the runner needs no session."""

    model_config = ConfigDict(frozen=True)

    id: int
    rule_text: str
    kind: CustomJudgeKind
    #: What a ``PATTERN`` rule forbids (regex or ``ast:`` node types); ``None`` for ``LLM``.
    pattern: str | None = None

    @classmethod
    def from_row(cls, row: CustomJudgeRow) -> CustomRule:
        return cls(id=row.id, rule_text=row.rule_text, kind=row.kind, pattern=row.pattern)


class CustomJudgeResult(BaseModel):
    """What one rule said about one question."""

    #: ``CustomJudgeRow.id`` of the rule.
    judge_id: int
    #: The rule text at the time it was judged, so a later edit does not rewrite history.
    rule_text: str
    kind: CustomJudgeKind
    #: ``True`` passes, ``False`` fails, ``None`` means the judge could not answer (model
    #: error, unreadable pattern). ``None`` is an absent measurement, not a failure: it never
    #: triggers a regeneration.
    passed: bool | None
    #: Why it failed, phrased so it can be fed back to the generator as a correction.
    #: ``None`` when it passed.
    reason: str | None = None


class RuleVerdict(BaseModel):
    """What the model answers for one ``LLM`` rule."""

    passes: bool
    #: One sentence: why it fails, phrased as a fix the question writer should make.
    reason: str = Field(min_length=1, max_length=400)


RULE_SYSTEM_PROMPT = (
    "You check one generated exam question against one rule written by the course "
    "professor. Answer whether the question (its prompt, code, reference solution and "
    "tests) follows the rule. Judge only this rule, nothing else about the question. "
    "Give a one-sentence reason; when it does not follow the rule, phrase the reason as "
    "the fix the question writer should make."
)


def validate_pattern(pattern: str) -> None:
    """Raise ``ValueError`` when a ``PATTERN`` rule's pattern cannot be checked."""
    if pattern.startswith(AST_PREFIX):
        names = _ast_names(pattern)
        if not names:
            raise ValueError("An ast: pattern must name at least one node type, e.g. ast:Global.")
        unknown = [name for name in names if not _is_ast_node(name)]
        if unknown:
            raise ValueError(f"Unknown Python syntax node type(s): {', '.join(unknown)}.")
        return
    if not pattern.strip():
        raise ValueError("A pattern rule needs a pattern.")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"The pattern is not a valid regular expression: {exc}.") from exc


def load_rules(session: Session, curriculum_version_id: int | None) -> list[CustomRule]:
    """The enabled rules of one taxonomy, oldest first; ``[]`` without a taxonomy."""
    if curriculum_version_id is None:
        return []
    rows = CustomJudgeRepository(session).list_for_version(curriculum_version_id, enabled_only=True)
    return [CustomRule.from_row(row) for row in rows]


def run_custom_judges(
    question: Question,
    rules: Sequence[CustomRule],
    *,
    client: StructuredLLMClient | None = None,
) -> list[CustomJudgeResult]:
    """Judge one question against every rule, returning one result per rule, in rule order.

    ``PATTERN`` rules match ``pattern`` against the question's code -- fenced blocks in the
    prompt, the reference solution, the tests, and code fields of ``content`` -- or against
    the whole prompt when the question carries no code. No model call. ``LLM`` rules make
    one yes/no structured call each via ``client`` (default: the judge client at
    ``judge_temperature``, created only if an ``LLM`` rule is present). Never raises for a
    single rule's failure -- that rule's result has ``passed=None``. An empty ``rules``
    returns ``[]`` without touching the client. Persists nothing; the caller stores the
    results.
    """
    results: list[CustomJudgeResult] = []
    llm = client
    for rule in rules:
        if rule.kind is CustomJudgeKind.PATTERN:
            results.append(_run_pattern(question, rule))
            continue
        if llm is None:
            try:
                llm = get_structured_client(temperature=get_settings().judge_temperature)
            except (AdaptiveTrainerError, OSError) as exc:
                logger.warning("No model for custom rule %s: %s", rule.id, exc)
                results.append(_unanswered(rule))
                continue
        results.append(_run_llm(question, rule, llm))
    return results


def _run_pattern(question: Question, rule: CustomRule) -> CustomJudgeResult:
    pattern = rule.pattern or ""
    try:
        validate_pattern(pattern)
    except ValueError:
        logger.warning("Custom rule %s has an unusable pattern %r.", rule.id, pattern)
        return _unanswered(rule)
    sources = list(_code_sources(question))
    if pattern.startswith(AST_PREFIX):
        names = set(_ast_names(pattern))
        found = sorted(
            {
                type(node).__name__
                for source in sources
                for node in _parse_nodes(source)
                if type(node).__name__ in names
            }
        )
        if found:
            return _failed(
                rule, f"Rule broken: {rule.rule_text} (the code uses {', '.join(found)})."
            )
        return _passed(rule)
    compiled = re.compile(pattern, re.MULTILINE)
    for source in sources:
        match = compiled.search(source)
        if match is not None:
            excerpt = " ".join(match.group(0).split())[:80]
            return _failed(rule, f"Rule broken: {rule.rule_text} (found {excerpt!r}).")
    return _passed(rule)


def _run_llm(
    question: Question, rule: CustomRule, client: StructuredLLMClient
) -> CustomJudgeResult:
    prompt = f"Rule: {rule.rule_text}\n\nQuestion:\n{_render_question(question)}"
    try:
        verdict = client.complete_structured(
            system=RULE_SYSTEM_PROMPT, prompt=prompt, response_model=RuleVerdict
        )
    except (AdaptiveTrainerError, OSError, ValueError) as exc:
        logger.warning("Custom rule %s could not be judged: %s", rule.id, exc)
        return _unanswered(rule)
    if verdict.passes:
        return _passed(rule)
    return _failed(rule, verdict.reason.strip())


def _render_question(question: Question) -> str:
    parts = [f"Prompt:\n{question.prompt}"]
    if question.reference_solution:
        parts.append(f"Reference solution:\n{question.reference_solution}")
    if question.tests:
        parts.append(f"Tests:\n{question.tests}")
    code = list(_content_code(question.content or {}))
    if code:
        parts.append("Code:\n" + "\n\n".join(code))
    return "\n\n".join(parts)


def _code_sources(question: Question) -> Iterator[str]:
    """Every piece of code the question carries; the prompt itself if it has none."""
    found = False
    for block in _FENCE.findall(question.prompt):
        found = True
        yield block
    extra = (question.reference_solution, question.tests, *_content_code(question.content or {}))
    for text in extra:
        if text and text.strip():
            found = True
            yield text
    if not found:
        yield question.prompt


def _content_code(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _CODE_KEYS and isinstance(item, str):
                yield item
            else:
                yield from _content_code(item)
    elif isinstance(value, list):
        for item in value:
            yield from _content_code(item)


def _ast_names(pattern: str) -> list[str]:
    return [name.strip() for name in pattern[len(AST_PREFIX) :].split(",") if name.strip()]


def _is_ast_node(name: str) -> bool:
    node = getattr(ast, name, None)
    return isinstance(node, type) and issubclass(node, ast.AST)


def _parse_nodes(source: str) -> Iterator[ast.AST]:
    """The syntax nodes of ``source``; nothing when it is not parseable Python."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return iter(())
    return ast.walk(tree)


def _passed(rule: CustomRule) -> CustomJudgeResult:
    return CustomJudgeResult(
        judge_id=rule.id, rule_text=rule.rule_text, kind=rule.kind, passed=True
    )


def _failed(rule: CustomRule, reason: str) -> CustomJudgeResult:
    return CustomJudgeResult(
        judge_id=rule.id, rule_text=rule.rule_text, kind=rule.kind, passed=False, reason=reason
    )


def _unanswered(rule: CustomRule) -> CustomJudgeResult:
    return CustomJudgeResult(
        judge_id=rule.id, rule_text=rule.rule_text, kind=rule.kind, passed=None
    )
