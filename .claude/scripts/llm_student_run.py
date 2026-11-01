#!/usr/bin/env python3
"""LLM-persona student simulator for AdaptiveTrainer.

Unlike ``.claude/scripts/student_run.py`` (a canned answer-key replay against
the fixed "Sample" set), this drives a *real* LLM through each question: it
reads the actual prompt/code/options the student would see and answers
in-character as one of three skill personas (novice / average / expert), so
right and wrong answers come from genuine (simulated) understanding rather
than a scripted correctness rate.

Every HTTP call below is the exact one the frontend makes for the same step
(see ``frontend/src/lib/api/queries.ts``) -- same method, same path, same body
shape:

  POST /api/auth/login                          form-encoded, professor cookie
                                                 (only needed to freeze a set;
                                                 the student flow itself is
                                                 unauthenticated, same as a
                                                 learner's browser)
  POST /api/question-sets                       {label, notes}
       -> freezes every currently-*approved* question of the currently
          *approved* curriculum version into an immutable QuestionSetOut.
          Frontend: TopicGenerateButton's sibling "Freeze set" action.
  POST /api/students                            {display_name, email}
       -> StudentIdentityOut. Frontend: join-classroom-screen.tsx's enrol call.
  POST /api/training-sessions                   {student_id, set_version_id}
       -> TrainingSessionOut. Frontend: useStartTrainingSession().
  GET  /api/training-sessions/{id}/next
       -> ServedQuestionOut {attempt_id, question_id, question_type, prompt,
          code, options, requested_difficulty, served_difficulty,
          fallback_used, ordinal}. Frontend: useNextQuestion(). 409
          (NoQuestionAvailableError / CurriculumCompletedError) means the run
          is naturally over -- the server has already ended the session in the
          CurriculumCompletedError case.
  POST /api/attempts/{attempt_id}/answer        {answer}
       -> AnsweredOut {score, mastery_before, mastery_after, detail}.
          Frontend: useAnswerAttempt(). ``answer`` is a bare string whose
          shape depends on question_type (app/adaptive/scoring.py):
            multiple_choice   -> the chosen option's index, as a string ("0")
            true_false        -> "True" or "False" (case-insensitive)
            output_prediction -> the predicted stdout, compared to
                                  content.expected_output after the same
                                  whitespace/CRLF normalization the code
                                  runner uses
  POST /api/training-sessions/{id}/end          Frontend: useEndTrainingSession().

The persona "brain" reuses the app's own structured-LLM client
(``app.llm.client.get_structured_client``), so it authenticates against
OpenRouter exactly the way question generation does -- same ``.env``
(``LLM_API_KEY`` / ``LLM_MODEL`` / ``LLM_PROVIDER``), same client. This is a
second, independent caller of that client, not a mock.

Usage (run from the repo root, backend already up on :8099):
  .venv\\Scripts\\python.exe .claude\\scripts\\llm_student_run.py
  .venv\\Scripts\\python.exe .claude\\scripts\\llm_student_run.py --n 12 --personas novice,expert
  .venv\\Scripts\\python.exe .claude\\scripts\\llm_student_run.py --set-id 3   # reuse an already-frozen set
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.errors import AdaptiveTrainerError  # noqa: E402
from app.llm.client import get_structured_client  # noqa: E402

BASE = "http://127.0.0.1:8099/api"
CURRICULUM_LABEL = "Python for Data Science - Intro Programming Module"
DEV_EMAIL = "dev@local.test"
DEV_PASSWORD = "devpassword123"

# ---------------------------------------------------------------- personas

PERSONAS: dict[str, str] = {
    "novice": (
        "You are role-playing as a real first-time programming student about three "
        "weeks into an intro Python-for-data-science course. Your understanding is "
        "shaky and still forming: you often misjudge operator precedence, make "
        "off-by-one mistakes with loops and slicing, mix up mutable vs immutable "
        "types, get confused about what a function returns vs. prints, and lose "
        "track of state in recursive or nested calls. Actually reason at this "
        "level -- do not silently solve it correctly and then fake a wrong answer. "
        "Think it through the way this student genuinely would, in a few short "
        "sentences, then give the answer that thinking honestly leads to, right or "
        "wrong."
    ),
    "average": (
        "You are role-playing as a solid student about halfway through an intro "
        "Python-for-data-science course. You reliably get variables, control flow, "
        "basic functions, strings and lists right. You still sometimes stumble on "
        "recursion, closures/scope, file I/O, and multi-step nested logic. Reason "
        "briefly and honestly at this level, then answer the way this student "
        "really would."
    ),
    "expert": (
        "You are role-playing as a strong student who already knew how to program "
        "before this course. You reason carefully and correctly and should get "
        "almost every question right; only a genuinely obscure or ambiguous edge "
        "case should trip you up. Show brief reasoning, then answer."
    ),
}

# --------------------------------------------------------- answer schemas


class McqAnswer(BaseModel):
    reasoning: str = Field(description="One or two sentences of in-character reasoning.")
    option_index: int = Field(description="Index (0-based) of the chosen option.")


class TrueFalseAnswer(BaseModel):
    reasoning: str = Field(description="One or two sentences of in-character reasoning.")
    is_true: bool = Field(description="True if the statement/code claim is correct.")


class OutputPredictionAnswer(BaseModel):
    reasoning: str = Field(description="One or two sentences of in-character reasoning.")
    predicted_stdout: str = Field(
        description="Exactly what the program prints to stdout, verbatim (no extra commentary)."
    )


# ------------------------------------------------------------- HTTP helpers


def _raise_for_status(resp: requests.Response) -> dict[str, Any]:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not resp.ok:
        raise RuntimeError(f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {body}")
    return body


def login(session: requests.Session) -> None:
    resp = session.post(f"{BASE}/auth/login", data={"username": DEV_EMAIL, "password": DEV_PASSWORD})
    if resp.status_code != 204:
        sys.exit(f"professor login failed ({resp.status_code}): {resp.text}")
    me = _raise_for_status(session.get(f"{BASE}/auth/me"))
    if "email" not in me:
        sys.exit(f"login did not stick: {me}")


def resolve_approved_curriculum(session: requests.Session) -> dict[str, Any]:
    versions = _raise_for_status(session.get(f"{BASE}/curriculum/versions"))
    approved_id = versions.get("approved_version_id")
    row = next((v for v in versions["versions"] if v["id"] == approved_id), None)
    if row is None:
        sys.exit("No approved curriculum version -- upload/approve one first.")
    if row["label"] != CURRICULUM_LABEL:
        sys.exit(
            f"The approved curriculum is {row['label']!r}, not {CURRICULUM_LABEL!r}. "
            f"POST /api/curriculum/versions/{{id}}/activate the right version first."
        )
    return row


def freeze_set(session: requests.Session, label: str) -> dict[str, Any]:
    return _raise_for_status(
        session.post(
            f"{BASE}/question-sets",
            json={"label": label, "notes": "LLM persona simulation run"},
        )
    )


def create_student(session: requests.Session, display_name: str, email: str) -> dict[str, Any]:
    return _raise_for_status(session.post(f"{BASE}/students", json={"display_name": display_name, "email": email}))


def start_session(session: requests.Session, student_id: int, set_version_id: int) -> dict[str, Any]:
    return _raise_for_status(
        session.post(
            f"{BASE}/training-sessions",
            json={"student_id": student_id, "set_version_id": set_version_id},
        )
    )


def next_question(session: requests.Session, training_session_id: int) -> dict[str, Any] | None:
    resp = session.get(f"{BASE}/training-sessions/{training_session_id}/next")
    if resp.status_code == 409:
        return None  # NoQuestionAvailableError / CurriculumCompletedError: run is over
    return _raise_for_status(resp)


def submit_answer(session: requests.Session, attempt_id: int, answer: str) -> dict[str, Any]:
    return _raise_for_status(session.post(f"{BASE}/attempts/{attempt_id}/answer", json={"answer": answer}))


def end_session(session: requests.Session, training_session_id: int) -> None:
    with contextlib.suppress(Exception):
        session.post(f"{BASE}/training-sessions/{training_session_id}/end")


# ---------------------------------------------------------------- the brain


def _question_context(nx: dict[str, Any]) -> str:
    lines = [
        f"Topic/subtopic: {nx.get('subtopic_name') or 'unlabeled'}",
        f"Difficulty served: {nx['served_difficulty']}",
        "",
        nx["prompt"],
    ]
    if nx.get("code"):
        lines += ["", "```python", nx["code"], "```"]
    if nx.get("options"):
        lines += [""] + [f"  [{i}] {opt}" for i, opt in enumerate(nx["options"])]
    return "\n".join(lines)


def answer_question(client, persona_key: str, nx: dict[str, Any]) -> tuple[str, str]:
    """Return (wire_answer, reasoning) for one served question."""
    system = PERSONAS[persona_key]
    context = _question_context(nx)
    qtype = nx["question_type"]

    if qtype == "multiple_choice":
        n_opts = len(nx.get("options") or [])
        result = client.complete_structured(
            system=system,
            prompt=f"{context}\n\nWhich option is correct? Give its index.",
            response_model=McqAnswer,
        )
        idx = max(0, min(result.option_index, max(n_opts - 1, 0)))
        return str(idx), result.reasoning

    if qtype == "true_false":
        result = client.complete_structured(
            system=system,
            prompt=f"{context}\n\nIs this true or false?",
            response_model=TrueFalseAnswer,
        )
        return ("True" if result.is_true else "False"), result.reasoning

    if qtype == "output_prediction":
        result = client.complete_structured(
            system=system,
            prompt=f"{context}\n\nWhat does this program print to stdout? "
            "Give exactly what would be printed, nothing else.",
            response_model=OutputPredictionAnswer,
        )
        return result.predicted_stdout, result.reasoning

    # Not present in this taxonomy today (parsons/code_completion/debugging/
    # coding); fall through to an honest skip rather than guessing at a shape.
    return "", f"(persona simulator has no handler for question_type={qtype!r}; skipped)"


# ------------------------------------------------------------------- runner


def run_persona(
    session: requests.Session, client, persona_key: str, n: int, set_version_id: int, run_tag: str
) -> dict[str, Any]:
    display_name = f"LLM {persona_key.title()} Persona {run_tag}"
    email = f"llm-{persona_key}-{run_tag}@example.com"
    student = create_student(session, display_name, email)
    ts = start_session(session, student["id"], set_version_id)
    print(f"\n=== {persona_key} === student_id={student['id']}  session_id={ts['id']}  name={display_name!r}")

    answered = 0
    for _ in range(n):
        nx = next_question(session, ts["id"])
        if nx is None:
            print("  (no more servable questions -- run ended by the server)")
            break
        wire_answer, reasoning = answer_question(client, persona_key, nx)
        res = submit_answer(session, nx["attempt_id"], wire_answer)
        answered += 1
        mb = res.get("mastery_before")
        ma = res.get("mastery_after")
        mastery = f"{mb:.2f}->{ma:.2f}" if mb is not None and ma is not None else "n/a"
        fb = "FALLBACK" if nx["fallback_used"] else ""
        print(
            f"  #{nx['ordinal']:>2} q{nx['question_id']:<4} {nx['question_type']:<17} "
            f"diff={nx['served_difficulty']:<6} {fb:<8} score={res['score']:>5.1f}  mastery {mastery}"
        )
        print(f"       -> {reasoning[:160]}")

    end_session(session, ts["id"])
    return {"persona": persona_key, "student_id": student["id"], "session_id": ts["id"], "answered": answered}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=12, help="questions per persona (default 12)")
    ap.add_argument(
        "--personas",
        default="novice,average,expert",
        help="comma-separated subset of: novice,average,expert",
    )
    ap.add_argument("--set-id", type=int, default=None, help="reuse an already-frozen set instead of freezing one")
    args = ap.parse_args()

    persona_keys = [p.strip() for p in args.personas.split(",") if p.strip()]
    for p in persona_keys:
        if p not in PERSONAS:
            sys.exit(f"unknown persona {p!r}; choose from {list(PERSONAS)}")

    session = requests.Session()
    login(session)

    if args.set_id is not None:
        set_row = _raise_for_status(session.get(f"{BASE}/question-sets/{args.set_id}"))
        print(f"Reusing set #{set_row['id']} {set_row['label']!r} ({set_row['question_count']} questions)")
    else:
        curriculum = resolve_approved_curriculum(session)
        run_tag = time.strftime("%Y%m%d-%H%M%S")
        set_row = freeze_set(session, label=f"LLM sim {run_tag}")
        print(
            f"Froze set #{set_row['id']} {set_row['label']!r}: {set_row['question_count']} questions "
            f"from curriculum {curriculum['label']!r} (v{curriculum['id']})"
        )

    client = get_structured_client()
    print(f"Persona brain: {client.description}")

    run_tag = time.strftime("%Y%m%d-%H%M%S")
    results = []
    for persona_key in persona_keys:
        try:
            results.append(run_persona(session, client, persona_key, args.n, set_row["id"], run_tag))
        except AdaptiveTrainerError as exc:
            print(f"  !! {persona_key} run failed: {exc}")

    print("\n=== summary ===")
    for r in results:
        print(f"  {r['persona']:8s} student_id={r['student_id']:<5} session_id={r['session_id']:<5} answered={r['answered']}")
    print(f"\nCheck it visually at http://localhost:3000/students/roster")
    print(f"Join link for this set: http://localhost:3000/students/join?set={set_row['id']}")


if __name__ == "__main__":
    main()
