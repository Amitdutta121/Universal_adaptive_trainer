#!/usr/bin/env python3
"""Deterministic student-workflow test harness for AdaptiveTrainer.

The only non-deterministic inputs are the CLI flags. Given the same flags this
does the same thing every time: enrol a student, run N adaptive questions under
a fixed answer policy, end the session, then assert that every instructor-
dashboard number reconciles (the dashboard is a pure client render of
/api/students, /api/students/{id}/progress, /api/counts and
/api/training-sessions/{id}, so hitting those IS the consistency check).

Usage:
  python .claude/scripts/student_run.py --policy expert  --n 20
  python .claude/scripts/student_run.py --policy beginner --n 10 --seed 7
  python .claude/scripts/student_run.py --policy mixed    --n 15 --seed 1 --name "Mixed Sim 1"
  python .claude/scripts/student_run.py --policy inconsistent --n 20 --seed 2
  python .claude/scripts/student_run.py --policy random   --n 20 --seed 3
  python .claude/scripts/student_run.py --verify-only --student 16

Policies (deterministic given the same --seed):
  expert       - always answer correctly
  beginner     - correct with flat p=0.35
  mixed        - correct with flat p=0.65
  inconsistent - streaky: alternates between a "hot" run (p=0.85) and a "cold"
                 run (p=0.15), flipping state with p=0.25 per question, so the
                 mastery curve visibly rises and falls instead of trending
                 toward one flat average -- an erratic learner, not a
                 different fixed skill level.
  random       - blind guessing: the *answer itself* is drawn uniformly at
                 random (a random option index, a coin-flip True/False, a
                 random garbage string for output_prediction) with no
                 reference to the correct answer at all, unlike the other
                 policies which decide correct/incorrect first and then look
                 up or perturb the real answer.
"""
import argparse, json, random, subprocess, sys, time

BASE = "http://127.0.0.1:8099/api"
CJ = "/tmp/atrainer_cj"

# Correct answers are derived live from GET /api/questions/{id} (professor
# view, content included) rather than a hardcoded per-set key, so this script
# works against any frozen set (Sample, or a fresh taxonomy's set) unchanged.


def curl(args, method="GET", body=None):
    cmd = ["curl", "-s", "-b", CJ, "-c", CJ, "-X", method]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
    cmd.append(args if args.startswith("http") else BASE + args)
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    try:
        return json.loads(out) if out.strip() else {}
    except json.JSONDecodeError:
        return {"_raw": out}


def login():
    subprocess.run(["curl", "-s", "-c", CJ, "-X", "POST", f"{BASE}/auth/login",
                    "-d", "username=dev@local.test&password=devpassword123"],
                   capture_output=True)
    me = curl("/auth/me")
    if "email" not in me:
        sys.exit(f"login failed: {me}")


_qcache = {}
def full_question(qid):
    if qid not in _qcache:
        _qcache[qid] = curl(f"/questions/{qid}")
    return _qcache[qid]


def parsons_answer(qid):
    c = full_question(qid)["content"]
    indent = {b["id"]: b.get("indent", 0) for b in c["blocks"]}
    return "\n".join(("    " * indent.get(bid, 0)) + str(bid) for bid in c["correct_order"])


def random_answer(nx, content, rng):
    """A blind guess: drawn uniformly at random, independent of what's correct."""
    qt = nx["question_type"]
    if qt == "multiple_choice":
        n = len(nx.get("options") or content.get("options") or [1, 2, 3, 4])
        return str(rng.randrange(n))
    if qt == "true_false":
        return rng.choice(["True", "False"])
    if qt == "output_prediction":
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789 "
        return "".join(rng.choice(alphabet) for _ in range(12))
    if qt == "parsons":
        ids = [b["id"] for b in content["blocks"]]
        rng.shuffle(ids)
        return "\n".join(str(i) for i in ids)
    return ""


def answer_for(nx, policy, want_correct, rng):
    qid, qt = nx["question_id"], nx["question_type"]
    content = full_question(qid)["content"]

    if policy == "random":
        return random_answer(nx, content, rng)

    if qt == "multiple_choice":
        n = len(nx.get("options") or content.get("options") or [1, 2, 3, 4])
        correct = content["correct_option_index"]
        return str(correct) if want_correct else str((correct + 1) % n)

    if qt == "true_false":
        correct = content["correct_answer"]  # bool
        value = correct if want_correct else not correct
        return "True" if value else "False"

    if qt == "output_prediction":
        expected = content["expected_output"]
        return expected if want_correct else "WRONG_OUTPUT_SIMULATED"

    if qt == "parsons":
        if want_correct:
            return parsons_answer(qid)
        blocks = content["blocks"]
        ids = [b["id"] for b in blocks]
        rng.shuffle(ids)
        return "\n".join(str(i) for i in ids)

    return ""


FLAT_P_CORRECT = {"expert": 1.0, "beginner": 0.35, "mixed": 0.65}
STREAK_P_CORRECT = {"hot": 0.85, "cold": 0.15}
STREAK_SWITCH_PROB = 0.25


def want_correct(policy, streak_state, rng):
    """Decide whether this question should be answered correctly.

    Returns ``None`` for ``random``, which does not look at correctness at all
    -- ``answer_for`` handles that policy by drawing a blind guess instead.
    """
    if policy == "random":
        return None
    if policy == "inconsistent":
        if rng.random() < STREAK_SWITCH_PROB:
            streak_state["mode"] = "cold" if streak_state["mode"] == "hot" else "hot"
        return rng.random() < STREAK_P_CORRECT[streak_state["mode"]]
    return rng.random() < FLAT_P_CORRECT[policy]


