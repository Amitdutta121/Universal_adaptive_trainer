/**
 * Mock data and logic for the "Predict, then reveal" tutorial prototype.
 *
 * TODO(real): the three experiments below are hand-written stand-ins. In the product they are
 * generated from the book section the student is stuck on (here: for loops and `range()`), and
 * each one is approved by the professor before a student sees it. The challenge target and the
 * "2 of 3 wrong" trigger come from the student's adaptive-practice history.
 *
 * Everything shown as a Python result is computed by `rangeLength` / `rangeHead` /
 * `rangeContains`, a faithful re-implementation of CPython's `range(start, stop, step)` on
 * arbitrary-size integers (BigInt), so a huge range costs nothing. The test file checks them
 * against real Python output.
 */

// ---- range() re-implementation ---------------------------------------------------------------

const ZERO = BigInt(0);
const ONE = BigInt(1);
const TWO = BigInt(2);

/** What Python raises for a bad `range()` call, kept as data so the UI can say it in plain words. */
export class PythonError extends Error {
  readonly kind: "ValueError" | "TypeError";
  constructor(kind: "ValueError" | "TypeError", message: string) {
    super(message);
    this.name = kind;
    this.kind = kind;
  }
}

/** Same text as CPython 3.12. */
export const ZERO_STEP_MESSAGE = "range() arg 3 must not be zero";

/** `len(range(start, stop, step))`. */
export function rangeLength(start: bigint, stop: bigint, step: bigint): bigint {
  if (step === ZERO) throw new PythonError("ValueError", ZERO_STEP_MESSAGE);
  const span = step > ZERO ? stop - start : start - stop;
  if (span <= ZERO) return ZERO;
  const size = step > ZERO ? step : -step;
  return (span + size - ONE) / size;
}

/** The first `limit` items of `list(range(start, stop, step))`. */
export function rangeHead(start: bigint, stop: bigint, step: bigint, limit: number): bigint[] {
  const length = rangeLength(start, stop, step);
  const count = length < BigInt(limit) ? Number(length) : limit;
  const items: bigint[] = [];
  for (let index = 0; index < count; index += 1) items.push(start + BigInt(index) * step);
  return items;
}

/** `value in range(start, stop, step)`. */
export function rangeContains(start: bigint, stop: bigint, step: bigint, value: bigint): boolean {
  if (step === ZERO) throw new PythonError("ValueError", ZERO_STEP_MESSAGE);
  const inBounds = step > ZERO ? value >= start && value < stop : value <= start && value > stop;
  return inBounds && (value - start) % step === ZERO;
}

/** `sum(range(start, stop, step))`, in closed form. */
export function rangeSum(start: bigint, stop: bigint, step: bigint): bigint {
  const length = rangeLength(start, stop, step);
  if (length === ZERO) return ZERO;
  const last = start + (length - ONE) * step;
  return ((start + last) * length) / TWO;
}

export function formatCount(value: bigint): string {
  return value.toLocaleString("en-US");
}

// ---- experiments 1-3: predict, then reveal ---------------------------------------------------

export type Experiment = {
  id: string;
  /** Shown as the snippet. */
  code: string;
  /** The `range()` arguments the snippet uses (`range(stop)` has start 0). */
  start: number;
  stop: number;
  /** "print": the loop prints each i. "total": the loop adds i and prints the total. */
  kind: "print" | "total";
  question: string;
  /** Answer options for "print" experiments; a "total" experiment takes a typed number. */
  options?: number[][];
  /** One sentence. Backticks mark inline code. */
  insight: string;
};

/** TODO(real): generated from the book section and approved by the professor. */
export const EXPERIMENTS: readonly Experiment[] = [
  {
    id: "range-stop",
    code: "for i in range(3):\n    print(i)",
    start: 0,
    stop: 3,
    kind: "print",
    question: "What prints?",
    options: [
      [1, 2, 3],
      [0, 1, 2],
      [0, 1, 2, 3],
    ],
    insight: "`range(3)` starts at 0, stops before 3.",
  },
  {
    id: "range-start-stop",
    code: "for i in range(1, 4):\n    print(i)",
    start: 1,
    stop: 4,
    kind: "print",
    question: "What prints?",
    options: [
      [1, 2, 3, 4],
      [1, 2, 3],
      [0, 1, 2, 3],
    ],
    insight: "`range(1, 4)` starts at 1, stops before 4.",
  },
  {
    id: "range-total",
    code: "total = 0\nfor i in range(1, 5):\n    total += i\nprint(total)",
    start: 1,
    stop: 5,
    kind: "total",
    question: "What is total?",
    insight: "`range(1, 5)` stops before 5: 1+2+3+4 = 10.",
  },
];

/** Three experiments plus the free-play step. */
export const TOTAL_STEPS = EXPERIMENTS.length + 1;

/** What the snippet really prints, one line per `print`. */
export function experimentOutput(experiment: Experiment): string[] {
  const start = BigInt(experiment.start);
  const stop = BigInt(experiment.stop);
  if (experiment.kind === "total") return [rangeSum(start, stop, ONE).toString()];
  return rangeHead(start, stop, ONE, 1000).map(String);
}

export function optionLabel(option: number[]): string {
  return option.join(" ");
}

