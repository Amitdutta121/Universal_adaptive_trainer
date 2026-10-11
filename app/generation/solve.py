"""Blind solve: can other models answer a round question from what the student sees?

A multiple-choice or true/false question is shown to a few small models without its key or
explanation. Each answers it and lists every option it thinks is correct. A question is
flagged when any solver picks a different answer, or finds zero or several correct options.

Measured on 49 professor-labelled questions (19 flawed, 30 good): Claude Haiku 4.5 and
DeepSeek, zero-shot, flagged about 14 of the 19 flawed and 1 of the 30 good. Few-shot
examples made it worse, so there are none. It finds wrong keys, two correct options and
missing information. It does not find code that does not run: solvers read code charitably.

The solver's finding is the correction for the next attempt (a targeted repair). Never
raises: an unavailable solver is skipped, and without any answer there is no flag.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import instructor
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.domain.enums import QuestionType
from app.domain.questions import Question
from app.llm import StructuredLLMClient
from app.llm.client import InstructorStructuredClient

logger = logging.getLogger(__name__)

LETTERS = "ABCDEFGH"

SOLVE_SYSTEM = (
    "You are a careful student taking an intro Python quiz. Answer from the question alone. "
    "Then audit the question: list EVERY option that is correct, and report anything "
    "ambiguous, contradictory, or impossible (e.g. no option is right). An option is correct "
    "when a careful Python teacher would mark it right as written. If the question asks for "
    "the best or most appropriate option, list only the best one."
)


class SolveVerdict(BaseModel):
    """One solver's answer and audit of a question it saw without the key."""

    answer: str = Field(description='The option letter you would choose, or "NONE".')
    correct_options: list[str] = Field(description="Every option letter that is correct.")
    exactly_one_correct: bool = Field(description="True when exactly one option is correct.")
    problems: str = Field(default="", description="Short text, or empty when none.")


@dataclass(frozen=True)
class SolveFinding:
    """A solver that disagrees with the key."""

    model: str
    verdict: SolveVerdict

    def describe(self, key: str) -> str:
        """One sentence for the correction and the review card."""
        name = self.model.split("/")[-1]
        correct = sorted({option.upper() for option in self.verdict.correct_options})
        if self.verdict.answer.upper() != key:
            said = f"{name} answered {self.verdict.answer} (key is {key})"
        elif len(correct) != 1:
            said = f"{name} finds {', '.join(correct) or 'no option'} correct"
        else:
            said = f"{name} doubts the key"
        return f"{said}: {self.verdict.problems}" if self.verdict.problems else said


def student_view(question: Question) -> tuple[str, str] | None:
    """The question text a student sees and its key letter; ``None`` when not solvable."""
    content = question.content or {}
    if question.question_type is QuestionType.MULTIPLE_CHOICE:
        options = [str(option) for option in content.get("options") or []]
        index = content.get("correct_option_index")
        if not options or not isinstance(index, int) or index >= len(options):
            return None
        key = LETTERS[index]
    elif question.question_type is QuestionType.TRUE_FALSE:
        if not isinstance(content.get("correct_answer"), bool):
            return None
        options = ["True", "False"]
        key = "A" if content["correct_answer"] else "B"
    else:
        return None
    parts = [question.prompt or ""]
    if content.get("code"):
        parts.append(str(content["code"]))
    choices = "\n".join(f"{LETTERS[i]}. {option}" for i, option in enumerate(options))
    return "\n\n".join(parts) + f"\n\nOptions:\n{choices}", key


def disagrees(verdict: SolveVerdict, key: str) -> bool:
    """The flag rule of the measurement: another answer, or not exactly one correct option."""
    correct = {option.strip().upper() for option in verdict.correct_options}
    return (
        verdict.answer.strip().upper() != key
        or len(correct) != 1
        or verdict.exactly_one_correct is False
    )


#: Returns the solvers that disagree with the key; empty when all agree or none answered.
BlindSolve = Callable[[Question], Sequence[SolveFinding]]


class BlindSolver:
    """The :data:`BlindSolve` of a round: one call per solver model, in parallel."""

    def __init__(
        self,
        models: Sequence[str] | None = None,
        *,
        settings: Settings | None = None,
        clients: dict[str, StructuredLLMClient] | None = None,
    ) -> None:
        self._settings = settings
        self._models = list(models) if models is not None else None
        self._clients = clients

    def _solvers(self) -> dict[str, StructuredLLMClient]:
        if self._clients is not None:
            return self._clients
        settings = self._settings or get_settings()
        models = self._models if self._models is not None else settings.blind_solve_models
        if not models or settings.llm_api_key is None:
            return {}
        return {
            model: InstructorStructuredClient(
                settings.model_copy(update={"llm_model": model}),
                temperature=0.0,
                # Solvers are other vendors' models; some fence their JSON.
                mode=instructor.Mode.MD_JSON,
            )
            for model in models
        }

    def __call__(self, question: Question) -> list[SolveFinding]:
        view = student_view(question)
        if view is None:
            return []
        text, key = view
        try:
            solvers = self._solvers()
        except Exception:
            logger.warning("blind solve skipped", exc_info=True)
            return []
        if not solvers:
            return []

        def solve(item: tuple[str, StructuredLLMClient]) -> SolveFinding | None:
            model, client = item
            try:
                verdict = client.complete_structured(
                    system=SOLVE_SYSTEM, prompt=text, response_model=SolveVerdict
                )
            except Exception:
                logger.warning("blind solver %s skipped", model, exc_info=True)
                return None
            return SolveFinding(model, verdict) if disagrees(verdict, key) else None

        with ThreadPoolExecutor(max_workers=len(solvers)) as pool:
            return [finding for finding in pool.map(solve, solvers.items()) if finding]