def run(policy, n, seed, name, set_id):
    rng = random.Random(seed)
    streak_state = {"mode": rng.choice(["hot", "cold"])}

    # CreateStudentRequest now requires email (ADR-041 identity work landed
    # since this script was first written); slugify the display name into one.
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    email = f"sim-{slug}-{int(time.time())}@example.com"
    sid = curl("/students", "POST", {"display_name": name, "email": email})["id"]
    ts = curl("/training-sessions", "POST",
              {"student_id": sid, "set_version_id": set_id})["id"]
    print(f"student_id={sid}  training_session_id={ts}  policy={policy} n={n} seed={seed}\n")

    for i in range(n):
        nx = curl(f"/training-sessions/{ts}/next")
        if "attempt_id" not in nx:
            # NoQuestionAvailableError / CurriculumCompletedError (both 409,
            # codes "no_question_available" / "curriculum_completed"): the
            # taxonomy/coverage ran out for this student, not a real failure.
            code = nx.get("error", {}).get("code", "")
            if code in ("no_question_available", "curriculum_completed"):
                print(f"(no more servable questions after {i} -- {code})")
                break
            sys.exit(f"next failed at i={i}: {nx}")
        want = want_correct(policy, streak_state, rng)
        res = curl(f"/attempts/{nx['attempt_id']}/answer", "POST",
                   {"answer": answer_for(nx, policy, want, rng)})
        tag = f"({streak_state['mode']})" if policy == "inconsistent" else ""
        want_label = "rand" if want is None else ("ok  " if want else "X   ")
        print(f"#{nx['ordinal']:>2} q{nx['question_id']:<3} {nx['question_type']:<15} "
              f"req={str(nx.get('requested_difficulty')):<6} served={str(nx.get('served_difficulty')):<6} "
              f"fb={str(nx.get('fallback_used')):<5} want={want_label}{tag:<6} "
              f"score={str(res.get('score')):<6} mastery->{round(res.get('mastery_after', 0), 3)}")

    curl(f"/training-sessions/{ts}/end", "POST")
    print(f"\nsession {ts} ended")
    return sid


def verify(student_id):
    """Assert every dashboard-visible number reconciles across the 4 endpoints."""
    counts = curl("/counts")
    # Roster is server-paginated (default page_size=20, max 100); page through
    # it so this check still sees every learner once the DB holds more than 20.
    roster, page = [], 1
    while True:
        batch = curl(f"/students?page={page}&page_size=100")
        roster += batch["students"]
        if len(roster) >= batch["total"] or not batch["students"]:
            break
        page += 1
    prog = curl(f"/students/{student_id}/progress")
    row = next((s for s in roster if s["id"] == student_id), None)

    checks = []
    def chk(name, ok, detail=""):
        checks.append((ok, name, detail))

    chk("counts.students == roster length",
        counts["students"] == len(roster),
        f'{counts["students"]} vs {len(roster)}')

    chk("roster row exists for student", row is not None)
    if row:
        chk("roster.answered_count == progress.answered",
            row["answered_count"] == prog["answered"],
            f'{row["answered_count"]} vs {prog["answered"]}')

    scored = [a for a in prog["recent_attempts"] if a["score"] is not None]
    chk("progress.answered == #scored recent_attempts",
        prog["answered"] == len(scored),
        f'{prog["answered"]} vs {len(scored)}')

    if scored:
        avg = sum(a["score"] for a in scored) / len(scored)
        chk("progress.average_score == mean(scored)",
            abs(avg - prog["average_score"]) < 0.01,
            f'{round(avg, 2)} vs {round(prog["average_score"], 2)}')

    for s in prog["sessions"]:
        live = curl(f"/training-sessions/{s['id']}")
        chk(f"session #{s['id']} answered_count matches",
            live["answered_count"] == s["answered_count"],
            f'{live["answered_count"]} vs {s["answered_count"]}')
        chk(f"session #{s['id']} served >= answered",
            live["served_count"] >= live["answered_count"],
            f'{live["served_count"]} >= {live["answered_count"]}')

    obs_total = sum(t["observations"] for t in prog["topics"])
    chk("sum(topic observations) == answered",
        obs_total == prog["answered"],
        f'{obs_total} vs {prog["answered"]}')

    measured = sum(1 for s in roster if s["answered_count"] > 0)
    unstarted = len(roster) - measured
    chk("class-insights measured + unstarted == learners",
        measured + unstarted == counts["students"],
        f'{measured} + {unstarted} == {counts["students"]}')

    print("\n=== dashboard consistency ===")
    for ok, name, detail in checks:
        print(f'  [{"PASS" if ok else "FAIL"}] {name}' + (f'   ({detail})' if detail else ""))
    failed = [c for c in checks if not c[0]]
    print(f'\n{len(checks) - len(failed)}/{len(checks)} passed')
    return not failed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--policy",
        choices=["expert", "beginner", "mixed", "inconsistent", "random"],
        default="expert",
    )
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--set", type=int, default=1, dest="set_id")
    ap.add_argument("--name", default=None)
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--student", type=int, default=None, help="student id for --verify-only")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()

    login()
    if a.verify_only:
        if a.student is None:
            sys.exit("--verify-only needs --student <id>")
        sys.exit(0 if verify(a.student) else 1)

    name = a.name or f"{a.policy.title()} Sim s{a.seed} {int(time.time())}"
    sid = run(a.policy, a.n, a.seed, name, a.set_id)
    if not a.no_verify:
        sys.exit(0 if verify(sid) else 1)
