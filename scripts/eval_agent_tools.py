"""Tool-call evals for the course assistant: does the agent call the right tools, in order?

**Spends API: the ``agent`` role's model (Azure ``gpt-5-mini`` with ``LLM_ROUTE=azure``) for
every turn of every case, about 3-8 model calls per turn; the whole set is well under a dollar.**
The inner model calls the agent's tools make (curriculum drafting, style and recipe planning,
style and recipe drafting) are faked with fixed replies, so only the agent's own decisions are
measured and each case is cheap and repeatable. Nothing touches ``data/adaptive_trainer.db``:
every run uses a fresh SQLite file in a temporary folder.

    python -m scripts.eval_agent_tools                       # every case
    python -m scripts.eval_agent_tools --case subject_preset_mismatch --case revise_styles_only
    python -m scripts.eval_agent_tools --out data/eval_agent_tools.json

Cases live in ``tests/fixtures/agent_tool_cases.yaml``. Each one seeds a course (subject,
question types, material), plays its turns as the professor, decides any approval cards the
way the case says, and checks the tool calls of its last turn (``expect``) and of the whole
case (``expect_all``) with :func:`check`. Exit status 1 when any case fails.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CASES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "agent_tool_cases.yaml"
OWNER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e1")
#: Model requests one agent run may make before the case fails (a run that loops on tools).
REQUEST_LIMIT = 25

# -- What a run did ---------------------------------------------------------------------------


@dataclass
class Call:
    name: str
    args: dict[str, Any]
    id: str = ""
    #: True when the call ended the run with an approval card instead of running.
    pending: bool = False


@dataclass
class Turn:
    message: str
    calls: list[Call] = field(default_factory=list)
    text: str = ""
    error: str | None = None


def calls_of(messages: list[Any], start: int) -> list[Call]:
    """Every tool call the model made in ``messages[start:]``, in order."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    calls = []
    for message in messages[start:]:
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    calls.append(Call(part.tool_name, part.args_as_dict(), part.tool_call_id))
    return calls


# -- Checks -----------------------------------------------------------------------------------


def _matches(value: Any, expected: Any) -> bool:
    if isinstance(expected, dict) and set(expected) <= {"in", "not", "contains", "not_in"}:
        if "in" in expected and value not in expected["in"]:
            return False
        if "not_in" in expected and value in expected["not_in"]:
            return False
        if "not" in expected and value == expected["not"]:
            return False
        needle = str(expected.get("contains", "")).lower()
        return needle in str(value).lower()
    return value == expected


def check(calls: list[Call], text: str, expect: dict[str, Any]) -> list[str]:
    """Why ``calls`` and the reply ``text`` fail ``expect``; empty when they pass.

    Keys: ``include`` (each tool called), ``exclude`` (none of them called), ``order`` (pairs
    ``[a, b]``: the first ``a`` comes before the first ``b``, and ``b`` is called), ``max``
    (tool -> most calls allowed), ``args`` (tool -> field -> value or ``{in, not_in, not,
    contains}``, on every call of the tool), ``pending`` (tools that must end the turn with an
    approval card), ``not_pending`` (tools that must not), ``text_excludes`` (regexes the reply
    must not match), ``text_max_chars``, ``any_of`` (at least one of these tools called).
    """
    names = [c.name for c in calls]
    problems = []
    for name in expect.get("include", []):
        if name not in names:
            problems.append(f"{name} was not called")
    for name in expect.get("exclude", []):
        if name in names:
            problems.append(f"{name} was called")
    if (group := expect.get("any_of")) and not set(group) & set(names):
        problems.append(f"none of {group} was called")
    for first, then in expect.get("order", []):
        if then not in names:
            problems.append(f"{then} was not called (expected after {first})")
        elif first not in names or names.index(first) > names.index(then):
            problems.append(f"{first} did not come before {then}")
    for name, most in expect.get("max", {}).items():
        if names.count(name) > most:
            problems.append(f"{name} called {names.count(name)} times (max {most})")
    for name, fields in expect.get("args", {}).items():
        for call in (c for c in calls if c.name == name):
            for key, wanted in fields.items():
                if not _matches(call.args.get(key), wanted):
                    problems.append(f"{name}.{key} = {call.args.get(key)!r}, wanted {wanted!r}")
    pending = {c.name for c in calls if c.pending}
    for name in expect.get("pending", []):
        if name not in pending:
            problems.append(f"{name} did not wait for approval")
    for name in expect.get("not_pending", []):
        if name in pending:
            problems.append(f"{name} asked for approval")
    for pattern in expect.get("text_excludes", []):
        if re.search(pattern, text, flags=re.IGNORECASE):
            problems.append(f"reply matches {pattern!r}")
    if (most := expect.get("text_max_chars")) and len(text) > most:
        problems.append(f"reply is {len(text)} chars (max {most})")
    return problems


# -- Fixed replies for the tools' own model calls -----------------------------------------------


