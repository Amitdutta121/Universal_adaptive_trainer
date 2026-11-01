/**
 * The hard requirement: the TypeScript interpreter agrees with real CPython on a table of snippets.
 *
 * `expected.generated.ts` is written by `record_expected.py`, which ran every snippet under
 * `sys.settrace` on CPython and recorded the final stdout, every 'line' event of the snippet's own
 * frames (module level and inside functions), and how the run ended. For each snippet this test asserts
 *   - identical stdout,
 *   - identical sequence of executed line numbers,
 *   - the same ending: ok / limit / the same exception class AND CPython's message text.
 *
 * Normalisations (see DESIGN_NOTES.md):
 *   1. Only 'line' events are compared, not 'call' / 'return' / 'exception' events.
 *   2. Snippets that would run forever or 1000 frames deep are recorded with the SAME caps as the
 *      interpreter (300 line events, 20 nested function frames), so those rows prove "identical up to
 *      the cap", not "identical to an uncapped run". The recorder raises StepLimit / RecursionError
 *      from its trace function at exactly the point the interpreter's cap fires.
 *   3. A run that ends in an exception still has its lines and stdout compared up to the raise.
 */

import { describe, expect, it } from "vitest";
import { EXPECTED } from "./expected.generated";
import { runProgram } from "./interpreter";
import { lineSequence } from "./trace";

const ERROR_CLASSES = [
  "NameError",
  "IndexError",
  "ZeroDivisionError",
  "TypeError",
  "UnboundLocalError",
  "AttributeError",
  "ValueError",
  "RecursionError",
];

describe("mini-python vs CPython (recorded table)", () => {
  it("covers at least 20 snippets, every topic and every error class", () => {
    expect(EXPECTED.length).toBeGreaterThanOrEqual(20);
    const topics = new Set(EXPECTED.map((c) => c.topic));
    for (const topic of ["conditionals", "while", "functions", "lists", "recursion"]) {
      expect(topics.has(topic), `topic ${topic}`).toBe(true);
    }
    const errors = new Set(EXPECTED.map((c) => c.error?.name));
    for (const name of ERROR_CLASSES) expect(errors.has(name), `error class ${name}`).toBe(true);
    expect(EXPECTED.some((c) => c.status === "limit")).toBe(true);
  });

  it.each(EXPECTED.map((c) => [c.id, c] as const))("%s", (_id, expected) => {
    const result = runProgram(expected.code);

    expect(result.output, "stdout").toBe(expected.stdout);
    expect(lineSequence(result), "executed line numbers").toEqual(expected.lines);

    if (expected.status === "limit") {
      expect(result.status).toBe("limit");
    } else if (expected.status === "error") {
      expect(result.status).toBe("error");
      expect(result.error?.name).toBe(expected.error?.name);
      expect(result.error?.message).toBe(expected.error?.message);
      // Every error also carries a plain-words line.
      expect(result.error?.plain.length ?? 0).toBeGreaterThan(10);
    } else {
      expect(result.status, result.message ?? result.error?.message ?? "").toBe("ok");
    }
  });
});
