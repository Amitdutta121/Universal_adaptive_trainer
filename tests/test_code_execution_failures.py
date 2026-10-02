"""A sandbox outage is never a wrong answer; one executor is shared (C5 review fixes)."""

from __future__ import annotations

import httpx
import pytest

from app.adaptive.scoring import score_answer
from app.domain.enums import Difficulty, QuestionKind, QuestionType
from app.domain.questions import Question
from app.errors import CodeExecutionUnavailableError, DomainRuleError
from app.generation.schemas import ExecutableTestCase
from app.validation.runner import LocalCodeRunner
from graders import ExecutorError, get_executor, get_grader, set_executor
from graders.executors import RunRequest, RunResult
from graders.executors.piston import PistonExecutor


class _DownExecutor:
    def run(self, request: RunRequest) -> RunResult:
        return RunResult("", "sandbox at http://internal:2000 down", None, False, "down")


@pytest.fixture
def sandbox_down():
    set_executor(_DownExecutor)
    yield
    set_executor(None)


@pytest.fixture(autouse=True)
def _reset():
    yield
    set_executor(None)


CODING = Question(
    id=3,
    prompt="Echo.",
    question_type=QuestionType.CODING,
    kind=QuestionKind.TESTABLE_PROGRAM,
    difficulty=Difficulty.EASY,
    content={"tests": [{"stdin": "1", "stdout": "1"}]},
)


def test_an_outage_is_not_scored_and_names_no_internals(sandbox_down) -> None:
    with pytest.raises(CodeExecutionUnavailableError) as raised:
        score_answer(CODING, "print(input())")
    assert raised.value.status_code == 503
    assert "internal" not in f"{raised.value} {raised.value.detail}"


def test_the_grader_raises_rather_than_scoring_zero(sandbox_down) -> None:
    with pytest.raises(ExecutorError):
        get_grader("code.python.tests").grade({"tests": [{"stdout": "1"}]}, "print(1)")


def test_authoring_checks_report_an_outage_not_a_failing_check(sandbox_down) -> None:
    runner = LocalCodeRunner()
    with pytest.raises(CodeExecutionUnavailableError):
        runner.run_script("print(1)")
    with pytest.raises(CodeExecutionUnavailableError):
        runner.run_tests("print(1)", [ExecutableTestCase(stdout="1")])


def test_an_unreachable_piston_is_an_infra_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    executor = PistonExecutor(client=httpx.Client(transport=httpx.MockTransport(refuse)))
    result = executor.run(RunRequest(language="python", source="print(1)"))
    assert result.infra_error is not None
    assert result.exit_code is None


def test_a_piston_rejection_is_an_infra_error() -> None:
    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "run_timeout cannot exceed 30000"})

    executor = PistonExecutor(client=httpx.Client(transport=httpx.MockTransport(reject)))
    assert executor.run(RunRequest(language="python", source="")).infra_error is not None


def test_a_crashing_program_is_still_a_wrong_answer() -> None:
    scored = score_answer(CODING, "raise SystemExit(3)")
    assert (scored.score, scored.passed_tests, scored.total_tests) == (0.0, 0, 1)


def test_one_executor_is_shared_by_graders_and_authoring_checks() -> None:
    created = []

    class Counting(_DownExecutor):
        def __init__(self) -> None:
            created.append(self)

        def run(self, request: RunRequest) -> RunResult:
            return RunResult("1\n", "", 0, False)

    set_executor(Counting)
    runner = LocalCodeRunner()
    for _ in range(3):
        runner.run_tests(
            "print(1)", [ExecutableTestCase(stdout="1"), ExecutableTestCase(stdout="1")]
        )
    score_answer(CODING, "print(1)")
    assert len(created) == 1
    assert get_executor() is created[0]


def test_set_executor_closes_the_previous_one() -> None:
    closed = []

    class Closing(_DownExecutor):
        def close(self) -> None:
            closed.append(True)

    set_executor(Closing)
    get_executor()
    set_executor(None)
    assert closed == [True]


def test_an_unbuilt_capability_is_unmarkable_not_a_crash(monkeypatch) -> None:
    import app.adaptive.scoring as scoring

    def missing(capability: str):
        raise KeyError(capability)

    monkeypatch.setattr(scoring, "get_grader", missing)
    with pytest.raises(DomainRuleError):
        score_answer(CODING, "print(1)")