def _curriculum(case: dict[str, Any]) -> dict[str, Any]:
    topics = case.get("curriculum") or [
        {"name": "Foundations", "subtopics": ["Core ideas", "Key terms"]},
        {"name": "Methods", "subtopics": ["First method", "Second method", "Comparing methods"]},
    ]
    return {
        "analysis": "From the syllabus.",
        "label": case.get("title", "Course"),
        "topics": [
            {
                "name": t["name"],
                "subtopics": [{"name": s, "description": f"{s}."} for s in t["subtopics"]],
            }
            for t in topics
        ],
        "out_of_scope": ["Projects and demos"],
    }


class FixedReplies:
    """Answers each structured call by the reply model it asks for; counts the calls."""

    description = "eval/fixed"

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case
        self.lock = threading.Lock()
        self.count = 0

    def complete_structured(self, *, system, prompt, response_model, history=()):
        from app.tutorials.experimental import RecipeDraft

        with self.lock:
            self.count += 1
        name = response_model.__name__
        keys = [f"T{t}.S{s}" for t, topic in enumerate(_curriculum(self.case)["topics"], 1)
                for s in range(1, len(topic["subtopics"]) + 1)]  # fmt: skip
        if name == "_DraftTaxonomy":
            reply: dict[str, Any] = _curriculum(self.case)
        elif name == "_StylePlan":
            reply = {
                "reasoning": "-",
                "styles": [
                    {"key": "s1", "name": "Pick the right idea", "question_type": "multiple_choice",
                     "summary": "Choose the statement that holds."},
                    {"key": "s2", "name": "True or not", "question_type": "true_false",
                     "summary": "Judge one claim."},
                ],
                "assignments": [{"subtopic": k, "styles": ["s1", "s2"]} for k in keys],
            }  # fmt: skip
        elif name == "_RecipePlan":
            reply = {
                "reasoning": "-",
                "recipes": [{"key": "r1", "name": "Worked explanation", "form": "markdown",
                             "summary": "A short worked explanation."}],
                "assignments": [{"subtopic": k, "recipes": ["r1"]} for k in keys],
            }  # fmt: skip
        elif response_model is RecipeDraft:
            reply = {
                "slug": "worked_explanation", "name": "Worked explanation",
                "summary": "A short worked explanation.", "renderer": "markdown",
                "prompt": "Explain the subtopic with one worked example.", "fits": ["concept"],
                "guidance_levels": ["worked"], "inputs": ["subtopic", "chunks"], "checks": [],
            }  # fmt: skip
        else:
            raise RuntimeError(f"eval has no fixed reply for {name}")
        return response_model.model_validate(reply)


# -- Running one case -------------------------------------------------------------------------


def _seed(case: dict[str, Any]) -> int:
    from app.persistence.database import get_session_factory
    from app.persistence.models import CourseRow
    from tests.book_documents import chunked_book

    with get_session_factory()() as session:
        course = CourseRow(
            name=case.get("course_name", case.get("title", "Course")),
            subject=case.get("subject"),
            owner_id=OWNER_ID,
            question_types=case.get("question_types") or [],
        )
        session.add(course)
        session.flush()
        for material in case.get("material", []):
            chunked_book(
                session,
                {
                    "title": material["title"],
                    "chapters": [{"sections": [{"text": part} for part in material["sections"]]}],
                },
                course_id=course.id,
            )
        session.commit()
        return course.id


