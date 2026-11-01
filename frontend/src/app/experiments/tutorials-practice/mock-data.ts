/**
 * Mock content for the practice-first prototype: five topics, eleven misconceptions, ten questions.
 *
 * TODO(real): everything in this file is hand-written. In the real system the question, its
 * misconception-tagged distractors, and the worked / faded examples would be produced when the
 * question is generated, validated by running the code in a sandbox (Pyodide or a server, recording
 * the trace from CPython), and then reviewed by the professor. The tags, hints and examples below
 * are checked against the mini-runner only by `mock-data.test.ts`.
 */

export type TopicId = "conditionals" | "while" | "functions" | "lists" | "recursion";

export const TOPICS: readonly { id: TopicId; label: string }[] = [
  { id: "conditionals", label: "Conditionals" },
  { id: "while", label: "While loops" },
  { id: "functions", label: "Functions" },
  { id: "lists", label: "Lists" },
  { id: "recursion", label: "Recursion" },
];

export const topicLabel = (id: TopicId): string => TOPICS.find((t) => t.id === id)?.label ?? id;

export type MisconceptionId =
  | "all_branches"
  | "specific_wins"
  | "no_auto_update"
  | "bound_off_by_one"
  | "print_vs_return"
  | "call_runs_body"
  | "negative_index"
  | "alias_copy"
  | "base_case_exit"
  | "stack_order"
  | "top_to_bottom";

export interface Misconception {
  id: MisconceptionId;
  topic: TopicId;
  /** Rung 1: one line that names the misconception and does NOT give the answer. */
  hint: string;
  /** Rung 3, part 1: a short worked example (its output is produced by running it). */
  worked: { code: string; note: string };
  /**
   * Rung 3, part 2: the same idea with new values and the LAST line blanked. The student's line is
   * put after `stem` (indented by `indent`) and the whole program is run: it passes when the output
   * equals `expected`.
   */
  faded: { stem: string; indent: string; goal: string; expected: string; answer: string };
}