/** The comparable form of what the snippet prints (lines joined by a space). */
export function experimentAnswer(experiment: Experiment): string {
  return experimentOutput(experiment).join(" ");
}

export type Answer = { guess: string; correct: boolean };

export function judgeGuess(experiment: Experiment, guess: string): Answer {
  return { guess, correct: guess === experimentAnswer(experiment) };
}

export type TotalGuess = { ok: true; value: string } | { ok: false; message: string };

/** A typed total: whole numbers only, normalised ("+010" -> "10"). */
export function parseTotalGuess(text: string): TotalGuess {
  const trimmed = text.trim();
  if (trimmed === "") return { ok: false, message: "Type a whole number." };
  if (!/^[+-]?\d{1,15}$/.test(trimmed)) return { ok: false, message: "Whole numbers only." };
  return { ok: true, value: BigInt(trimmed).toString() };
}

/** The wrong predictions, in order, for the recap. */
export function surprises(answers: Readonly<Record<string, Answer>>): Experiment[] {
  return EXPERIMENTS.filter((experiment) => answers[experiment.id]?.correct === false);
}

/** A Python comment that says what happened and what the student expected. */
export function outcomeComment(experiment: Experiment, guess: string): string {
  const actual = experimentAnswer(experiment);
  return experiment.kind === "total"
    ? `# total is ${actual}, you said ${guess}`
    : `# printed ${actual}, you said ${guess}`;
}

// ---- experiment 4: free play -----------------------------------------------------------------

/** How many list items are shown before "and N more". */
export const DISPLAY_CAP = 20;
export const CHALLENGE_TARGET = 5;
/** TODO(real): starting values chosen so the challenge needs the off-by-one insight. */
export const FREE_PLAY_DEFAULTS: Record<FieldName, string> = { start: "0", stop: "5", step: "1" };

export type FieldName = "start" | "stop" | "step";

export type FreePlayOutcome =
  | { status: "incomplete"; message: string; fields: FieldName[] }
  | { status: "error"; message: string; python: string; fields: FieldName[] }
  | {
      status: "ok";
      start: bigint;
      stop: bigint;
      step: bigint;
      length: bigint;
      head: bigint[];
      /** Items not shown because of the cap. */
      hidden: bigint;
      /** Why the list is empty, in plain words; null when it is not. */
      emptyReason: string | null;
      /** Whether CHALLENGE_TARGET is in the list. */
      hasTarget: boolean;
    };

const FIELDS: FieldName[] = ["start", "stop", "step"];
const INTEGER = /^[+-]?\d{1,16}$/;
const DECIMAL = /^[+-]?(\d+\.\d*|\.\d+)$/;

/** Parses the three text boxes and computes what `list(range(start, stop, step))` gives. */
export function parseFreePlay(input: Record<FieldName, string>): FreePlayOutcome {
  const text = { start: input.start.trim(), stop: input.stop.trim(), step: input.step.trim() };

  const empty = FIELDS.filter((field) => text[field] === "" || text[field] === "-" || text[field] === "+");
  if (empty.length > 0) {
    return {
      status: "incomplete",
      message: empty.length === 1 ? `Fill in ${empty[0]}.` : "Fill in the empty boxes.",
      fields: empty,
    };
  }

  const decimals = FIELDS.filter((field) => DECIMAL.test(text[field]));
  if (decimals.length > 0) {
    const field = decimals[0] as FieldName;
    return {
      status: "error",
      message: `range() only takes whole numbers, not ${text[field]}.`,
      python: "TypeError: 'float' object cannot be interpreted as an integer",
      fields: decimals,
    };
  }

  const bad = FIELDS.filter((field) => !INTEGER.test(text[field]));
  if (bad.length > 0) {
    return { status: "incomplete", message: "Numbers only, like 3 or -2.", fields: bad };
  }

  const start = BigInt(text.start);
  const stop = BigInt(text.stop);
  const step = BigInt(text.step);
  if (step === ZERO) {
    return {
      status: "error",
      message: "A step of 0 never moves, so Python refuses.",
      python: `ValueError: ${ZERO_STEP_MESSAGE}`,
      fields: ["step"],
    };
  }

  const length = rangeLength(start, stop, step);
  const head = rangeHead(start, stop, step, DISPLAY_CAP);
  let emptyReason: string | null = null;
  if (length === ZERO) {
    emptyReason =
      step > ZERO ? "Empty: start is not below stop." : "Empty: counting down needs start above stop.";
  }
  return {
    status: "ok",
    start,
    stop,
    step,
    length,
    head,
    hidden: length - BigInt(head.length),
    emptyReason,
    hasTarget: rangeContains(start, stop, step, BigInt(CHALLENGE_TARGET)),
  };
}

/** `[0, 1, 2, 3, 4]` exactly as Python prints it; a capped list is cut after the cap, unclosed. */
export function formatList(head: bigint[], hidden: bigint): string {
  const items = head.map(String).join(", ");
  return hidden > ZERO ? `[${items},` : `[${items}]`;
}

/** After the challenge is met: the one thing to take away, depending on which way it counts. */
export function challengeInsight(step: bigint): string {
  return step > ZERO
    ? `Stop is never included, so it must be past ${CHALLENGE_TARGET}.`
    : `Stop is never included, so it must be below ${CHALLENGE_TARGET}.`;
}