def run_case(case: dict[str, Any], model: Any) -> dict[str, Any]:
    from pydantic_ai import DeferredToolRequests, DeferredToolResults
    from pydantic_ai.usage import UsageLimits

    LIMITS = UsageLimits(request_limit=REQUEST_LIMIT)

    from app.agent.agent import professor_agent
    from app.agent.tools import AgentDeps
    from app.persistence.database import get_session_factory

    course_id = _seed(case)
    fixed = FixedReplies(case)
    deps = AgentDeps(
        session_factory=get_session_factory(),
        course_id=course_id,
        user_id=OWNER_ID,
        queue=_NoQueue(),
        draft_client=fixed,
        generation_client=fixed,
        setup_client=fixed,
        tutorial_client=fixed,
    )
    history: list[Any] = []
    turns: list[Turn] = []
    #: Tools whose approval cards the professor approves in this case; any other card ends
    #: the turn unanswered.
    approve = set(case.get("approve", []))
    started = time.monotonic()
    for number, message in enumerate(case["turns"], start=1):
        is_last = number == len(case["turns"])
        turn = Turn(message)
        turns.append(turn)
        try:
            result = professor_agent.run_sync(
                message, model=model, deps=deps, message_history=history, usage_limits=LIMITS
            )
            start = len(history)
            for _ in range(4):  # approval rounds within one turn
                turn.calls += calls_of(result.all_messages(), start)
                start = len(result.all_messages())
                if not isinstance(result.output, DeferredToolRequests):
                    turn.text = str(result.output)
                    break
                waiting = {c.tool_call_id: c.tool_name for c in result.output.approvals}
                for call in turn.calls:
                    call.pending = call.pending or call.id in waiting
                if is_last and not set(waiting.values()) <= approve:
                    break  # the card stays open: what the case checks
                # Cards the case approves are approved; before a later turn, any other is
                # rejected, as the professor would have to answer it to go on.
                result = professor_agent.run_sync(
                    model=model,
                    deps=deps,
                    usage_limits=LIMITS,
                    message_history=result.all_messages(),
                    deferred_tool_results=DeferredToolResults(
                        approvals={tool_id: name in approve for tool_id, name in waiting.items()}
                    ),
                )
            history = result.all_messages()
        except Exception as exc:  # a case that crashes fails, it does not stop the run
            turn.error = f"{type(exc).__name__}: {exc}"
            break
    last = turns[-1]
    all_calls = [c for t in turns for c in t.calls]
    problems = [] if last.error is None else [f"run failed: {last.error}"]
    problems += check(last.calls, last.text, case.get("expect", {}))
    problems += [f"(whole case) {p}" for p in check(all_calls, "", case.get("expect_all", {}))]
    return {
        "id": case["id"],
        "category": case.get("category", ""),
        "passed": not problems,
        "problems": problems,
        "seconds": round(time.monotonic() - started, 1),
        "inner_model_calls": fixed.count,
        "turns": [
            {
                "message": t.message,
                "calls": [
                    {"name": c.name, "args": _short(c.args), "pending": c.pending} for c in t.calls
                ],
                "reply": t.text,
                "error": t.error,
            }
            for t in turns
        ],
    }


def _report(result: dict[str, Any]) -> dict[str, Any]:
    """Print one finished case at once, so a long run shows its progress."""
    mark = "PASS" if result["passed"] else "FAIL"
    print(f"[{mark}] {result['id']} ({result['seconds']}s)", flush=True)
    return result


def _short(args: dict[str, Any]) -> dict[str, Any]:
    return {k: (v[:120] + "..." if isinstance(v, str) and len(v) > 120 else v)
            for k, v in args.items()}  # fmt: skip


class _NoQueue:
    """Generation is never started by these cases; record it if the agent tries."""

    def submit(self, func, /, *args, **kwargs) -> None:
        raise RuntimeError("eval: the agent started background work")


# -- Main ---------------------------------------------------------------------------------------


def _fresh_database(folder: Path) -> None:
    from app.config import get_settings
    from app.persistence import database
    from app.persistence.models import UserRow

    os.environ["DATABASE_URL"] = f"sqlite:///{(folder / 'eval.db').as_posix()}"
    os.environ["BOOK_UPLOAD_DIR"] = str(folder / "books")
    get_settings.cache_clear()
    database.reset_engine_for_testing()
    database.init_db(database.get_engine())
    with database.get_session_factory()() as session:
        session.add(
            UserRow(id=OWNER_ID, email="eval@example.com", hashed_password="-",
                    is_active=True, is_superuser=False, is_verified=True)
        )  # fmt: skip
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--case", action="append", help="run only these case ids")
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--out", type=Path, default=Path("data/eval_agent_tools.json"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    # A key-log pipe set on this machine breaks TLS to the provider (CLAUDE.md, Gotchas).
    os.environ.pop("SSLKEYLOGFILE", None)
    cases = yaml.safe_load(args.cases.read_text(encoding="utf-8"))["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] in set(args.case)]

    with tempfile.TemporaryDirectory() as folder:
        _fresh_database(Path(folder))
        from app.agent.agent import agent_model
        from app.settings_store import ModelRole, settings_for

        role = settings_for(ModelRole.AGENT)
        model = agent_model()
        print(
            f"agent model: {role.llm_model} at {role.llm_base_url}  ({len(cases)} cases)",
            flush=True,
        )
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(lambda case: _report(run_case(case, model)), cases))
        finally:
            from app.persistence import database

            database.reset_engine_for_testing()  # releases the file so the folder can go

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"model": role.llm_model, "results": results}, indent=2),
                        encoding="utf-8")  # fmt: skip
    width = max(len(r["id"]) for r in results)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        trace = " > ".join(
            c["name"] + ("*" if c["pending"] else "") for t in r["turns"] for c in t["calls"]
        )
        print(f"{mark}  {r['id']:<{width}}  {r['seconds']:>5}s  {trace}")
        for problem in r["problems"]:
            print(f"        - {problem}")
    passed = sum(r["passed"] for r in results)
    by_category: dict[str, list[bool]] = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r["passed"])
    print(f"\n{passed}/{len(results)} cases passed  (* = waited for approval)")
    for category, marks in sorted(by_category.items()):
        print(f"  {category:<22} {sum(marks)}/{len(marks)}")
    print(f"details: {args.out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
