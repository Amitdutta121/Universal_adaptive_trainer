import { describe, expect, it } from "vitest";
import { SyntaxIssue, UnsupportedError } from "./errors";
import { parseProgram } from "./parser";

function outcome(src: string): string {
  try {
    parseProgram(src);
    return "ok";
  } catch (e) {
    if (e instanceof UnsupportedError) return `unsupported: ${e.feature}`;
    if (e instanceof SyntaxIssue) return `${e.errorName}: ${e.message}`;
    throw e;
  }
}

describe("parser", () => {
  it("parses the whole teaching subset", () => {
    const program = parseProgram(
      [
        "def f(a, b):",
        "    total = a + b * 2",
        "    if total > 3 and not b:",
        "        return [total, a[0], -b]",
        "    elif total == 0:",
        "        return None",
        "    else:",
        "        pass",
        "    return total",
        "xs = [1, 2]",
        "xs[0] += f(1, 2)",
        "for x in range(3):",
        "    while x < 1 or x is None:",
        "        break",
        "    continue",
        "a = b = xs.copy()",
        "",
      ].join("\n"),
    );
    expect(program.map((s) => s.k)).toEqual(["def", "assign", "aug", "for", "assign"]);
    const def = program[0];
    if (def.k !== "def") throw new Error("expected def");
    // Parameters and every assigned name are local; `a`, `b` come first.
    expect(def.localNames).toEqual(["a", "b", "total"]);
  });

  it("attaches the source text of conditions and assignment targets", () => {
    const [ifStmt] = parseProgram(["if  x >   1:", "    y[0] = 2", ""].join("\n"));
    if (ifStmt.k !== "if") throw new Error("expected if");
    expect(ifStmt.testText).toBe("x >   1");
    const inner = ifStmt.body[0];
    if (inner.k !== "assign") throw new Error("expected assign");
    expect(inner.targets[0].text).toBe("y[0]");
  });

  it("keeps Python's precedence: unary minus below **, comparisons chain, and/or/not order", () => {
    const stmt = parseProgram("x = -2 ** 2\n")[0];
    if (stmt.k !== "assign") throw new Error("expected assign");
    expect(stmt.value.k).toBe("unary");
    const chain = parseProgram("y = 1 < a < 3\n")[0];
    if (chain.k !== "assign") throw new Error("expected assign");
    expect(chain.value.k).toBe("cmp");
    if (chain.value.k === "cmp") expect(chain.value.rest).toHaveLength(2);
  });

  it("names each unsupported construct in plain words", () => {
    expect(outcome("import os\n")).toBe("unsupported: import");
    expect(outcome("class A:\n    pass\n")).toBe("unsupported: classes");
    expect(outcome("try:\n    pass\nexcept:\n    pass\n")).toBe("unsupported: try / except");
    expect(outcome("f = lambda x: x\n")).toBe("unsupported: lambda");
    expect(outcome("a, b = 1, 2\n")).toBe("unsupported: tuples and multiple assignment");
    expect(outcome("x = (1, 2)\n")).toBe("unsupported: tuples");
    expect(outcome("x = [i for i in y]\n")).toBe("unsupported: list comprehensions");
    expect(outcome("x = a[1:2]\n")).toBe("unsupported: slicing (a[i:j])");
    expect(outcome("print(1, end='')\n")).toBe("unsupported: keyword arguments (like end=...)");
    expect(outcome("def f(a=1):\n    pass\n")).toBe("unsupported: default parameter values");
    expect(outcome("def f():\n    def g():\n        pass\n")).toBe(
      "unsupported: a function defined inside another function",
    );
    expect(outcome("x = a if b else c\n")).toBe(
      "unsupported: conditional expressions (x if c else y)",
    );
    expect(outcome("s.upper\n")).toContain("attributes");
    expect(outcome("if x: y = 1\n")).toContain("a body on the same line as the colon");
    expect(outcome("for i in a:\n    pass\nelse:\n    pass\n")).toBe(
      "unsupported: else after a loop",
    );
  });

  it("reports real syntax mistakes as SyntaxError / IndentationError", () => {
    expect(outcome("if x\n    y = 1\n")).toBe("SyntaxError: invalid syntax");
    expect(outcome("x = = 1\n")).toBe("SyntaxError: invalid syntax");
    expect(outcome("print 'a'\n")).toBe("SyntaxError: invalid syntax");
    expect(outcome("break\n")).toBe("SyntaxError: 'break' outside loop");
    expect(outcome("return 1\n")).toBe("SyntaxError: 'return' outside function");
    expect(outcome("if x:\ny = 1\n")).toBe(
      "IndentationError: expected an indented block after 'if' statement on line 1",
    );
    expect(outcome("x = 1\n    y = 2\n")).toBe("IndentationError: unexpected indent");
    expect(outcome("1 = x\n")).toContain("cannot assign to expression");
    expect(outcome("else:\n    pass\n")).toBe("SyntaxError: invalid syntax");
  });
});
