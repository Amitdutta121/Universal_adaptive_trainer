/**
 * Mock content for the inline-help prototype: a 3-question bank where every wrong option is tagged
 * with the misconception it reveals, plus one refresher per misconception.
 *
 * TODO(real): in production none of this is hand-written. The misconception-tagged distractors, the
 * per-option reasons and the refreshers are generated together with the question (from the course
 * book), then reviewed by the professor before students see them. The `SOURCE_LINE` page comes from
 * the retrieval chunk the question was generated from.
 *
 * Every correct answer and snippet `output` below was checked by running the `code` string with
 * Python. If you edit a snippet, re-run it and paste the real output.
 */

export type MisconceptionId =
  | "stop_included"
  | "start_at_one"
  | "count_not_sum"
  | "overwrite_not_add";

export type Snippet = {
  code: string;
  /** Exact stdout of `code`, without the trailing newline. */
  output: string;
};

export type Refresher = {
  /** Short name of the misconception, shown as the drawer title. */
  title: string;
  /** At most 3 lines. */
  short: [string, string, string];
  shortSnippet: Snippet;
  /** Exactly 6 lines, shown on the second time the same misconception is picked. */
  full: [string, string, string, string, string, string];
  fullSnippet: Snippet;
};

export type Option = {
  id: string;
  /** Rendered in monospace: these are code outputs. */
  text: string;
  correct: boolean;
  /** Set on every wrong option. */
  misconception?: MisconceptionId;
  /** The one-line reason shown in the result. Written for this option, not generic. */
  reason: string;
};

export type Question = {
  id: string;
  prompt: string;
  code: string;
  options: Option[];
};

export const TOPIC_LABEL = "Loops · for and range()";

export const SOURCE_LINE = "A Practical Introduction to Python Programming, p.62 (mock)";

export const QUESTIONS: Question[] = [
  {
    id: "q-sum-1-4",
    prompt: "What does this print?",
    // python: prints 6
    code: `total = 0
for i in range(1, 4):
    total += i
print(total)`,
    options: [
      {
        id: "a",
        text: "6",
        correct: true,
        reason: "range(1, 4) gives 1, 2, 3, and 1 + 2 + 3 = 6.",
      },
      {
        id: "b",
        text: "10",
        correct: false,
        misconception: "stop_included",
        reason: "That adds 4 too. range(1, 4) stops before 4, so it only gives 1, 2, 3.",
      },
      {
        id: "c",
        text: "3",
        correct: false,
        misconception: "count_not_sum",
        reason:
          "3 is how many times the loop runs. total += i adds the value of i each time: 1 + 2 + 3.",
      },
    ],
  },
  {
    id: "q-print-range-3",
    prompt: "What does this print on one line?",
    // python: prints "0 1 2 " (trailing space from end=" ")
    code: `for i in range(3):
    print(i, end=" ")`,
    options: [
      {
        id: "a",
        text: "0 1 2",
        correct: true,
        reason: "range(3) starts at 0 and stops before 3: 0, 1, 2.",
      },
      {
        id: "b",
        text: "1 2 3",
        correct: false,
        misconception: "start_at_one",
        reason: "range(n) starts at 0, not 1. To get 1, 2, 3 you would write range(1, 4).",
      },
      {
        id: "c",
        text: "0 1 2 3",
        correct: false,
        misconception: "stop_included",
        reason: "That includes 3. The stop value is never produced: range(3) ends at 2.",
      },
    ],
  },
  {
    id: "q-overwrite-2-5",
    prompt: "What does this print?",
    // python: prints 4
    code: `total = 0
for i in range(2, 5):
    total = i
print(total)`,
    options: [
      {
        id: "a",
        text: "4",
        correct: true,
        reason: "total = i replaces total each time, so it ends as the last value, 4.",
      },
      {
        id: "b",
        text: "9",
        correct: false,
        misconception: "overwrite_not_add",
        reason: "9 would need total += i. Plain = throws away the old total on every pass.",
      },
      {
        id: "c",
        text: "5",
        correct: false,
        misconception: "stop_included",
        reason: "The last value of range(2, 5) is 4. Its stop value, 5, is never used.",
      },
    ],
  },
];

