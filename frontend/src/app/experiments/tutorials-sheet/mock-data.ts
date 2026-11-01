/**
 * Mock content for the cheat-sheet prototype, plus the one helper that computes Python results.
 *
 * TODO(real): the patterns, the watch-out line and the "why" text are written by hand. In the real
 * product they are extracted from the book section the student's wrong answers point at (the
 * for-loop / range section) and approved by the professor before a student sees them.
 *
 * Every result shown as "what Python gives" is computed here, not typed, and the examples were
 * checked against CPython (`list(range(4))` -> [0, 1, 2, 3], and so on; see the test file).
 */

/** Python's `list(range(start, stop, step))`, including the empty cases and negative steps. */
export function pyRange(start: number, stop?: number, step = 1): number[] {
  if (step === 0) throw new RangeError("range() arg 3 must not be zero");
  const [from, to] = stop === undefined ? [0, start] : [start, stop];
  const out: number[] = [];
  for (let n = from; step > 0 ? n < to : n > to; n += step) out.push(n);
  return out;
}

/** How Python prints a list: `[1, 2, 3]`, or `[]` when empty. */
export function pyListRepr(items: readonly (number | string)[]): string {
  return `[${items.map((item) => (typeof item === "string" ? `'${item}'` : String(item))).join(", ")}]`;
}

export type Pattern = {
  id: string;
  /** Two or three words: what the pattern is for. */
  label: string;
  code: string;
  /** What the code produces, already computed. */
  result: string;
};

const NUMBERS_TO_ADD = [3, 1, 4];
const LETTERS = ["a", "b"];

// TODO(real): pattern set extracted from the book section and approved by the professor.
export const PATTERNS: readonly Pattern[] = [
  { id: "stop-only", label: "Start at 0", code: "range(4)", result: pyRange(4).join(" ") },
  { id: "start-stop", label: "Pick a start", code: "range(1, 4)", result: pyRange(1, 4).join(" ") },
  { id: "step", label: "Skip ahead", code: "range(0, 10, 3)", result: pyRange(0, 10, 3).join(" ") },
  { id: "list", label: "Walk a list", code: 'for x in ["a", "b"]', result: LETTERS.join(" ") },
  {
    id: "total",
    label: "Add up a total",
    code: "total = 0\nfor n in [3, 1, 4]:\n    total += n",
    result: `total = ${NUMBERS_TO_ADD.reduce((sum, n) => sum + n, 0)}`,
  },
];

// TODO(real): the misconception line comes from the wrong-answer data for this section.
export const WATCH_OUT = {
  code: "range(1, 5)",
  text: `gives ${pyRange(1, 5).join(" ")}. It never reaches 5. For 1 to 5, write`,
  fixCode: "range(1, 6)",
};

/** The "Show me why" text. Kept under 80 words; `code` spans use backticks. */
// TODO(real): generated from the book section, then approved.
export const WHY_TEXT =
  "`range(start, stop)` counts up from start and quits the moment it would reach stop, without using it. " +
  "That is why `range(4)` gives four numbers and the last one is 3: counting from 0, four numbers end at 3. " +
  "The same rule causes the off-by-one mistake. To include 5, the stop has to be 6. " +
  "A quick check: stop minus start is how many times the loop body runs.";

/** Bounds for the two steppers, and the number line's extent. */
export const LINE_MIN = 0;
export const LINE_MAX = 10;
export const DEFAULT_START = 1;
export const DEFAULT_STOP = 5;

export const SAVED_KEY = "tutorials-sheet:for-range:saved";
