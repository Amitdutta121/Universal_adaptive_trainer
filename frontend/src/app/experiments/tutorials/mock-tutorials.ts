/**
 * Mock tutorials for the student-facing tutorial prototype.
 *
 * TODO(real): everything in this file stands in for tutorials the backend would generate from a
 * book's sections (retrieval → grounded draft → faithfulness check → professor approval). The
 * prose, code and outputs were written by hand. The book names are the ones in the sample bank,
 * but the chapter titles and page numbers in `sources` are INVENTED for the mock and do not point
 * at real pages. `output` on a code block is precomputed here; a real page would run the code
 * (in-browser Python) or store the output the validator produced.
 *
 * Inline text supports `code` and **bold** only; see `Inline` in `components/tutorial-blocks.tsx`.
 */

export type CalloutTone = "idea" | "mistake" | "tip";

export type CheckOption = { text: string; correct?: boolean; why: string };

export type Block =
  | { kind: "p"; text: string; cite?: number }
  | { kind: "list"; items: string[] }
  | {
      kind: "code";
      title?: string;
      code: string;
      /** Precomputed. Absent when the snippet must not be run (an infinite loop, say). */
      output?: string;
      /** Shown instead of a Run button when `output` is absent. */
      note?: string;
    }
  | { kind: "callout"; tone: CalloutTone; title: string; text: string }
  | { kind: "check"; id: string; question: string; code?: string; options: CheckOption[] };

export type TutorialSection = { id: string; title: string; blocks: Block[] };

export type TutorialSource = {
  book: string;
  chapter: string;
  pages: string;
};

export type Tutorial = {
  id: string;
  /** The topic group it sits under in the course outline. */
  topic: string;
  title: string;
  summary: string;
  level: "Beginner" | "Intermediate";
  minutes: number;
  /** The taxonomy subtopics it teaches, as the adaptive engine names them. */
  subtopics: string[];
  sections: TutorialSection[];
  sources: TutorialSource[];
  /** Why the adaptive engine put this in front of the student, when it did. */
  recommendedBecause?: { misses: number; attempts: number; subtopic: string };
  reviewedOn: string;
};

const HEINOLD = "A Practical Introduction to Python Programming (Heinold)";
const THINK = "Think Python (1st ed.)";

export const COURSE = {
  title: "Introduction to Python",
  taxonomy: "Python for Data Science — Intro Programming Module",
};

