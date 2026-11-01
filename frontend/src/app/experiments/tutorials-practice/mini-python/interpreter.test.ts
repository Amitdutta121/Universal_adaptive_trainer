/**
 * Behaviour of the interpreter that the CPython table cannot express: the step trace itself (frames,
 * list identity, captions), the caps, plain-words messages, and "never crashes" on odd input.
 * Values, line numbers and Python's own error names are covered by `cpython-table.test.ts`.
 */

import { describe, expect, it } from "vitest";
import { INTERNAL_MESSAGE, runProgram } from "./interpreter";
import { captionFor, changedVars, condenseOutput, lineSequence } from "./trace";

const run = (src: string) => runProgram(`${src.trim()}\n`);

describe("trace shape", () => {
  it("records the state BEFORE each line runs, then an end step", () => {
    const result = run("x = 1\nx = x + 1\nprint(x)");
    expect(result.status).toBe("ok");
    expect(result.steps.map((s) => s.kind)).toEqual(["line", "line", "line", "end"]);
    const globalsAt = (i: number) =>
      result.steps[i].frames[0].vars.map((v) => `${v.name}=${v.repr}`);
    expect(globalsAt(0)).toEqual([]);
    expect(globalsAt(1)).toEqual(["x=1"]);
    expect(globalsAt(2)).toEqual(["x=2"]);
    expect(result.steps[2].output).toBe("");
    expect(result.steps[3].output).toBe("2\n");
    expect(result.output).toBe("2\n");
  });

  it("captions explain what the previous line did", () => {
    const { steps } = run("x = 5\nif x > 3:\n    print(x)");
    expect(captionFor(steps, 0)).toBe("Line 1 runs first.");
    expect(captionFor(steps, 1)).toBe("`x` is now 5.");
    expect(captionFor(steps, 2)).toBe("`x > 3` is True: run this block.");
    expect(captionFor(steps, 3)).toBe("Printed: 5 The program finished.");
  });

  it("shows a call stack: one frame per nested call, labelled with its arguments", () => {
    const { steps } = run(
      "def fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\nprint(fact(3))",
    );
    const deepest = Math.max(...steps.map((s) => s.frames.length));
    expect(deepest).toBe(4); // Global + fact(3) + fact(2) + fact(1)
    const atBase = steps.find((s) => s.frames.length === deepest && s.line === 3);
    expect(atBase?.frames.map((f) => f.label)).toEqual(["Global", "fact(3)", "fact(2)", "fact(1)"]);
    expect(atBase?.frames[3].vars).toEqual([{ name: "n", type: "int", repr: "1" }]);
    const entered = steps.filter((s) => s.entered).map((s) => s.entered);
    expect(entered).toEqual(["fact(3)", "fact(2)", "fact(1)"]);
    expect(
      captionFor(
        steps,
        steps.findIndex((s) => s.entered === "fact(2)"),
      ),
    ).toContain("Called `fact(2)`");
    // The return value shows up in the caption.
    expect(steps.flatMap((s) => s.after).some((t) => t.includes("Return 6"))).toBe(true);
    expect(run("def f():\n    pass\nprint(f())").steps.flatMap((s) => s.after)).toContain(
      "`f()` ended without `return`, so it gives back None.",
    );
  });

  it("gives every list an id so aliasing is visible, and copies get a new one", () => {
    const { steps } = run("a = [1, 2]\nb = a\nc = a.copy()\nc.append(3)\nprint(a)");
    const last = steps[steps.length - 1].frames[0].vars;
    const byName = Object.fromEntries(last.map((v) => [v.name, v]));
    expect(byName.a.listId).toBe(byName.b.listId);
    expect(byName.c.listId).not.toBe(byName.a.listId);
    expect(byName.c.repr).toBe("[1, 2, 3]");
    expect(byName.a.repr).toBe("[1, 2]");
    expect(steps.flatMap((s) => s.after)).toContain(
      "`b` now refers to the same list as `a` (list #1). Nothing was copied.",
    );
  });

  it("`+=` on a list changes the same list; `a = a + [x]` makes a new one", () => {
    const { steps } = run("a = [1]\nb = a\na += [2]\na = a + [3]");
    const vars = Object.fromEntries(steps[steps.length - 1].frames[0].vars.map((v) => [v.name, v]));
    expect(vars.b.repr).toBe("[1, 2]");
    expect(vars.a.repr).toBe("[1, 2, 3]");
    expect(vars.a.listId).not.toBe(vars.b.listId);
  });

  it("marks which variables changed between two steps", () => {
    const { steps } = run("x = 1\ny = 2\nx = 3");
    expect([...changedVars(steps, 1)]).toEqual(["0:x"]);
    expect([...changedVars(steps, 2)]).toEqual(["0:y"]);
    expect([...changedVars(steps, 3)]).toEqual(["0:x"]);
    expect([...changedVars(steps, 0)]).toEqual([]);
  });

  it("supports the line sequence helper used by the CPython table", () => {
    expect(lineSequence(run("for i in range(2):\n    pass"))).toEqual([1, 2, 1, 2, 1]);
  });

  it("condenses a repeated output line for the answer-versus-actual panel", () => {
    expect(condenseOutput("0\n0\n0\n0\n0\n")).toBe("0  (x5)");
    expect(condenseOutput("1\n2\n3\n")).toBe("1\n2\n3");
    expect(condenseOutput("")).toBe("");
  });
});