export const MISCONCEPTIONS: Record<MisconceptionId, Misconception> = {
  all_branches: {
    id: "all_branches",
    topic: "conditionals",
    hint: "Looks like you expected more than one branch to run. Check what happens once a branch is chosen.",
    worked: {
      code: 'n = 5\nif n > 1:\n    print("A")\nelif n > 3:\n    print("B")\n',
      note: "Both conditions are true, but only the first true branch runs.",
    },
    faded: {
      stem: 'n = 8\nlabel = "low"\nif n > 3:\n    label = "A"\nelif n > 6:\n    label = "B"\n',
      indent: "",
      goal: "Finish the last line so it prints the label this chain set.",
      expected: "A\n",
      answer: "print(label)",
    },
  },
  specific_wins: {
    id: "specific_wins",
    topic: "conditionals",
    hint: "Looks like you expected the `elif` to run. Check which condition is true first.",
    worked: {
      code: 'n = 8\nif n > 3:\n    print("mid")\nelif n > 6:\n    print("high")\n',
      note: "Conditions are tried top to bottom. The first true one wins, even if a later one is more specific.",
    },
    faded: {
      stem: 'score = 9\ngrade = "low"\nif score > 4:\n    grade = "ok"\nelif score > 8:\n    grade = "top"\n',
      indent: "",
      goal: "Finish the last line so it prints the grade that was set.",
      expected: "ok\n",
      answer: "print(grade)",
    },
  },
  no_auto_update: {
    id: "no_auto_update",
    topic: "while",
    hint: "Looks like you expected the loop variable to change by itself. Check what changes it.",
    worked: {
      code: "i = 0\nwhile i < 3:\n    print(i)\n    i = i + 1\n",
      note: "`i` only changes because the last line changes it. Without that line the loop never ends.",
    },
    faded: {
      stem: 'i = 0\nwhile i < 2:\n    print("x")\n',
      indent: "    ",
      goal: "Finish the last line, inside the loop, so it prints x twice and stops.",
      expected: "x\nx\n",
      answer: "i = i + 1",
    },
  },
  bound_off_by_one: {
    id: "bound_off_by_one",
    topic: "while",
    hint: "Looks like the loop ran one time too many or too few. Check exactly when the condition turns False.",
    worked: {
      code: "n = 1\nwhile n < 3:\n    print(n)\n    n = n + 1\n",
      note: "`n < 3` turns False when n reaches 3, so 3 is never printed. `<=` would include it.",
    },
    faded: {
      stem: "n = 1\nwhile n < 4:\n    n = n + 1\n",
      indent: "",
      goal: "Finish the last line so it prints the value n ends with.",
      expected: "4\n",
      answer: "print(n)",
    },
  },
  print_vs_return: {
    id: "print_vs_return",
    topic: "functions",
    hint: "Looks like you expected `print` to hand the value back. Check what `result` holds.",
    worked: {
      code: "def add(a, b):\n    return a + b\nprint(add(2, 3))\n",
      note: "`return` hands the value to the caller. `print` only shows it, and the call then gives back None.",
    },
    faded: {
      stem: "def double(n):\n    return n * 2\n",
      indent: "",
      goal: "Finish the last line so it prints 14, double of 7.",
      expected: "14\n",
      answer: "print(double(7))",
    },
  },
  call_runs_body: {
    id: "call_runs_body",
    topic: "functions",
    hint: "Looks like you skipped what runs inside the call. Check when the body's `print` happens.",
    worked: {
      code: 'def hi():\n    print("hi")\nhi()\n',
      note: "The body runs at the moment of the call, before the next line of the caller.",
    },
    faded: {
      stem: 'def bye():\n    print("bye")\n',
      indent: "",
      goal: "Finish the last line so the program prints bye.",
      expected: "bye\n",
      answer: "bye()",
    },
  },
  negative_index: {
    id: "negative_index",
    topic: "lists",
    hint: "Looks like a negative index counted from the wrong end. Check where `-1` points.",
    worked: {
      code: "a = [10, 20, 30]\nprint(a[-1])\n",
      note: "`-1` is the last item, `-2` the one before it. Counting from the front starts at 0.",
    },
    faded: {
      stem: "a = [10, 20, 30]\n",
      indent: "",
      goal: "Finish the last line so it prints the second-to-last item.",
      expected: "20\n",
      answer: "print(a[-2])",
    },
  },
  alias_copy: {
    id: "alias_copy",
    topic: "lists",
    hint: "Looks like you expected `b = a` to make a separate copy. Check what `b` refers to.",
    worked: {
      code: "a = [1, 2]\nb = a\nb.append(3)\nprint(a)\n",
      note: "`b = a` shares one list. A change made through `b` shows up in `a`.",
    },
    faded: {
      stem: "a = [1, 2]\nb = a.copy()\nb.append(3)\n",
      indent: "",
      goal: "Finish the last line so it prints the untouched original.",
      expected: "[1, 2]\n",
      answer: "print(a)",
    },
  },
  base_case_exit: {
    id: "base_case_exit",
    topic: "recursion",
    hint: "Looks like the base case did more or less than you expected. Check what runs before its `return`.",
    worked: {
      code: "def down(n):\n    if n == 0:\n        return\n    print(n)\n    down(n - 1)\ndown(2)\n",
      note: "When n is 0 the function returns at once, so 0 is never printed.",
    },
    faded: {
      stem: "def down(n):\n    if n == 0:\n        return\n    print(n)\n    down(n - 1)\n",
      indent: "",
      goal: "Finish the last line so it prints 3, 2, 1 and never 0.",
      expected: "3\n2\n1\n",
      answer: "down(3)",
    },
  },
  stack_order: {
    id: "stack_order",
    topic: "recursion",
    hint: "Looks like you expected the calls to print in a different order. Check what runs after the recursive call returns.",
    worked: {
      code: "def up(n):\n    if n == 0:\n        return\n    up(n - 1)\n    print(n)\nup(2)\n",
      note: "The `print` waits until the deeper call returns, so the smallest n prints first.",
    },
    faded: {
      stem: "def up(n):\n    if n == 0:\n        return\n    up(n - 1)\n    print(n)\n",
      indent: "",
      goal: "Finish the last line so it prints 1, 2, 3.",
      expected: "1\n2\n3\n",
      answer: "up(3)",
    },
  },
  top_to_bottom: {
    id: "top_to_bottom",
    topic: "functions",
    hint: "Python runs lines from top to bottom. Check that each name exists before it is used.",
    worked: {
      code: "price = 4\nprint(price * 2)\n",
      note: "`price` is set on line 1, so line 2 can use it. Swap them and line 1 fails.",
    },
    faded: {
      stem: "price = 4\n",
      indent: "",
      goal: "Finish the last line so it prints double the price.",
      expected: "8\n",
      answer: "print(price * 2)",
    },
  },
};

// ---- questions ------------------------------------------------------------------------------

export interface ChoiceOption {
  id: string;
  /** What the option says: the program's output, or a description when the output is not finite. */
  text: string;
  /** null = the correct option. TODO(real): produced and validated at question-generation time. */
  misconception: MisconceptionId | null;
  /** For an option that describes a loop that never ends instead of quoting output. */
  describes?: "never_ends";
}

export interface ChoiceQuestion {
  kind: "choice";
  id: string;
  topic: TopicId;
  code: string;
  options: ChoiceOption[];
}

export interface ParsonsLine {
  id: string;
  /** Includes its indentation; only the ORDER is up to the student. */
  text: string;
}

export interface ParsonsQuestion {
  kind: "parsons";
  id: string;
  topic: TopicId;
  goal: string;
  /** What the correctly ordered program prints. */
  expected: string;
  /** In solution order. */
  lines: ParsonsLine[];
  /** The order the student starts from (ids). */
  start: string[];
  /** Mock diagnosis (TODO(real)): what a wrong order is tagged as, depending on how it fails. */
  onError: MisconceptionId;
  onWrongOutput: MisconceptionId;
}

