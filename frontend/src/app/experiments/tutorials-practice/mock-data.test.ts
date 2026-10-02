/**
 * The mock content is checked against the mini-runner (which is itself checked against CPython in
 * `mini-python/cpython-table.test.ts`): every correct option really is what the code prints, every
 * distractor really is wrong, and every worked / faded example works as written.
 *
 * TODO(real): the real pipeline runs this validation at question-generation time, on CPython.
 */

import { describe, expect, it } from "vitest";
import { EXPECTED } from "./mini-python/expected.generated";
import { runProgram } from "./mini-python";
import {
  BANK,
  type ChoiceQuestion,
  MISCONCEPTIONS,
  type ParsonsQuestion,
  TOPICS,
} from "./mock-data";
import {
  checkFaded,
  checkParsons,
  correctOption,
  initialStats,
  move,
  optionMatches,
  parsonsCode,
  parsonsSolution,
  pickNext,
  recordCorrect,
  recordMiss,
  recordOutcome,
} from "./practice-logic";

const choices = BANK.filter((q): q is ChoiceQuestion => q.kind === "choice");
const parsons = BANK.filter((q): q is ParsonsQuestion => q.kind === "parsons");
const knownCode = new Set(EXPECTED.map((c) => c.code));
const words = (text: string) => text.trim().split(/\s+/).length;

describe("the question bank", () => {
  it("has ten questions, two per topic, and two Parsons problems (conditionals, functions)", () => {
    expect(BANK).toHaveLength(10);
    for (const topic of TOPICS) expect(BANK.filter((q) => q.topic === topic.id)).toHaveLength(2);
    expect(parsons.map((q) => q.topic).sort()).toEqual(["conditionals", "functions"]);
    expect(new Set(BANK.map((q) => q.id)).size).toBe(10);
  });

  it("interleaves topics: no two neighbouring questions share a topic", () => {
    for (let i = 1; i < BANK.length; i++) expect(BANK[i].topic).not.toBe(BANK[i - 1].topic);
  });

  it.each(choices.map((q) => [q.id, q] as const))(
    "%s: the code is in the CPython table",
    (_id, q) => {
      expect(knownCode.has(q.code), "add this snippet to record_expected.py").toBe(true);
    },
  );

  it.each(parsons.map((q) => [q.id, q] as const))(
    "%s: the solution is in the CPython table",
    (_id, q) => {
      expect(knownCode.has(parsonsCode(q, parsonsSolution(q)))).toBe(true);
    },
  );

  it.each(choices.map((q) => [q.id, q] as const))(
    "%s: exactly one option is right, and the runner agrees",
    (_id, q) => {
      const result = runProgram(q.code);
      expect(q.options.filter((o) => o.misconception === null)).toHaveLength(1);
      for (const option of q.options) {
        expect(optionMatches(option, result), option.text).toBe(option.misconception === null);
      }
      // Every wrong option is tagged with a misconception of this topic.
      for (const option of q.options) {
        if (option.misconception) {
          const topic = MISCONCEPTIONS[option.misconception].topic;
          expect([q.topic, "functions"]).toContain(topic);
        }
      }
      expect(correctOption(q)).toBeDefined();
    },
  );

  it("the never-ending loop question is answered by the 300-step cap, not by output", () => {
    const q = choices.find((c) => c.id === "while-never-changes");
    expect(q).toBeDefined();
    const result = runProgram(q?.code ?? "");
    expect(result.status).toBe("limit");
    expect(q?.options.find((o) => o.describes === "never_ends")?.misconception).toBeNull();
  });

  it.each(parsons.map((q) => [q.id, q] as const))(
    "%s: only a working order passes, and the start order does not",
    (_id, q) => {
      expect(checkParsons(q, parsonsSolution(q)).correct).toBe(true);
      expect(new Set(q.start)).toEqual(new Set(q.lines.map((l) => l.id)));
      const start = checkParsons(q, q.start);
      expect(start.correct).toBe(false);
      expect(start.misconception).not.toBeNull();
      // A name used before it is set is diagnosed as a top-to-bottom mistake.
      const swapped = checkParsons(q, [...parsonsSolution(q)].reverse());
      expect(swapped.correct).toBe(false);
    },
  );

  it("the ordering diagnosis is mock but deterministic: any run that fails is a top-to-bottom mistake", () => {
    const cond = parsons.find((q) => q.id === "cond-parsons");
    if (!cond) throw new Error("missing question");
    // temp assigned after the chain: NameError.
    const late = ["l1", "l2", "l3", "l4", "l5", "l6", "l0"];
    expect(checkParsons(cond, late).result.error?.name).toBe("NameError");
    expect(checkParsons(cond, late).misconception).toBe("top_to_bottom");
    // else: with nothing under it: IndentationError.
    const broken = ["l0", "l1", "l2", "l3", "l4", "l6", "l5"];
    expect(checkParsons(cond, broken).result.status).toBe("syntax");
    expect(checkParsons(cond, broken).misconception).toBe("top_to_bottom");
  });
});