export const REFRESHERS: Record<MisconceptionId, Refresher> = {
  stop_included: {
    title: "range stops before the end",
    short: [
      "range(a, b) counts up from a and stops before b.",
      "So range(1, 4) gives 1, 2, 3, and never 4.",
      "The last value is always b - 1.",
    ],
    shortSnippet: {
      code: `for i in range(1, 4):
    print(i)`,
      output: "1\n2\n3",
    },
    full: [
      "range(start, stop) makes numbers from start up to, but not including, stop.",
      "So range(1, 4) is 1, 2, 3. It never reaches 4.",
      "How many values? stop - start, here 4 - 1 = 3.",
      "To include 4, write range(1, 5).",
      "range(4) is short for range(0, 4): 0, 1, 2, 3.",
      "Check yourself: the last value is always stop - 1.",
    ],
    fullSnippet: {
      code: `print(list(range(1, 4)))
print(list(range(1, 5)))
print(list(range(4)))`,
      output: "[1, 2, 3]\n[1, 2, 3, 4]\n[0, 1, 2, 3]",
    },
  },
  start_at_one: {
    title: "range starts at 0",
    short: [
      "With one number, range starts at 0, not 1.",
      "range(3) gives 0, 1, 2: three values, and the first is 0.",
      "For 1, 2, 3 give both ends: range(1, 4).",
    ],
    shortSnippet: {
      code: `print(list(range(3)))
print(list(range(1, 4)))`,
      output: "[0, 1, 2]\n[1, 2, 3]",
    },
    full: [
      "range(n) is short for range(0, n).",
      "It always starts at 0 and stops before n.",
      "So range(3) is 0, 1, 2: three values.",
      "If you want to start at 1, say so: range(1, n + 1).",
      "range(1, 4) is 1, 2, 3, and range(1, 3 + 1) is the same.",
      "Check yourself: len(range(n)) is n, and the first value is 0.",
    ],
    fullSnippet: {
      code: `n = 3
print(len(range(n)))
print(list(range(n)))
print(list(range(1, n + 1)))`,
      output: "3\n[0, 1, 2]\n[1, 2, 3]",
    },
  },
  count_not_sum: {
    title: "The loop repeats, total adds",
    short: [
      "The body runs once per value, and does what you wrote.",
      "total += i adds the value of i, not 1.",
      "Trace it: total goes 0, 1, 3, 6.",
    ],
    shortSnippet: {
      code: `total = 0
for i in range(1, 4):
    total += i
    print(i, total)`,
      output: "1 1\n2 3\n3 6",
    },
    full: [
      "A for loop repeats its body once per value of range.",
      "What the body does is up to you.",
      "total += i means total = total + i.",
      "To count passes instead, you would write total += 1.",
      "Trace by hand: total is 0, then 0 + 1, then 1 + 2, then 3 + 3.",
      "Check yourself: 3 passes does not mean the answer is 3.",
    ],
    fullSnippet: {
      code: `total = 0
count = 0
for i in range(1, 4):
    total += i
    count += 1
print(total, count)`,
      output: "6 3",
    },
  },
  overwrite_not_add: {
    title: "= replaces, += adds",
    short: [
      "total = i throws away the old total on each pass.",
      "total += i keeps it and adds i on top.",
      "With plain =, total ends as the last value only.",
    ],
    shortSnippet: {
      code: `a = 0
b = 0
for i in range(1, 4):
    a = i
    b += i
print(a, b)`,
      output: "3 6",
    },
    full: [
      "Accumulating means keeping a running total across passes.",
      "total += i is total = total + i: it reads the old total first.",
      "total = i never reads the old total, so it is lost.",
      "After the loop, plain = leaves only the last i.",
      "Start the total before the loop (total = 0), add inside it.",
      "Check yourself: no + anywhere means nothing is being added up.",
    ],
    fullSnippet: {
      code: `last = 0
total = 0
for i in range(2, 5):
    last = i
    total += i
print(last, total)`,
      output: "4 9",
    },
  },
};
