"""Records the traces, example outputs and check answers the /experiments/tutorials-deck prototype uses.

Run:  D:/FInalAdaptiveTrainer/.venv/Scripts/python.exe record_traces.py
Every snippet is executed for real: the stepped ones under `sys.settrace` (call / line / return
events, with the call stack, the watched variables and `id()`s of lists), the static ones plainly.
The script writes `traces.generated.ts` next to itself. What is hand-written here is prose only
(captions' wording, questions, "why" lines); every value, output line, branch state, frame and
list-sharing fact is recorded, and every prediction's right answer is derived from the recording
and asserted to be one of the offered choices.

A step describes the state AFTER its `line` ran (line is null at the start): the code highlights
`line`, the panels show `frames` / `heap` / `output`. A call is its own step and jumps to the `def`
line; a return is its own step with the frame still on the stack and the value it gives back.

TODO(real): this is the shape of the recorder a tutorial generator would run at build time, from
the book section's snippet, then have validated with the professor's approval, instead of a
hand-run script.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import sys
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).parent
OUT = HERE / "traces.generated.ts"

#: "line" events a snippet may run before we call it endless.
CAP = 9
#: Line events allowed when checking that a snippet finishes at all.
PLAIN_CAP = 400
MAX_CAPTION_WORDS = 16


class StepCap(Exception):
    pass


# ---------------------------------------------------------------------------------------------
# Snippets. Code is exactly what the student sees.
# ---------------------------------------------------------------------------------------------

COND_SHADOW = (
    'mark = 95\nif mark >= 60:\n    grade = "pass"\nelif mark >= 90:\n    grade = "distinction"\n'
    'else:\n    grade = "fail"\nprint(grade)'
)
WHILE_ENDS = "n = 3\nwhile n > 0:\n    print(n)\n    n = n - 1"
WHILE_STUCK = 'count = 0\nwhile count < 3:\n    print("tick")'
FN_RETURN = "def add(a, b):\n    total = a + b\n    return total\nresult = add(2, 3)\nprint(result)"
FN_PRINT = "def add(a, b):\n    print(a + b)\nresult = add(2, 3)\nprint(result)"
LIST_ALIAS = (
    "a = [10, 20, 30]\nprint(a[0])\nprint(a[-1])\nb = a\nb.append(40)\nprint(a)"
)
REC_FACT = (
    "def factorial(n):\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\n"
    "print(factorial(3))"
)

FACTORIAL = "def factorial(n):\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\n"

# Static examples shown on the idea and worked-example cards. Output is recorded, never typed.
EXAMPLES = {
    "if-basic": 'mark = 72\nif mark >= 60:\n    print("pass")\nelse:\n    print("fail")',
    "elif-chain": (
        'mark = 72\nif mark >= 90:\n    grade = "A"\nelif mark >= 60:\n    grade = "B"\n'
        'else:\n    grade = "C"\nprint(grade)'
    ),
    "elif-fixed": (
        'mark = 95\nif mark >= 90:\n    grade = "distinction"\nelif mark >= 60:\n    grade = "pass"\n'
        'else:\n    grade = "fail"\nprint(grade)'
    ),
    "while-countdown": WHILE_ENDS,
    "while-stuck": WHILE_STUCK,
    "while-fixed": 'count = 0\nwhile count < 3:\n    print("tick")\n    count = count + 1',
    "fn-greet": 'def greet(name):\n    return "Hi " + name\nprint(greet("Ada"))',
    "fn-square": "def square(x):\n    return x * x\ny = square(4)\nprint(y)",
    "fn-worked": (
        "def total_price(price, qty):\n    return price * qty\ncost = total_price(4, 3)\nprint(cost)"
    ),
    "list-index": "a = [10, 20, 30]\nprint(a[0])\nprint(a[-1])",
    "list-append": "a = [10, 20, 30]\na.append(40)\nprint(a)\nprint(len(a))",
    "list-copy": "a = [10, 20, 30]\nb = a.copy()\nb.append(40)\nprint(a)",
    "rec-countdown": (
        "def countdown(n):\n    if n == 0:\n        return\n    print(n)\n    countdown(n - 1)\n"
        "countdown(2)"
    ),
    "rec-unwind": FACTORIAL + "print(factorial(1))\nprint(factorial(2))\nprint(factorial(3))",
}
#: Examples that never finish: recorded up to the cap, and shown with "and on, forever".
ENDLESS_EXAMPLES = {"while-stuck"}
ENDLESS_SHOWN_LINES = 3

FADED_COND = (
    'mark = 65\nif mark >= 90:\n    grade = "distinction"\nelif mark >= 60:\n    grade = "pass"\n'
    'else:\n    grade = "fail"\nprint(grade)'
)
FADED_WHILE_TEMPLATE = "total = 0\ni = 1\nwhile i <= 3:\n    total = total + i\n    ____\nprint(total)"
FADED_WHILE_CHOICES = ["i = i + 1", "i = 1", "total = 0"]
FADED_WHILE_RIGHT = "i = i + 1"
FADED_FN_LINES = ["def area(w, h):", "    return w * h", "a = area(3, 5)", "print(a)"]
FADED_FN_SHUFFLED = [2, 3, 1, 0]
FADED_LIST = "a = [1, 2]\nb = a\nb.append(3)\nprint(a)"
FADED_REC = FACTORIAL + "print(factorial(4))"


# ---------------------------------------------------------------------------------------------
# Running code for real
# ---------------------------------------------------------------------------------------------


def run_plain(code: str, cap: int | None = None):
    """Runs `code` untraced. Returns (output lines, finished, error text or None)."""
    out = io.StringIO()
    count = 0

    def tracer(frame, event, _arg):
        nonlocal count
        if frame.f_code.co_filename != "<plain>":
            return None
        if event == "line":
            count += 1
            if cap is not None and count > cap:
                raise StepCap
        return tracer

    error = None
    finished = True
    try:
        compiled = compile(code, "<plain>", "exec")
        if cap is not None:
            sys.settrace(tracer)
        with contextlib.redirect_stdout(out):
            exec(compiled, {"__name__": "__snippet__"})
    except StepCap:
        finished = False
    except Exception as exc:  # noqa: BLE001 - we want the real message for the student
        error = f"{type(exc).__name__}: {getattr(exc, 'msg', None) or exc}"
    finally:
        sys.settrace(None)
    return out.getvalue().splitlines(), finished, error


def clean_vars(env):
    return {
        key: value
        for key, value in env.items()
        if not key.startswith("__") and not callable(value) and not isinstance(value, type(sys))
    }


class Recorder:
    def __init__(self, code: str, cap: int | None) -> None:
        self.code = compile(code, "<snippet>", "exec")
        self.cap = cap
        self.out = io.StringIO()
        self.events: list[dict] = []
        self.labels: dict = {}
        self.line_events = 0
        self.capped = False

    def stack(self, frame):
        frames = []
        current = frame
        while current is not None:
            if current.f_code.co_filename == "<snippet>":
                frames.append(current)
            current = current.f_back
        return list(reversed(frames))

    def snapshot(self, frame, kind, retval=None):
        frames = []
        for f in self.stack(frame):
            env = clean_vars(f.f_locals)
            frames.append(
                {
                    "label": self.labels.get(f, "global"),
                    "line": f.f_lineno,
                    "vars": {key: repr(value) for key, value in env.items()},
                    "raw": {key: copy.copy(value) for key, value in env.items()},
                    "ids": {key: id(value) for key, value in env.items() if isinstance(value, list)},
                }
            )
        return {
            "kind": kind,
            "line": frame.f_lineno,
            "frames": frames,
            "output": self.out.getvalue().splitlines(),
            "retval": retval,
            "repr_retval": repr(retval),
        }

    def tracer(self, frame, event, arg):
        if frame.f_code.co_filename != "<snippet>":
            return None
        is_module = frame.f_code is self.code
        if event == "call":
            if not is_module:
                args = [repr(frame.f_locals[n]) for n in frame.f_code.co_varnames[: frame.f_code.co_argcount]]
                self.labels[frame] = f"{frame.f_code.co_name}({', '.join(args)})"
                self.events.append(self.snapshot(frame, "call"))
            return self.tracer
        if event == "line":
            if self.cap is not None and self.line_events >= self.cap:
                self.events.append(self.snapshot(frame, "cap"))
                self.capped = True
                raise StepCap
            self.line_events += 1
            self.events.append(self.snapshot(frame, "line"))
        elif event == "return":
            self.events.append(self.snapshot(frame, "end" if is_module else "return", arg))
        return self.tracer

    def run(self):
        sys.settrace(self.tracer)
        try:
            with contextlib.redirect_stdout(self.out):
                exec(self.code, {"__name__": "__snippet__"})
        except StepCap:
            pass
        finally:
            sys.settrace(None)


# ---------------------------------------------------------------------------------------------
# Events -> steps
# ---------------------------------------------------------------------------------------------


def plan_steps(events):
    """(event index, highlighted line, kind). See the module docstring for the rules."""
    plan = [(0, None, "start")]
    for k in range(1, len(events)):
        e, p = events[k], events[k - 1]
        if e["kind"] == "call":
            plan.append((k, e["line"], "call"))
        elif p["kind"] == "call":
            continue  # the first line of a function is the same state as its call step
        elif p["kind"] == "return":
            kind = "back" if e["kind"] == "line" else e["kind"]
            plan.append((k, p["frames"][-2]["line"], kind))
        else:
            kind = e["kind"] if e["kind"] in ("return", "end", "cap") else "line"
            plan.append((k, p["line"], kind))
    return plan


def parse_chain(code):
    """The top-level if/elif/else chain: label, test expression, and the lines it owns."""
    lines = code.splitlines()
    heads = []
    for number, text in enumerate(lines, 1):
        m = re.match(r"(if|elif|else)\b\s*(.*?):\s*$", text)
        if m:
            heads.append((number, m.group(1), m.group(2), text.rstrip(":")))
    chain = []
    for i, (number, kind, expr, label) in enumerate(heads):
        end = len(lines) + 1
        for later in range(number + 1, len(lines) + 1):
            if not lines[later - 1].startswith((" ", "\t")):
                end = later
                break
        chain.append({"kind": kind, "expr": expr, "label": label, "test": number, "lines": list(range(number, end))})
    return chain


def branch_states(chain, ran_at, raws):
    """State of each branch given which steps have run: taken / false / skipped / pending."""
    states, taken, clear = [], False, True  # clear: every earlier test has run and was False
    for b in chain:
        if taken:
            state = "skipped"
        elif b["kind"] == "else":
            state = "taken" if clear else "pending"
        elif b["test"] in ran_at:
            state = "taken" if eval(b["expr"], {}, raws[ran_at[b["test"]]]) else "false"  # noqa: S307
        else:
            state = "pending"
        if state == "taken":
            taken = True
        if state != "false":
            clear = False
        states.append(state)
    return states


def heap_of(event, numbering):
    g = event["frames"][0]
    objs: dict[int, dict] = {}
    for name, raw in g["raw"].items():
        if isinstance(raw, list):
            number = numbering.setdefault(g["ids"][name], len(numbering) + 1)
            obj = objs.setdefault(number, {"id": number, "names": [], "items": [repr(x) for x in raw]})
            obj["names"].append(name)
    return list(objs.values())


def last_var(frame, name):
    return frame["vars"].get(name)


def caption(t, c):
    """Plain-words caption for one step. Wording is authored; every value in it is recorded."""
    kind, s, e, p = c.kind, c.src.strip(), c.e, c.p
    top = e["frames"][-1]
    if kind == "start":
        return "Nothing has run yet. Press Step."
    if kind == "cap":
        var = t["stuck"]
        return f"Stopped after {CAP} steps. {var} is still {top['vars'][var]}: this would go on forever."
    p_ret = p["repr_retval"] if p and p["kind"] == "return" else None
    printed = c.new_out[-1] if c.new_out else ""
    if kind == "call":
        params = ", ".join(f"{n} is {v}" for n, v in top["vars"].items())
        name = top["label"].split("(")[0]
        caller = e["frames"][-2]["label"]
        if caller != "global":
            return f"{caller} calls {top['label']}. New frame: {params}."
        return f"Call: Python jumps into {name}. {params}."
    if kind == "return":
        ret = e["repr_retval"]
        if t["id"].startswith("rec"):
            n = top["vars"]["n"]
            if p_ret is not None:
                return f"{p_ret} came back. {n} * {p_ret} = {ret}, so {top['label']} returns {ret}."
            return f"Base case: {top['label']} returns {ret}."
        if s.startswith("return"):
            return f"return sends {ret} back to the caller."
        return f"print shows {printed}. add has no return, so it gives back {ret}."
    if kind == "back":
        m = re.match(r"(\w+)\s*=", s)
        if m:
            return f"{p_ret} comes back: {m.group(1)} is {top['vars'][m.group(1)]}."
        return f"{p_ret} comes back to the caller."
    if s.startswith("print("):
        m = re.match(r"print\((\w+)\[(-?\d+)\]\)", s)
        if t["view"] == "memory" and m:
            idx = int(m.group(2))
            how = "counts from the end" if idx < 0 else "counts from 0"
            return f"{m.group(1)}[{idx}] {how}: print shows {printed}."
        lead = f"{p_ret} comes back, and " if p_ret is not None else ""
        return f"{lead}print shows {printed}."
    m = re.match(r"def (\w+)", s)
    if m:
        return f"Python stores {m.group(1)}. Nothing runs yet."
    m = re.match(r"(?:if|elif) (.*):$", s)
    if m:
        expr = m.group(1)
        res = bool(eval(expr, {}, top["raw"]))  # noqa: S307
        if t["view"] == "branches":
            return (
                f"{expr} is True: take this branch and skip the rest."
                if res
                else f"{expr} is False: try the next test."
            )
        return f"n is {top['vars']['n']}. {expr} is {res}. " + ("Base case." if res else "Keep going.")
    m = re.match(r"while (.*):$", s)
    if m:
        res = c.step_check_last
        return f"{m.group(1)} is True: run the body." if res else f"{m.group(1)} is False: the loop ends."
    m = re.match(r"(\w+)\.append\((.*)\)$", s)
    if m:
        names = next(o["names"] for o in c.heap if m.group(1) in o["names"])
        if len(names) > 1:
            return f"append adds {m.group(2)}. {' and '.join(names)} are one list: both grow."
        return f"append adds {m.group(2)} to the end of {m.group(1)}."
    m = re.match(r"(\w+)\s*=\s*(\w+)$", s)
    if m and t["view"] == "memory" and isinstance(top["raw"].get(m.group(1)), list):
        return f"{m.group(1)} = {m.group(2)} makes no copy. Two names, one list."
    m = re.match(r"(\w+)\s*=\s*\[", s)
    if m and t["view"] == "memory":
        return f"{m.group(1)} points at a new list of {len(top['raw'][m.group(1)])} items."
    m = re.match(r"(\w+)\s*=", s)
    if m:
        name = m.group(1)
        new = top["vars"][name]
        old_frame = p["frames"][len(e["frames"]) - 1] if p and len(p["frames"]) >= len(e["frames"]) else None
        old = old_frame["vars"].get(name) if old_frame else None
        text = f"{name} is {new}." if old is None else f"{name} was {old}, now {new}."
        if c.skipped:
            text += " Skipped branches never ran."
        return text
    raise ValueError(f"no caption rule for {s!r} ({kind})")


def build_trace(t):
    rec = Recorder(t["code"], t.get("cap"))
    rec.run()
    events = rec.events
    plan = plan_steps(events)
    numbering: dict[int, int] = {}
    chain = parse_chain(t["code"]) if t["view"] == "branches" else []
    while_expr = None
    if t["view"] == "while":
        while_expr = re.search(r"^while (.*):$", t["code"], re.M).group(1)
        while_line = next(i for i, l in enumerate(t["code"].splitlines(), 1) if l.startswith("while "))
    source = t["code"].splitlines()

    steps, ran_at, raws, check_results = [], {}, [], []
    prev_out: list[str] = []
    for index, (k, hl, kind) in enumerate(plan):
        e = events[k]
        p = events[k - 1] if k else None
        frames = [{"label": f["label"], "vars": f["vars"]} for f in e["frames"]]
        if kind == "return":
            frames[-1]["ret"] = e["repr_retval"]
        step = {
            "line": hl,
            "kind": kind,
            "frames": frames,
            "paused": [f["line"] for f in e["frames"][:-1]],
            "output": e["output"],
        }
        raws.append(e["frames"][0]["raw"] if len(e["frames"]) == 1 else e["frames"][-1]["raw"])
        if hl is not None:
            ran_at.setdefault(hl, index)
        heap = heap_of(e, numbering) if t["view"] == "memory" else []
        if t["view"] == "memory":
            step["heap"] = heap
            m = re.search(r"(\w+)\[(-?\d+)\]", source[hl - 1]) if hl else None
            if m:
                obj = next((o for o in heap if m.group(1) in o["names"]), None)
                if obj:
                    step["focus"] = {"obj": obj["id"], "index": int(m.group(2)) % len(obj["items"])}
            if steps:
                before = {o["id"]: len(o["items"]) for o in steps[-1]["heap"]}
                step["added"] = [
                    {"obj": o["id"], "index": i}
                    for o in heap
                    for i in range(before.get(o["id"], len(o["items"])), len(o["items"]))
                ]
            else:
                step["added"] = []
        if t["view"] == "while":
            if hl == while_line:
                check_results.append(bool(eval(while_expr, {}, e["frames"][0]["raw"])))  # noqa: S307
            step["check"] = {"expr": while_expr, "results": list(check_results)}
        if t["view"] == "branches":
            ran = {line: at for line, at in ran_at.items()}
            states = branch_states(chain, ran, raws)
            step["branches"] = [{"label": b["label"], "state": s} for b, s in zip(chain, states)]
            dim: list[int] = []
            for b, s in zip(chain, states):
                if s == "skipped":
                    dim += b["lines"]
                elif s == "false":
                    dim += b["lines"][1:]
            step["dim"] = sorted(dim)
        ctx = SimpleNamespace(
            kind=kind,
            src=source[hl - 1] if hl else "",
            e=e,
            p=p,
            new_out=e["output"][len(prev_out):],
            heap=heap,
            step_check_last=check_results[-1] if check_results else None,
            skipped=any(b["state"] == "skipped" for b in step.get("branches", [])),
        )
        step["caption"] = caption(t, ctx)
        words = len(step["caption"].split())
        assert words <= MAX_CAPTION_WORDS, (t["id"], words, step["caption"])
        prev_out = e["output"]
        steps.append(step)

    expected, finished, error = run_plain(t["code"], PLAIN_CAP)
    assert error is None, error
    if t.get("endless"):
        assert not finished and rec.capped, "snippet was meant to be endless"
        assert steps[-1]["kind"] == "cap"
    else:
        assert finished and not rec.capped
        assert steps[-1]["output"] == expected, (t["id"], steps[-1]["output"], expected)

    predictions = []
    for spec in t["predictions"]:
        at = spec["at"](steps)
        answer = spec["correct"](steps)
        assert answer in spec["choices"], (t["id"], spec["id"], answer, spec["choices"])
        predictions.append(
            {
                "id": spec["id"],
                "atStep": at,
                "question": spec["question"],
                "choices": spec["choices"],
                "answer": spec["choices"].index(answer),
                "why": spec["why"],
            }
        )
    return {
        "id": t["id"],
        "label": t["label"],
        "view": t["view"],
        "code": t["code"],
        "endless": bool(t.get("endless")),
        "takeaway": t["takeaway"],
        "expectedOutput": expected if not t.get("endless") else steps[-1]["output"],
        "predictions": predictions,
        "steps": steps,
    }


# ---------------------------------------------------------------------------------------------
# Trace specs (prose is authored here; values are derived from the recording)
# ---------------------------------------------------------------------------------------------


def first_step(steps, test):
    return next(i for i, s in enumerate(steps) if test(s))


TRACE_SPECS = [
    dict(
        id="cond", topic="conditionals", label="mark = 95", view="branches", code=COND_SHADOW,
        takeaway="The first true test wins. Put the strictest test first.",
        predictions=[
            dict(
                id="first", at=lambda st: 1, question="Which grade will print?",
                choices=["distinction", "pass", "fail"], correct=lambda st: st[-1]["output"][-1],
                why="The first true test wins: 95 >= 60 is True, so the elif is never tested.",
            ),
            dict(
                id="key", at=lambda st: first_step(st, lambda s: s["line"] == 2),
                question="The if test is True. Does Python test the elif next?",
                choices=["Yes, it tests every branch", "No, it skips it"],
                correct=lambda st: "No, it skips it"
                if st[first_step(st, lambda s: s["line"] == 2)]["branches"][1]["state"] == "skipped"
                else "Yes, it tests every branch",
                why="Once a branch is taken, the rest of the chain is skipped.",
            ),
        ],
    ),
    dict(
        id="while-ends", topic="while", label="Countdown", view="while", code=WHILE_ENDS,
        takeaway="The test runs before every pass. When it is False, the loop ends.",
        predictions=[
            dict(
                id="first", at=lambda st: 1, question="What will this print?",
                choices=["3 2 1", "3 2 1 0", "2 1 0"], correct=lambda st: " ".join(st[-1]["output"]),
                why="n stops the loop at 0, and 0 > 0 is False, so 0 is never printed.",
            ),
            dict(
                id="key", at=lambda st: first_step(st, lambda s: s["check"]["results"][-1:] == [False]),
                question="n is 0 now. What happens at the while line?",
                choices=["The body runs once more", "The loop ends"],
                correct=lambda st: "The loop ends"
                if st[first_step(st, lambda s: s["check"]["results"][-1:] == [False])]["check"]["results"][-1] is False
                else "The body runs once more",
                why="0 > 0 is False, so Python leaves the loop.",
            ),
        ],
    ),
    dict(
        id="while-stuck", topic="while", label="Stuck loop", view="while", code=WHILE_STUCK, cap=CAP,
        endless=True, stuck="count",
        takeaway="Nothing changes count, so the test never turns False.",
        predictions=[
            dict(
                id="first", at=lambda st: 1, question="How many times will tick print?",
                choices=["Three times", "Never", "Forever"],
                correct=lambda st: "Forever" if st[-1]["kind"] == "cap" else "Three times",
                why="count stays 0, so count < 3 is True every time.",
            ),
            dict(
                id="key", at=lambda st: first_step(st, lambda s: len(s["check"]["results"]) == 2),
                question="The body ran once. count is still 0. Is the test True again?",
                choices=["Yes, nothing changed count", "No, it already ran"],
                correct=lambda st: "Yes, nothing changed count"
                if st[first_step(st, lambda s: len(s["check"]["results"]) == 2)]["check"]["results"][1]
                else "No, it already ran",
                why="The test only looks at count, and nothing inside the loop changes it.",
            ),
        ],
    ),
    dict(
        id="fn-return", topic="functions", label="Returns a value", view="stack", code=FN_RETURN,
        takeaway="return hands the value back to the caller.",
        predictions=[
            dict(
                id="first", at=lambda st: 1, question="What will this print?",
                choices=["5", "None", "Nothing"], correct=lambda st: st[-1]["output"][-1],
                why="add returns total, and result keeps it.",
            ),
            dict(
                id="key", at=lambda st: first_step(st, lambda s: "ret" in s["frames"][-1]),
                question="What will add give back to its caller?", choices=["5", "None"],
                correct=lambda st: st[first_step(st, lambda s: "ret" in s["frames"][-1])]["frames"][-1]["ret"],
                why="return total sends total's value back.",
            ),
        ],
    ),
    dict(
        id="fn-print", topic="functions", label="Only prints", view="stack", code=FN_PRINT,
        takeaway="print shows a value. Without return, the call gives back None.",
        predictions=[
            dict(
                id="first", at=lambda st: 1, question="What will the two prints show?",
                choices=["5 then 5", "5 then None", "Only 5"], correct=lambda st: " then ".join(st[-1]["output"]),
                why="add prints 5 but returns nothing, so result is None.",
            ),
            dict(
                id="key", at=lambda st: first_step(st, lambda s: "ret" in s["frames"][-1]),
                question="What will add give back to its caller?", choices=["5", "None"],
                correct=lambda st: st[first_step(st, lambda s: "ret" in s["frames"][-1])]["frames"][-1]["ret"],
                why="No return line means the call gives back None.",
            ),
        ],
    ),
    dict(
        id="list-alias", topic="lists", label="Two names", view="memory", code=LIST_ALIAS,
        takeaway="b = a copies the name, not the list. Both names see every change.",
        predictions=[
            dict(
                id="first", at=lambda st: 1, question="What will print(a[-1]) show?",
                choices=["30", "10", "An error"], correct=lambda st: st[-1]["output"][1],
                why="Index -1 counts from the end: the last item.",
            ),
            dict(
                id="key", at=lambda st: len(st) - 1,
                question="b.append(40) has run. What will print(a) show?",
                choices=["[10, 20, 30]", "[10, 20, 30, 40]"], correct=lambda st: st[-1]["output"][-1],
                why="a and b are the same list, so a sees the 40 too.",
            ),
        ],
    ),
    dict(
        id="rec-fact", topic="recursion", label="factorial(3)", view="stack", code=REC_FACT,
        takeaway="Each call has its own n. Answers flow back as the stack unwinds.",
        predictions=[
            dict(
                id="first", at=lambda st: 1, question="What will this print?",
                choices=["3", "6", "9"], correct=lambda st: st[-1]["output"][-1],
                why="3 * 2 * 1 is 6.",
            ),
            dict(
                id="key",
                at=lambda st: first_step(st, lambda s: s["kind"] == "return" and s["frames"][-1]["label"] == "factorial(2)"),
                question="factorial(1) gave back 1. What does factorial(2) give back?",
                choices=["1", "2", "3"],
                correct=lambda st: st[
                    first_step(st, lambda s: s["kind"] == "return" and s["frames"][-1]["label"] == "factorial(2)")
                ]["frames"][-1]["ret"],
                why="factorial(2) is 2 * factorial(1), which is 2 * 1.",
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------------------------
# Examples, faded checks
# ---------------------------------------------------------------------------------------------


def build_examples():
    result = {}
    for key, code in EXAMPLES.items():
        if key in ENDLESS_EXAMPLES:
            out, finished, error = run_plain(code, PLAIN_CAP)
            assert error is None and not finished
            result[key] = {"code": code, "output": out[:ENDLESS_SHOWN_LINES], "endless": True}
        else:
            out, finished, error = run_plain(code, PLAIN_CAP)
            assert error is None and finished, (key, error)
            result[key] = {"code": code, "output": out, "endless": False}
    return result


def build_faded():
    cond_out, ok, err = run_plain(FADED_COND, PLAIN_CAP)
    assert ok and err is None
    while_choices = []
    for choice in FADED_WHILE_CHOICES:
        out, finished, err = run_plain(FADED_WHILE_TEMPLATE.replace("____", choice), PLAIN_CAP)
        assert err is None, err
        while_choices.append({"value": choice, "terminates": finished, "output": out})
    assert [c["value"] for c in while_choices if c["terminates"]] == [FADED_WHILE_RIGHT]
    canonical, ok, err = run_plain("\n".join(FADED_FN_LINES), PLAIN_CAP)
    assert ok and err is None
    orders = {}
    for perm in permutations(range(len(FADED_FN_LINES))):
        out, finished, err = run_plain("\n".join(FADED_FN_LINES[i] for i in perm), PLAIN_CAP)
        good = err is None and out == canonical
        orders[",".join(map(str, perm))] = {
            "ok": good,
            "text": f"Prints {' '.join(out) or 'nothing'}." if err is None else f"{err}.",
        }
    assert [k for k, v in orders.items() if v["ok"]] == ["0,1,2,3"], "the Parsons problem must have one order"
    list_out, ok, err = run_plain(FADED_LIST, PLAIN_CAP)
    assert ok and err is None
    rec_out, ok, err = run_plain(FADED_REC, PLAIN_CAP)
    assert ok and err is None
    return {
        "cond": {"code": FADED_COND, "output": cond_out},
        "while": {"template": FADED_WHILE_TEMPLATE, "choices": while_choices},
        "fn": {"lines": FADED_FN_LINES, "shuffled": FADED_FN_SHUFFLED, "output": canonical, "orders": orders},
        "list": {"code": FADED_LIST, "output": list_out},
        "rec": {"code": FADED_REC, "output": rec_out},
    }


HEADER = """/**
 * GENERATED FILE. Do not edit by hand.
 *
 * Written by `record_traces.py` (next to this file), run on Python __VERSION__. Every snippet here was
 * executed: the stepped ones under `sys.settrace` (call stack, watched variables, list `id()`s),
 * the static ones plainly. To change a snippet, edit the script and run it again.
 *
 * A step describes the state AFTER its `line` ran (`line` is null at the start). `output` is what
 * `print` has written so far, `frames` is the call stack bottom first, `heap` groups the names that
 * share one list (recorded from `id()`), and `branches` / `dim` / `check` are derived from the run.
 *
 * TODO(real): these are recorded by hand-running a script. In the product the tutorial generator
 * runs each snippet when a tutorial is built from a book section, and the traces are stored with
 * the tutorial once the professor approves it.
 */