describe("misconceptions", () => {
  const all = Object.values(MISCONCEPTIONS);

  it("has one per key, and every tag used in the bank exists", () => {
    for (const [key, m] of Object.entries(MISCONCEPTIONS)) expect(m.id).toBe(key);
    for (const q of BANK) {
      const tags =
        q.kind === "choice"
          ? q.options.flatMap((o) => (o.misconception ? [o.misconception] : []))
          : [q.onError, q.onWrongOutput];
      for (const tag of tags) expect(MISCONCEPTIONS[tag]).toBeDefined();
    }
  });

  it.each(all.map((m) => [m.id, m] as const))(
    "%s: the rung 1 line is short and the worked example runs",
    (_id, m) => {
      expect(words(m.hint)).toBeLessThanOrEqual(22);
      expect(m.hint.startsWith("Looks like") || m.hint.startsWith("Python runs")).toBe(true);
      // Rung 1 never quotes an answer of any question in the bank.
      for (const q of choices) {
        const answer = correctOption(q).text;
        if (answer.length > 3) expect(m.hint.includes(answer)).toBe(false);
      }
      const worked = runProgram(m.worked.code);
      expect(worked.status).toBe("ok");
      expect(worked.output.length).toBeGreaterThan(0);
      expect(m.worked.code.trim().split("\n").length).toBeLessThanOrEqual(7);
      expect(words(m.worked.note)).toBeLessThanOrEqual(24);
    },
  );

  it.each(all.map((m) => [m.id, m] as const))(
    "%s: the faded example passes with the answer line and fails without one",
    (_id, m) => {
      expect(checkFaded(m, m.faded.answer)).toEqual({ passed: true, feedback: "" });
      expect(checkFaded(m, "").passed).toBe(false);
      expect(checkFaded(m, "pass").passed).toBe(false);
      expect(checkFaded(m, "print(").feedback).toContain("does not run");
      // The stem is the same idea with the last line removed: the program alone prints nothing useful.
      expect(runProgram(m.faded.stem).output).not.toBe(m.faded.expected);
    },
  );

  it("accepts a different correct line, not just the answer key", () => {
    expect(checkFaded(MISCONCEPTIONS.no_auto_update, "i += 1").passed).toBe(true);
    expect(checkFaded(MISCONCEPTIONS.no_auto_update, "print(i)").passed).toBe(false);
    expect(checkFaded(MISCONCEPTIONS.no_auto_update, "print(i)").feedback).toContain("never stops");
    expect(checkFaded(MISCONCEPTIONS.bound_off_by_one, "print(n + 1)").feedback).toContain(
      "prints 5",
    );
  });
});

describe("adaptivity stub", () => {
  it("two misses on a topic bring the next question from that topic", () => {
    let stats = initialStats();
    const first = pickNext([], stats);
    expect(first?.question.id).toBe("cond-shadowed-elif");
    stats = recordMiss(recordMiss(stats, "conditionals"), "conditionals");
    const next = pickNext(["cond-shadowed-elif"], stats);
    expect(next?.reason).toBe("steered");
    expect(next?.question.id).toBe("cond-parsons");
  });

  it("one miss does not steer, and a correct answer clears the streak", () => {
    let stats = recordMiss(initialStats(), "lists");
    expect(pickNext(["cond-shadowed-elif"], stats)?.reason).toBe("order");
    stats = recordMiss(stats, "lists");
    expect(pickNext(["cond-shadowed-elif"], stats)?.question.topic).toBe("lists");
    stats = recordCorrect(stats, "lists");
    expect(stats.lists.missStreak).toBe(0);
    expect(pickNext(["cond-shadowed-elif"], stats)?.reason).toBe("order");
  });

  it("steers to the least confident topic first, and falls back to bank order when it is used up", () => {
    // while: one right answer, then two misses (0.2); recursion: two misses (0.0), so recursion goes first.
    let stats = recordCorrect(initialStats(), "while");
    for (const t of ["while", "while", "recursion", "recursion"] as const) {
      stats = recordMiss(stats, t);
    }
    expect(pickNext([], stats)?.question.topic).toBe("recursion");
    const usedUp = BANK.filter((q) => q.topic === "recursion").map((q) => q.id);
    expect(pickNext(usedUp, stats)?.question.topic).toBe("while");
    const everyone = pickNext(
      BANK.filter((q) => q.topic === "recursion" || q.topic === "while").map((q) => q.id),
      stats,
    );
    expect(everyone?.reason).toBe("order");
    expect(
      pickNext(
        BANK.map((q) => q.id),
        stats,
      ),
    ).toBeNull();
  });

  it("keeps confidence between 0 and 1 and one dot per finished question", () => {
    let stats = initialStats();
    for (let i = 0; i < 5; i++) stats = recordMiss(stats, "lists");
    expect(stats.lists.confidence).toBe(0);
    for (let i = 0; i < 9; i++) stats = recordCorrect(stats, "lists");
    expect(stats.lists.confidence).toBe(1);
    stats = recordOutcome(stats, "lists", "missed");
    expect(stats.lists.results).toEqual(["missed"]);
  });

  it("moves a line up or down and ignores moves off either end", () => {
    expect(move(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(move(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(move(["a", "b", "c"], 0, -1)).toEqual(["a", "b", "c"]);
    expect(move(["a", "b", "c"], 2, 3)).toEqual(["a", "b", "c"]);
  });
});
