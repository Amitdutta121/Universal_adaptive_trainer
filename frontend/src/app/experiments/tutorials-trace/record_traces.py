"""Records the step-by-step traces the /experiments/tutorials-trace prototype plays back.

Run:  D:/FInalAdaptiveTrainer/.venv/Scripts/python.exe record_traces.py
It executes each snippet for real under `sys.settrace`, snapshots the watched variables and the
stdout after every line, and writes `mock-data.ts` next to this file. Only the caption wording
rules below are written by hand; every value and every line of output is recorded.

TODO(real): this is the shape of the recorder a tutorial generator would run at build time, then
have validated with the tutorial's approval, instead of a hand-run script.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

# One spec per trace. `watch` is what the variables panel shows; `secret` is masked until reveal.
TRACES = [
    {
        "id": "list",
        "label": "Loop a list",
        "code": 'fruits = ["apple", "banana", "cherry"]\nfor fruit in fruits:\n    print(fruit)',
        "watch": ["fruits", "fruit"],
        "secret": [],
        "line_captions": {1: "fruits is a list of three items."},
        "takeaway": "for hands you each item in turn, once per pass.",
    },
    {
        "id": "total",
        "label": "Running total",
        "code": "total = 0\nfor i in range(1, 4):\n    total = total + i\nprint(total)",
        "watch": ["i", "total"],
        "secret": [],
        "line_captions": {1: "total starts at 0."},
        "takeaway": "range(1, 4) gives 1, 2, 3: it stops before 4.",
    },
    {
        "id": "off-by-one",
        "label": "Off by one",
        "code": (
            "total = 0\n"
            "for i in range(1, 5):  # I expect 1, 2, 3, 4, 5\n"
            "    total = total + i\n"
            "print(total)"
        ),
        "watch": ["i", "total"],
        "secret": [],
        "line_captions": {1: "total starts at 0."},
        "takeaway": "To reach 5, write range(1, 6). The stop is never included.",
        "expectation": {"variable": "i", "expected": "5"},
    },
]

# The "Now you try" snippet: `total` is masked in the UI until the student has predicted it.
TRY = {
    "id": "try",
    "label": "Now you try",
    "code": "total = 0\nfor n in range(2, 5):\n    total = total + n\nprint(total)",
    "watch": ["n", "total"],
    "secret": ["total"],
    "line_captions": {1: "total starts at 0."},
    "takeaway": "",
    "masked_captions": True,
}


class Recorder:
    def __init__(self, code: str, watch: list[str]) -> None:
        self.watch = watch
        self.out = io.StringIO()
        self.events: list[dict] = []
        self.code = compile(code, "<snippet>", "exec")

    def snap(self, frame, line):
        env = frame.f_locals
        self.events.append(
            {
                "line": line,
                "vars": {name: repr(env[name]) for name in self.watch if name in env},
                "output": self.out.getvalue().splitlines(),
            }
        )

    def tracer(self, frame, event, _arg):
        if frame.f_code is not self.code:
            return None
        if event == "line":
            self.snap(frame, frame.f_lineno)
        elif event == "return":
            self.snap(frame, None)
        return self.tracer

    def run(self):
        sys.settrace(self.tracer)
        try:
            with contextlib.redirect_stdout(self.out):
                exec(self.code, {"__name__": "__snippet__"})
        finally:
            sys.settrace(None)
        # The event at line L holds the state BEFORE L runs; a step shows the state AFTER its line,
        # which is the state recorded at the next event (the final "return" event closes the last).
        steps = []
        for now, after in zip(self.events, self.events[1:]):
            steps.append({"line": now["line"], "vars": after["vars"], "output": after["output"]})
        return steps


def caption(spec, source_line, line, before, step):
    masked = spec.get("masked_captions", False)
    m_for = re.match(r"\s*for (\w+) in ", source_line)
    if m_for:
        var = m_for.group(1)
        if var in before["vars"] and before["vars"][var] == step["vars"].get(var):
            if spec.get("expectation"):
                call = re.search(r"range\(.*?\)", source_line).group(0)
                return f"No 5 comes: {call} stops before 5."
            return "No values left. The loop stops."
        return f"{var} takes the next value: {step['vars'][var]}"
    if line in spec["line_captions"]:
        return spec["line_captions"][line]
    m_acc = re.match(r"\s*total = total \+ (\w+)", source_line)
    if m_acc:
        if masked:
            return "total changes. Where will it end?"
        var = m_acc.group(1)
        return f"total was {before['vars']['total']}, add {step['vars'][var]}: now {step['vars']['total']}"
    if source_line.strip().startswith("print("):
        if masked:
            return "print shows the final total."
        shown = step["output"][-1]
        if spec.get("expectation"):
            return f"Prints {shown}, not 15. The 5 never ran."
        return f"print shows {shown} in the output."
    raise ValueError(f"no caption rule for line {line}: {source_line!r}")


def build(spec):
    steps = Recorder(spec["code"], spec["watch"]).run()
    source = spec["code"].splitlines()
    prev = {"vars": {}, "output": []}
    for step in steps:
        step["caption"] = caption(spec, source[step["line"] - 1], step["line"], prev, step)
        assert len(step["caption"].split()) <= 12, step["caption"]
        prev = step
    trace = {
        "id": spec["id"],
        "label": spec["label"],
        "code": spec["code"],
        "secret": spec["secret"],
        "takeaway": spec["takeaway"],
        "steps": steps,
    }
    if spec.get("expectation"):
        # First step at which the loop has finished: "expected 5, got 4" is true from there on.
        finished = next(i + 1 for i, s in enumerate(steps) if s["caption"].startswith("No 5"))
        trace["expectation"] = {**spec["expectation"], "fromStep": finished}
    return trace


def ts_literal(value, indent=0):
    """JSON, but one step per line so the file stays reviewable."""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = ",\n".join(f"{pad}  {json.dumps(k)}: {ts_literal(v, indent + 1)}" for k, v in value.items())
        return "{\n" + inner + ",\n" + pad + "}"
    if isinstance(value, list) and value and isinstance(value[0], dict):
        if "steps" in value[0]:
            inner = ",\n".join(f"{pad}  {ts_literal(v, indent + 1)}" for v in value)
            return "[\n" + inner + ",\n" + pad + "]"
        inner = ",\n".join(f"{pad}  {json.dumps(v)}" for v in value)
        return "[\n" + inner + ",\n" + pad + "]"
    return json.dumps(value)


HEADER = """/**
 * Mock traces for `/experiments/tutorials-trace`.
 *
 * GENERATED by `record_traces.py` (next to this file): every snippet was executed under
 * `sys.settrace` on Python __VERSION__, and each step below is what it recorded. To change a
 * snippet, edit the script and re-run it; do not edit this file by hand.
 *
 * A step describes the state AFTER its line ran: `line` is 1-based, `vars` holds `repr()` of each
 * watched variable that exists by then, `output` is what `print` has written so far.
 *
 * TODO(real): these traces are recorded by hand-running a script. In the product they come from the
 * tutorial generator, which runs each snippet when the tutorial is built and stores the trace with
 * the tutorial after the professor approves it.
 */