export type Frame = { label: string; vars: Record<string, string>; ret?: string };
export type BranchState = "taken" | "false" | "skipped" | "pending";
export type Step = {
  /** 1-based line that just ran; null before anything has run. */
  line: number | null;
  kind: "start" | "line" | "call" | "return" | "back" | "end" | "cap";
  /** At most 16 words: what just happened. */
  caption: string;
  /** Call stack, bottom first. `ret` is set on a frame that is returning. */
  frames: Frame[];
  /** Lines of the frames waiting for a call to come back. */
  paused: number[];
  output: string[];
  heap?: { id: number; names: string[]; items: string[] }[];
  focus?: { obj: number; index: number };
  added?: { obj: number; index: number }[];
  branches?: { label: string; state: BranchState }[];
  dim?: number[];
  check?: { expr: string; results: boolean[] };
};
export type Prediction = {
  id: string;
  /** Asked when the student presses Step to reveal step `atStep`. */
  atStep: number;
  question: string;
  choices: string[];
  /** Index into `choices`, derived from the recording. */
  answer: number;
  why: string;
};
export type Trace = {
  id: string;
  label: string;
  view: "branches" | "while" | "stack" | "memory";
  code: string;
  /** True when the snippet never finishes and the trace stops at the step cap. */
  endless: boolean;
  takeaway: string;
  /** From an independent, untraced run of the same code. */
  expectedOutput: string[];
  predictions: Prediction[];
  steps: Step[];
};
export type Example = { code: string; output: string[]; endless: boolean };
export type Faded = {
  cond: { code: string; output: string[] };
  while: { template: string; choices: { value: string; terminates: boolean; output: string[] }[] };
  fn: {
    lines: string[];
    shuffled: number[];
    output: string[];
    /** Every ordering of the lines, run for real: `ok` when it prints the expected output. */
    orders: Record<string, { ok: boolean; text: string }>;
  };
  list: { code: string; output: string[] };
  rec: { code: string; output: string[] };
};

"""


def main():
    traces = {t["id"]: build_trace(t) for t in TRACE_SPECS}
    examples = build_examples()
    faded = build_faded()
    body = HEADER.replace("__VERSION__", sys.version.split()[0])
    body += "export const TRACES: Record<string, Trace> = " + json.dumps(traces, indent=1, ensure_ascii=False) + ";\n\n"
    body += "export const EXAMPLES: Record<string, Example> = " + json.dumps(examples, indent=1, ensure_ascii=False) + ";\n\n"
    body += "export const FADED: Faded = " + json.dumps(faded, indent=1, ensure_ascii=False) + ";\n"
    OUT.write_text(body, encoding="utf-8", newline="\n")
    for key, trace in traces.items():
        print(key, len(trace["steps"]), "steps; output", trace["steps"][-1]["output"])
        for step in trace["steps"]:
            print("   ", step["line"], step["kind"], "|", step["caption"])
    print("examples", {k: v["output"] for k, v in examples.items()})
    print("faded", {k: v.get("output") for k, v in faded.items()})


if __name__ == "__main__":
    main()