export const TUTORIALS: Tutorial[] = [
  {
    id: "variables-and-types",
    topic: "Foundations",
    title: "Variables and data types",
    summary: "Name a value, know what kind of value it is, and convert between kinds when you must.",
    level: "Beginner",
    minutes: 6,
    subtopics: ["Variables", "Data types", "Type conversion"],
    reviewedOn: "12 Sep 2026",
    sources: [
      { book: HEINOLD, chapter: "Variables and the type system", pages: "pp. 14–19" },
      { book: THINK, chapter: "Variables, expressions and statements", pages: "pp. 23–27" },
    ],
    sections: [
      {
        id: "what-a-variable-is",
        title: "What a variable is",
        blocks: [
          {
            kind: "p",
            cite: 1,
            text: "A **variable** is a name attached to a value. You create one with `=`, and from then on the name stands for the value wherever you use it.",
          },
          {
            kind: "code",
            title: "variables.py",
            code: `age = 19
price = 4.50
name = "Ada"
is_student = True

print(name, "is", age)`,
            output: "Ada is 19",
          },
          {
            kind: "callout",
            tone: "idea",
            title: "The name points at the value",
            text: "Assigning again does not change the old value, it moves the name. After `age = 20`, the name `age` refers to 20 and nothing else about your program has to be told.",
          },
        ],
      },
      {
        id: "the-four-types",
        title: "The four types you will use first",
        blocks: [
          {
            kind: "p",
            cite: 2,
            text: "Every value has a **type**, and the type decides what you can do with it. Use `type()` to ask.",
          },
          {
            kind: "code",
            title: "types.py",
            code: `age = 19
price = 4.50
name = "Ada"
is_student = True

print(type(age))
print(type(price))
print(type(name))
print(type(is_student))`,
            output: `<class 'int'>
<class 'float'>
<class 'str'>
<class 'bool'>`,
          },
          {
            kind: "list",
            items: [
              "`int` — whole numbers: `19`, `-3`, `0`",
              "`float` — numbers with a decimal point: `4.50`, `-0.1`",
              "`str` — text, in single or double quotes: `\"Ada\"`",
              "`bool` — `True` or `False`, with the capital letter",
            ],
          },
          {
            kind: "check",
            id: "division",
            question: "What does this print?",
            code: "print(7 / 2)",
            options: [
              { text: "3", why: "`/` always gives a float, even when the answer is a whole number. `//` is the one that rounds down." },
              { text: "3.5", correct: true, why: "Right: `/` is true division and returns a `float`. Use `7 // 2` if you want 3." },
              { text: "4", why: "Python does not round for you. `/` keeps the fraction." },
              { text: "It raises an error", why: "Dividing two ints is fine; the result is a float." },
            ],
          },
        ],
      },
      {
        id: "converting",
        title: "Converting between types",
        blocks: [
          {
            kind: "p",
            text: "Text that looks like a number is still text. `input()` always hands you a `str`, so convert it before you calculate with it.",
          },
          {
            kind: "code",
            title: "convert.py",
            code: `a = "5"
b = "3"

print(a + b)
print(int(a) + int(b))`,
            output: `53
8`,
          },
          {
            kind: "callout",
            tone: "mistake",
            title: "\"5\" + \"3\" is \"53\"",
            text: "On two strings, `+` joins them. If a total comes out looking like two numbers glued together, a value is still a string. Wrap it in `int()` or `float()` first.",
          },
        ],
      },
    ],
  },
  {
    id: "if-elif-else",
    topic: "Foundations",
    title: "Making decisions with if, elif and else",
    summary: "Run different code depending on a condition, and see why the order of your checks matters.",
    level: "Beginner",
    minutes: 7,
    subtopics: ["Conditionals", "Boolean expressions"],
    reviewedOn: "12 Sep 2026",
    sources: [
      { book: HEINOLD, chapter: "Decision structures", pages: "pp. 41–49" },
      { book: THINK, chapter: "Conditionals and recursion", pages: "pp. 47–52" },
    ],
    sections: [
      {
        id: "the-shape",
        title: "The shape of a decision",
        blocks: [
          {
            kind: "p",
            cite: 1,
            text: "An `if` statement runs its indented block only when its condition is `True`. Add `elif` for further conditions and `else` for everything left over.",
          },
          {
            kind: "code",
            title: "grade.py",
            code: `score = 74

if score >= 90:
    grade = "A"
elif score >= 70:
    grade = "B"
elif score >= 50:
    grade = "C"
else:
    grade = "F"

print(grade)`,
            output: "B",
          },
          {
            kind: "callout",
            tone: "idea",
            title: "Only one branch runs",
            text: "Python checks the conditions from the top and stops at the first one that is true. That is why the value 74 gets a `B` and never reaches the `C` test.",
          },
        ],
      },
      {
        id: "order-matters",
        title: "Why the order matters",
        blocks: [
          {
            kind: "p",
            text: "Because the first true condition wins, put the most specific test first. Here the second test can never run:",
          },
          {
            kind: "code",
            title: "order.py",
            code: `score = 95

if score >= 50:
    print("pass")
elif score >= 90:
    print("distinction")`,
            output: "pass",
          },
          {
            kind: "callout",
            tone: "mistake",
            title: "= is not ==",
            text: "`=` stores a value, `==` compares two values. Writing `if score = 90:` is a syntax error; writing `if score == 90:` asks the question you meant.",
          },
          {
            kind: "check",
            id: "two-ifs",
            question: "What does this print?",
            code: `x = 10

if x > 5:
    print("A")
if x > 8:
    print("B")
else:
    print("C")`,
            options: [
              { text: "A only", why: "The second `if` is a separate statement, so it is checked too." },
              { text: "A, then B", correct: true, why: "Two separate `if` statements are both evaluated. `x > 5` prints A; `x > 8` is true, so B, and its `else` is skipped." },
              { text: "A, then C", why: "`else` belongs to the second `if`. Since `x > 8` is true, the `else` does not run." },
              { text: "A, B and C", why: "An `else` never runs when its own `if` was true." },
            ],
          },
        ],
      },
    ],
  },
  {
    id: "for-loops",
    topic: "Repetition",
    title: "for loops and range()",
    summary: "Repeat a block once per item, count with range(), and avoid the off-by-one that catches everyone.",
    level: "Beginner",
    minutes: 9,
    subtopics: ["for loops", "range()", "Accumulators"],
    reviewedOn: "14 Sep 2026",
    recommendedBecause: { misses: 2, attempts: 3, subtopic: "for loops" },
    sources: [
      { book: HEINOLD, chapter: "Repetitions", pages: "pp. 58–71" },
      { book: THINK, chapter: "Iteration", pages: "pp. 59–63" },
    ],
    sections: [
      {
        id: "repeat-per-item",
        title: "Repeat once per item",
        blocks: [
          {
            kind: "p",
            cite: 1,
            text: "A `for` loop takes each item of a sequence in turn, gives it a name, and runs the indented block once for each.",
          },
          {
            kind: "code",
            title: "fruits.py",
            code: `fruits = ["apple", "banana", "cherry"]

for fruit in fruits:
    print(fruit.upper())`,
            output: `APPLE
BANANA
CHERRY`,
          },
          {
            kind: "callout",
            tone: "idea",
            title: "You name the loop variable",
            text: "`fruit` is not special. Pick a name that says what one item is, and read the loop as \"for each fruit in fruits\".",
          },
        ],
      },
      {
        id: "counting-with-range",
        title: "Counting with range()",
        blocks: [
          {
            kind: "p",
            cite: 2,
            text: "`range()` produces numbers. `range(5)` is `0, 1, 2, 3, 4`: it starts at 0 and stops **before** 5. Give it a start, a stop and a step to control the count.",
          },
          {
            kind: "code",
            title: "range.py",
            code: `for i in range(5):
    print(i, end=" ")
print()

for n in range(2, 11, 3):
    print(n, end=" ")`,
            output: `0 1 2 3 4
2 5 8`,
          },
          {
            kind: "callout",
            tone: "mistake",
            title: "The stop value is never included",
            text: "`range(1, 5)` gives 1, 2, 3, 4. To count 1 through 5 you need `range(1, 6)`. Most off-by-one errors in loops come from forgetting this.",
          },
          {
            kind: "check",
            id: "range-sum",
            question: "What is `total` at the end?",
            code: `total = 0
for i in range(1, 4):
    total += i
print(total)`,
            options: [
              { text: "4", why: "That would be the last value plus nothing. Trace it: the loop runs for 1, 2 and 3." },
              { text: "6", correct: true, why: "`range(1, 4)` is 1, 2, 3, and 1 + 2 + 3 = 6. The 4 is never reached." },
              { text: "10", why: "That counts 4 as well, which needs `range(1, 5)`." },
              { text: "3", why: "That is how many times the loop ran, not what it added up." },
            ],
          },
        ],
      },
      {
        id: "accumulating",
        title: "Building up a result",
        blocks: [
          {
            kind: "p",
            text: "A loop is often used to build one answer from many items: start a variable before the loop, then update it inside. This is called an **accumulator**.",
          },
          {
            kind: "code",
            title: "total.py",
            code: `total = 0
for price in [4.5, 3.0, 12.25]:
    total += price

print(total)`,
            output: "19.75",
          },
          {
            kind: "p",
            text: "When you also need the position of each item, `enumerate()` hands you both:",
          },
          {
            kind: "code",
            title: "enumerate.py",
            code: `fruits = ["apple", "banana", "cherry"]

for index, fruit in enumerate(fruits, start=1):
    print(f"{index}. {fruit}")`,
            output: `1. apple
2. banana
3. cherry`,
          },
          {
            kind: "callout",
            tone: "tip",
            title: "Reset the accumulator in the right place",
            text: "Set `total = 0` before the loop. Inside the loop it would reset on every pass, and you would only ever see the last item.",
          },
        ],
      },
    ],
  },
  {
    id: "while-loops",
    topic: "Repetition",
    title: "while loops",
    summary: "Repeat until a condition stops being true, stop early with break, and never write the loop that runs forever.",
    level: "Beginner",
    minutes: 7,
    subtopics: ["while loops", "break"],
    reviewedOn: "14 Sep 2026",
    sources: [
      { book: HEINOLD, chapter: "Repetitions", pages: "pp. 72–80" },
      { book: THINK, chapter: "Iteration", pages: "pp. 55–59" },
    ],
    sections: [
      {
        id: "until-false",
        title: "Repeat until the condition fails",
        blocks: [
          {
            kind: "p",
            cite: 1,
            text: "Use `while` when you do not know in advance how many times to repeat. The condition is checked before every pass, and the loop ends the first time it is `False`.",
          },
          {
            kind: "code",
            title: "countdown.py",
            code: `count = 3
while count > 0:
    print(count)
    count -= 1
print("Liftoff!")`,
            output: `3
2
1
Liftoff!`,
          },
        ],
      },
      {
        id: "forever",
        title: "The loop that never ends",
        blocks: [
          {
            kind: "p",
            text: "Something inside the loop has to move the condition towards `False`. If nothing does, it runs forever.",
          },
          {
            kind: "code",
            title: "stuck.py",
            code: `count = 3
while count > 0:
    print(count)
    # count never changes`,
            note: "Not run: this loop never stops. In a terminal, Ctrl+C interrupts it.",
          },
          {
            kind: "callout",
            tone: "mistake",
            title: "Check that the variable in the condition changes",
            text: "When a program hangs, look at the `while` line, then find the line inside that changes each variable it mentions. If there is none, that is the bug.",
          },
        ],
      },
      {
        id: "break",
        title: "Leaving early with break",
        blocks: [
          {
            kind: "p",
            cite: 2,
            text: "`break` ends the nearest loop at once. Paired with `while True:` it lets you put the exit test anywhere in the body.",
          },
          {
            kind: "code",
            title: "first_square.py",
            code: `attempts = 0
while True:
    attempts += 1
    if attempts * attempts > 50:
        break

print(attempts)`,
            output: "8",
          },
          {
            kind: "check",
            id: "doubling",
            question: "What does this print?",
            code: `n = 1
while n < 20:
    n *= 2
print(n)`,
            options: [
              { text: "16", why: "16 is less than 20, so the loop goes round once more." },
              { text: "20", why: "`n` doubles, so it goes 1, 2, 4, 8, 16, 32. It never equals 20." },
              { text: "32", correct: true, why: "16 < 20 so it doubles to 32; now 32 < 20 is false and the loop ends. The print sees 32." },
              { text: "31", why: "`*=` multiplies; it does not add one." },
            ],
          },
        ],
      },
    ],
  },
  {
    id: "functions",
    topic: "Functions",
    title: "Defining and calling functions",
    summary: "Package code under a name, pass values in, get a value back, and tell return from print.",
    level: "Beginner",
    minutes: 8,
    subtopics: ["Defining functions", "Parameters", "return"],
    reviewedOn: "16 Sep 2026",
    sources: [
      { book: HEINOLD, chapter: "Functions", pages: "pp. 96–108" },
      { book: THINK, chapter: "Functions", pages: "pp. 29–38" },
    ],
    sections: [
      {
        id: "define-and-call",
        title: "Define once, call anywhere",
        blocks: [
          {
            kind: "p",
            cite: 1,
            text: "`def` gives a block of code a name. The names in the brackets are **parameters**; the values you pass when you call it are **arguments**.",
          },
          {
            kind: "code",
            title: "greet.py",
            code: `def greet(name):
    return f"Hello, {name}!"

message = greet("Ada")
print(message)`,
            output: "Hello, Ada!",
          },
        ],
      },
      {
        id: "return-vs-print",
        title: "return is not print",
        blocks: [
          {
            kind: "p",
            cite: 2,
            text: "`print` shows something on the screen. `return` hands a value back to whoever called the function. A function with no `return` hands back `None`.",
          },
          {
            kind: "code",
            title: "add.py",
            code: `def add(a, b):
    print(a + b)

result = add(2, 3)
print(result)`,
            output: `5
None`,
          },
          {
            kind: "callout",
            tone: "mistake",
            title: "The answer appeared, but you cannot use it",
            text: "The `5` above came from the `print` inside `add`. The function itself returned `None`, so `result` holds nothing useful. If you want to calculate with the answer, `return` it.",
          },
          {
            kind: "check",
            id: "no-return",
            question: "What does this print?",
            code: `def double(x):
    x * 2

print(double(4))`,
            options: [
              { text: "8", why: "The function computes `x * 2` but never returns it, so nothing comes back." },
              { text: "None", correct: true, why: "There is no `return`, so the call evaluates to `None`, and that is what `print` shows." },
              { text: "4", why: "The parameter is not changed by the function's body." },
              { text: "It raises an error", why: "The code is valid; it just returns nothing." },
            ],
          },
        ],
      },
      {
        id: "defaults",
        title: "Default values",
        blocks: [
          {
            kind: "p",
            text: "Give a parameter a default and callers may leave it out. Parameters with defaults go after the ones without.",
          },
          {
            kind: "code",
            title: "area.py",
            code: `def area(width, height=1):
    return width * height

print(area(4, 3))
print(area(4))`,
            output: `12
4`,
          },
          {
            kind: "callout",
            tone: "tip",
            title: "Name what a function does",
            text: "A good function name is a verb or a question (`area`, `is_even`, `greet`). If you cannot name it in a word or two, it is probably doing two jobs.",
          },
        ],
      },
    ],
  },
];

export const TUTORIAL_TOPICS = [...new Set(TUTORIALS.map((tutorial) => tutorial.topic))];

export function tutorialById(id: string): Tutorial | undefined {
  return TUTORIALS.find((tutorial) => tutorial.id === id);
}

/** How many `check` blocks a tutorial has, so a finished reading can say "2 of 2 checks". */
export function countChecks(tutorial: Tutorial): number {
  return tutorial.sections.reduce(
    (sum, section) => sum + section.blocks.filter((block) => block.kind === "check").length,
    0,
  );
}