export type Step = {
  line: number;
  vars: Record<string, string>;
  output: string[];
  /** At most 12 words: what just happened. */
  caption: string;
};

export type Trace = {
  id: string;
  label: string;
  code: string;
  /** Variables whose values are masked until the student has predicted them. */
  secret: string[];
  /** One line shown once the trace has run to its end. */
  takeaway: string;
  /** From `fromStep` on, the panel shows what the student expected next to what happened. */
  expectation?: { variable: string; expected: string; fromStep: number };
  steps: Step[];
};

"""


def main():
    traces = [build(spec) for spec in TRACES]
    try_trace = build(TRY)
    body = HEADER.replace("__VERSION__", sys.version.split()[0])
    body += "export const TRACES: Trace[] = " + ts_literal(traces) + ";\n\n"
    body += '/** The "Now you try" snippet. `total` is hidden until the student reveals. */\n'
    body += "export const TRY_TRACE: Trace = " + ts_literal(try_trace) + ";\n\n"
    final_total = try_trace["steps"][-1]["vars"]["total"]
    # The wrong choices are the two classic mistakes; check the numbers the explanations quote.
    assert final_total == str(sum(range(2, 5)))
    assert sum(range(2, 6)) == 14  # counted the stop value
    assert sum(range(5)) == 10  # forgot the start
    body += (
        "/** TODO(real): the choices and the reason for each wrong one come from the tutorial author. */\n"
        "export const TRY_CHOICES = [\n"
        '  { value: "14", why: "That counts the 5. range(2, 5) stops before 5." },\n'
        '  { value: "' + final_total + '", why: "2 + 3 + 4. It starts at 2 and stops before 5." },\n'
        '  { value: "10", why: "That is range(5), which starts at 0. This one starts at 2." },\n'
        "] as const;\n\n"
        'export const TRY_ANSWER = "' + final_total + '";\n'
    )
    (HERE / "mock-data.ts").write_text(body, encoding="utf-8", newline="\n")
    for t in [*traces, try_trace]:
        last = t["steps"][-1]
        print(t["id"], len(t["steps"]), "steps; final vars", last["vars"], "output", last["output"])


if __name__ == "__main__":
    main()