describe("caps", () => {
  it("stops a loop that never ends after 300 steps, in plain words", () => {
    const result = run("n = 0\nwhile n < 3:\n    print(n)");
    expect(result.status).toBe("limit");
    expect(result.message).toBe("Stopped after 300 steps. This loop may never end.");
    expect(result.steps.filter((s) => s.kind === "line")).toHaveLength(300);
    const last = result.steps[result.steps.length - 1];
    expect(last.kind).toBe("limit");
    expect(last.message).toBe(result.message);
    expect(captionFor(result.steps, result.steps.length - 1)).toBe(result.message);
    // What ran before the cap is still there to look at.
    expect(result.output.startsWith("0\n0\n")).toBe(true);
  });

  it("honours custom limits", () => {
    const result = runProgram("while True:\n    pass\n", { maxSteps: 10, maxDepth: 20 });
    expect(result.status).toBe("limit");
    expect(result.message).toBe("Stopped after 10 steps. This loop may never end.");
  });

  it("allows 20 nested calls and refuses the 21st with a RecursionError", () => {
    const ok = run(
      "def d(n):\n    if n == 0:\n        return 0\n    return 1 + d(n - 1)\nprint(d(19))",
    );
    expect(ok.status).toBe("ok");
    expect(ok.output).toBe("19\n");
    const tooDeep = run(
      "def d(n):\n    if n == 0:\n        return 0\n    return 1 + d(n - 1)\nprint(d(20))",
    );
    expect(tooDeep.status).toBe("error");
    expect(tooDeep.error?.name).toBe("RecursionError");
    expect(tooDeep.error?.plain).toContain("base case");
  });

  it("refuses to build huge values instead of freezing", () => {
    const result = run('s = "ab" * 100000000');
    expect(result.status).toBe("unsupported");
    expect(result.message).toContain("more than 10,000 items");
  });
});

describe("errors are named the way Python names them, plus one plain line", () => {
  const cases: [string, string, string][] = [
    ["print(y)", "NameError", "Python doesn't know the name `y`"],
    [
      "a = [1, 2]\nprint(a[5])",
      "IndexError",
      "The list has 2 items, so valid positions are 0 to 1 (or -1 to -2). 5 is outside that.",
    ],
    ["a = []\nprint(a[0])", "IndexError", "The list is empty"],
    ["print(1 / 0)", "ZeroDivisionError", "You divided by zero"],
    ['print("a" + 1)', "TypeError", "Turn the number into text with str(...)"],
    ["def f():\n    pass\nprint(f() + 1)", "TypeError", "One of these values is None"],
    [
      "def f():\n    x = x + 1\nf()",
      "UnboundLocalError",
      "`x` is assigned somewhere inside this function",
    ],
    ["x = None\nx.append(1)", "AttributeError", "This value is None"],
    ['int("abc")', "ValueError", "isn't a whole number"],
  ];
  it.each(cases)("%s", (src, name, plain) => {
    const result = run(src);
    expect(result.status).toBe("error");
    expect(result.error?.name).toBe(name);
    expect(result.error?.plain).toContain(plain);
    const last = result.steps[result.steps.length - 1];
    expect(last.kind).toBe("error");
    expect(last.message?.startsWith(`${name}: `)).toBe(true);
    // The error step keeps the highlighted line and the state at the moment of the error.
    expect(last.line).toBe(result.error?.line);
  });

  it("keeps the call stack of the frame that failed", () => {
    const result = run("def f(n):\n    return [1][n]\nf(3)");
    const last = result.steps[result.steps.length - 1];
    expect(last.frames.map((f) => f.label)).toEqual(["Global", "f(3)"]);
    expect(last.line).toBe(2);
  });
});