export type Question = ChoiceQuestion | ParsonsQuestion;

const line = (id: string, text: string): ParsonsLine => ({ id, text });

/** Ten questions, two per topic, interleaved. Two are Parsons problems (conditionals, functions). */
export const BANK: Question[] = [
  {
    kind: "choice",
    id: "cond-shadowed-elif",
    topic: "conditionals",
    code: 'score = 85\nif score >= 60:\n    print("pass")\nelif score >= 80:\n    print("good")\nelse:\n    print("fail")\n',
    options: [
      { id: "a", text: "pass", misconception: null },
      { id: "b", text: "good", misconception: "specific_wins" },
      { id: "c", text: "pass\ngood", misconception: "all_branches" },
    ],
  },
  {
    kind: "choice",
    id: "while-never-changes",
    topic: "while",
    code: "count = 0\nwhile count < 3:\n    print(count)\n",
    options: [
      { id: "a", text: "0\n1\n2", misconception: "no_auto_update" },
      { id: "b", text: "Prints 0 forever", misconception: null, describes: "never_ends" },
      { id: "c", text: "0", misconception: "no_auto_update" },
    ],
  },
  {
    kind: "choice",
    id: "fn-print-vs-return",
    topic: "functions",
    code: "def add(a, b):\n    print(a + b)\nresult = add(2, 3)\nprint(result)\n",
    options: [
      { id: "a", text: "5\n5", misconception: "print_vs_return" },
      { id: "b", text: "5\nNone", misconception: null },
      { id: "c", text: "None", misconception: "call_runs_body" },
    ],
  },
  {
    kind: "choice",
    id: "list-negative-index",
    topic: "lists",
    code: "a = [10, 20, 30, 40]\nprint(a[-1], a[1])\n",
    options: [
      { id: "a", text: "10 20", misconception: "negative_index" },
      { id: "b", text: "30 20", misconception: "negative_index" },
      { id: "c", text: "40 20", misconception: null },
    ],
  },
  {
    kind: "choice",
    id: "rec-countdown",
    topic: "recursion",
    code: 'def countdown(n):\n    if n == 0:\n        print("go")\n        return\n    print(n)\n    countdown(n - 1)\ncountdown(2)\n',
    options: [
      { id: "a", text: "go", misconception: "base_case_exit" },
      { id: "b", text: "2\n1\ngo", misconception: null },
      { id: "c", text: "go\n1\n2", misconception: "stack_order" },
    ],
  },
  {
    kind: "parsons",
    id: "cond-parsons",
    topic: "conditionals",
    goal: "Put the lines in order so the program prints warm.",
    expected: "warm\n",
    lines: [
      line("l0", "temp = 20"),
      line("l1", "if temp > 25:"),
      line("l2", '    print("hot")'),
      line("l3", "elif temp > 15:"),
      line("l4", '    print("warm")'),
      line("l5", "else:"),
      line("l6", '    print("cold")'),
    ],
    start: ["l3", "l0", "l6", "l1", "l4", "l5", "l2"],
    onError: "top_to_bottom",
    onWrongOutput: "specific_wins",
  },
  {
    kind: "choice",
    id: "while-off-by-one",
    topic: "while",
    code: "n = 1\nwhile n < 4:\n    print(n)\n    n = n + 1\n",
    options: [
      { id: "a", text: "1\n2\n3\n4", misconception: "bound_off_by_one" },
      { id: "b", text: "1\n2\n3", misconception: null },
      { id: "c", text: "1\n2", misconception: "bound_off_by_one" },
    ],
  },
  {
    kind: "parsons",
    id: "fn-parsons",
    topic: "functions",
    goal: "Put the lines in order so the program prints 12.",
    expected: "12\n",
    lines: [
      line("l0", "def times_three(n):"),
      line("l1", "    return n * 3"),
      line("l2", "result = times_three(4)"),
      line("l3", "print(result)"),
    ],
    start: ["l2", "l0", "l3", "l1"],
    onError: "top_to_bottom",
    onWrongOutput: "print_vs_return",
  },
  {
    kind: "choice",
    id: "list-alias",
    topic: "lists",
    code: "a = [1, 2, 3]\nb = a\nb.append(4)\nprint(a)\n",
    options: [
      { id: "a", text: "[1, 2, 3]", misconception: "alias_copy" },
      { id: "b", text: "[4]", misconception: "alias_copy" },
      { id: "c", text: "[1, 2, 3, 4]", misconception: null },
    ],
  },
  {
    kind: "choice",
    id: "rec-print-after",
    topic: "recursion",
    code: "def show(n):\n    if n == 0:\n        return\n    show(n - 1)\n    print(n)\nshow(3)\n",
    options: [
      { id: "a", text: "3\n2\n1", misconception: "stack_order" },
      { id: "b", text: "0\n1\n2\n3", misconception: "base_case_exit" },
      { id: "c", text: "1\n2\n3", misconception: null },
    ],
  },
];
