/**
 * Stand-in content for the micro-card tutorial: Python `for` loops with `range()`.
 *
 * TODO(real): every string in this file is hand-written. In the product the cards are generated from
 * the course book, approved by the professor, and picked for a student because of the questions they
 * missed in adaptive practice (`MISSED` below comes from that session).
 *
 * Every `output` was produced by running its `source` with Python 3; do not edit one without
 * re-running the snippet.
 *
 * Copy limits, asserted in the test: headline <= 8 words, body <= 25 words.
 */

export const PRACTICE_HREF = "/experiments/student";

// TODO(real): from the student's adaptive practice session, per topic.
export const MISSED = { topic: "for loops", missedCount: 2, askedCount: 3 };

export type Snippet = { source: string; output: string };

export type LessonCard = {
  kind: "lesson";
  id: string;
  headline: string;
  /** `code` spans are allowed; nothing else. */
  body: string;
  snippet?: Snippet;
};

export type CheckOption = { id: string; code: string; feedback: string };

export type CheckCard = {
  kind: "check";
  id: string;
  headline: string;
  question: string;
  options: CheckOption[];
  correctId: string;
};

export type Card = LessonCard | CheckCard;

export const CARDS: Card[] = [
  {
    kind: "lesson",
    id: "intro",
    headline: `You missed ${MISSED.missedCount} of ${MISSED.askedCount} loop questions`,
    body: "Most slips come from the same few ideas. Six quick cards, then one check. About a minute.",
  },
  {
    kind: "lesson",
    id: "for-list",
    headline: "A for loop repeats once per item",
    body: "Each pass, `name` holds the next item in the list. The indented line runs every time.",
    snippet: {
      source: 'for name in ["Ana", "Bo", "Cy"]:\n    print(name)',
      output: "Ana\nBo\nCy",
    },
  },
  {
    kind: "lesson",
    id: "range-n",
    headline: "range(3) counts 0, 1, 2",
    body: "`range(n)` gives n numbers and starts at 0, not 1. So `range(3)` runs three passes.",
    snippet: {
      source: "for i in range(3):\n    print(i)",
      output: "0\n1\n2",
    },
  },
  {
    kind: "lesson",
    id: "range-stop",
    headline: "range stops before its end value",
    body: "The stop value is never included. `range(5)` ends at 4, one short of 5.",
    snippet: {
      source: "print(list(range(5)))",
      output: "[0, 1, 2, 3, 4]",
    },
  },
  {
    kind: "lesson",
    id: "range-start-stop",
    headline: "Pick your start with two values",
    body: "`range(start, stop)` begins at start and still stops before stop.",
    snippet: {
      source: "for i in range(2, 5):\n    print(i)",
      output: "2\n3\n4",
    },
  },
  {
    kind: "lesson",
    id: "total",
    headline: "Build a total with a variable",
    body: "Set it to 0 before the loop, add to it each pass, and print after the loop ends.",
    snippet: {
      source: "total = 0\nfor i in range(1, 4):\n    total += i\nprint(total)",
      output: "6",
    },
  },
  {
    kind: "lesson",
    id: "off-by-one",
    headline: "range(1, 5) does not include 5",
    body: "This is the classic off-by-one. To include 5, stop at 6: the last value plus one.",
    snippet: {
      source: "print(list(range(1, 5)))\nprint(list(range(1, 6)))",
      output: "[1, 2, 3, 4]\n[1, 2, 3, 4, 5]",
    },
  },
  {
    kind: "check",
    id: "check",
    headline: "One quick check",
    question: "Which one loops over 1, 2, 3, 4, 5?",
    correctId: "b",
    options: [
      { id: "a", code: "range(1, 5)", feedback: "It stops before 5, so it gives 1 to 4." },
      { id: "b", code: "range(1, 6)", feedback: "Stop is 6, so the last value is 5." },
      { id: "c", code: "range(5)", feedback: "It starts at 0, so it gives 0 to 4." },
      { id: "d", code: "range(0, 5)", feedback: "Same as range(5): 0 to 4." },
    ],
  },
];