describe("unsupported syntax gives a clear message, never a crash", () => {
  const cases: [string, string][] = [
    ["import math", "import"],
    ["print(f'{1}')", "f-strings"],
    ["d = {}", "dictionaries and sets"],
    ["xs = [1]\nprint(xs[0:1])", "slicing"],
    ["xs = [3, 1]\nxs.sort()", "the list method `.sort()`"],
    ['"a".upper()', "the string method `.upper()`"],
    ["print(sorted([2, 1]))", "the built-in `sorted()`"],
    ["x = 1\nx.real", "attributes"],
    ["if True: print(1)", "a body on the same line as the colon"],
  ];
  it.each(cases)("%s", (src, feature) => {
    const result = run(src);
    expect(result.status).toBe("unsupported");
    expect(result.message).toContain(feature);
    expect(result.message?.startsWith("This mini-runner doesn't support ")).toBe(true);
    expect(result.message?.endsWith(" yet.")).toBe(true);
  });

  it("keeps what ran before a runtime-unsupported feature", () => {
    const result = run('print("start")\nxs = [2, 1]\nxs.sort()');
    expect(result.status).toBe("unsupported");
    expect(result.output).toBe("start\n");
    const last = result.steps[result.steps.length - 1];
    expect(last.kind).toBe("unsupported");
    expect(last.line).toBe(3);
  });

  it("reports syntax errors without running anything", () => {
    const result = run("if x\n    y = 1");
    expect(result.status).toBe("syntax");
    expect(result.steps).toEqual([]);
    expect(result.error?.name).toBe("SyntaxError");
    expect(result.error?.line).toBe(1);
    expect(result.error?.plain).toContain("missing colon");
  });

  it("never throws or hits an internal error, whatever the input", () => {
    const junk = [
      "",
      "\n\n",
      "   ",
      "(((((((((((((",
      `x = ${"(".repeat(5000)}1${")".repeat(5000)}`,
      "def f(:\n",
      "for\n",
      "while True:\n    pass\n    break\n    x =",
      "x = [",
      "\t\tprint(1)",
      "print(1)\n  ",
      "x = 1 +\n",
      "not",
      "print(",
      "a = b = c = []\nprint(a is b is c)",
      "print(1, )",
      "x = 'unterminated",
      "\u0000",
      "é = 1",
      "x = 10 ** 100000",
      "print(-1 ** 0.5)",
      "print(0 ** -1)",
      "print(2.0 ** 5000)",
      "for i in range(10 ** 12):\n    break",
      "print(len(range(10 ** 30)))",
      "print(int('9' * 400) + 1)",
    ];
    for (const src of junk) {
      const result = runProgram(src);
      expect(result.message ?? "", src.slice(0, 30)).not.toBe(INTERNAL_MESSAGE);
      expect(["ok", "error", "limit", "unsupported", "syntax"]).toContain(result.status);
    }
  });
});

describe("modifying a snippet and re-running", () => {
  it("re-running edited code gives a fresh, independent trace", () => {
    const before = run("x = 3\nif x > 5:\n    print('big')\nelse:\n    print('small')");
    const after = run("x = 9\nif x > 5:\n    print('big')\nelse:\n    print('small')");
    expect(before.output).toBe("small\n");
    expect(after.output).toBe("big\n");
    expect(lineSequence(before)).toEqual([1, 2, 5]);
    expect(lineSequence(after)).toEqual([1, 2, 3]);
  });
});
