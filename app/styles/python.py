"""The Intro Python style library (docs/QUESTION_SETUP_PLAN.md).

Curated content, not mock data: these are the styles the product ships for the ``intro_python``
subject. Seeded from the setup prototype's templates
(``frontend/src/app/experiments/question-setup/mock-python.ts``). Every example is a real,
correct question: output-prediction answers are what CPython prints, and the test suite runs
them to keep it that way (``tests/test_styles.py``).

Ids are stored on questions and setups -- never rename one; add a new style instead.
"""

from __future__ import annotations

from app.domain.enums import Difficulty, QuestionType
from app.styles.schema import ExampleOption, ExampleQuestion, QuestionStyle

SUBJECT = "intro_python"

E, M, H = Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD

_RUNS_OUTPUT = "Runs the code when the question is made and compares the exact output"
_RUNS_TESTS = "Runs hidden tests on the student's code"


def _choices(*options: tuple[str, bool]) -> list[ExampleOption]:
    return [ExampleOption(text=text, correct=correct) for text, correct in options]


def _style(
    id: str,
    name: str,
    summary: str,
    question_type: QuestionType,
    difficulty_range: list[Difficulty],
    checked_by: str,
    applies_to: list[str],
    examples: tuple[ExampleQuestion, ExampleQuestion],
) -> QuestionStyle:
    return QuestionStyle(
        id=id,
        subject=SUBJECT,
        name=name,
        summary=summary,
        question_type=question_type,
        difficulty_range=difficulty_range,
        checked_by=checked_by,
        applies_to=applies_to,
        examples=examples,
    )


PYTHON_STYLES: list[QuestionStyle] = [
    _style(
        "py.concept_check",
        "Check one concept on a tiny snippet",
        "Students read one or two lines and pick what is true about them.",
        QuestionType.MULTIPLE_CHOICE,
        [E, M],
        "One correct option out of four",
        ["data types", "operators", "expressions", "strings", "lists", "dictionaries", "tuples"],
        (
            ExampleQuestion(
                prompt="After this line runs, what is the type of x?",
                code="x = 7 / 2",
                options=_choices(
                    ("int", False), ("float", True), ("str", False), ("It raises an error", False)
                ),
                answer="float",
                grounding="Expressions and statements",
            ),
            ExampleQuestion(
                prompt="What does this expression evaluate to?",
                code="'abc' * 2",
                options=_choices(
                    ("'abcabc'", True), ("'aabbcc'", False), ("'abc2'", False), ("TypeError", False)
                ),
                answer="'abcabc'",
                grounding="String operations",
            ),
        ),
    ),
    _style(
        "py.predict_output",
        "Predict the output of a short snippet",
        "Students read up to five lines and type exactly what is printed.",
        QuestionType.OUTPUT_PREDICTION,
        [E],
        _RUNS_OUTPUT,
        ["print", "strings", "slicing", "indexing", "for loops", "arithmetic"],
        (
            ExampleQuestion(
                prompt="What does this code print?",
                code='word = "banana"\nprint(word[1:4])',
                answer="ana",
                grounding="String slices",
            ),
            ExampleQuestion(
                prompt="What does this code print?",
                code="total = 0\nfor n in [3, 1, 4]:\n    total = total + n\nprint(total)",
                answer="8",
                grounding="Traversing a list",
            ),
        ),
    ),
    _style(
        "py.misconception",
        "Catch a common misconception",
        "One true-or-false statement built around a mistake beginners often make.",
        QuestionType.TRUE_FALSE,
        [E],
        "True or false",
        ["boolean expressions", "return values", "variables", "mutability", "comparison"],
        (
            ExampleQuestion(
                prompt="True or false: = and == do the same thing in an if statement.",
                options=_choices(("True", False), ("False", True)),
                answer="False",
                grounding="Boolean expressions",
            ),
            ExampleQuestion(
                prompt="True or false: a function with no return statement returns None.",
                options=_choices(("True", True), ("False", False)),
                answer="True",
                grounding="Return values",
            ),
        ),
    ),
    _style(
        "py.trace_steps",
        "Trace a loop or call over several steps",
        "Students follow the values through a loop or a few calls, then give the output.",
        QuestionType.OUTPUT_PREDICTION,
        [M, H],
        _RUNS_OUTPUT,
        ["while loops", "for loops", "accumulators", "function calls", "aliasing", "recursion"],
        (
            ExampleQuestion(
                prompt="What does this code print?",
                code=(
                    "def f(n):\n    result = 1\n    while n > 1:\n        result = result * n\n"
                    "        n = n - 2\n    return result\n\nprint(f(7))"
                ),
                answer="105",
                grounding="The while statement",
            ),
            ExampleQuestion(
                prompt="What does this code print?",
                code="t = [1, 2, 3]\nu = t\nu.append(4)\nprint(len(t), t[-1])",
                answer="4 4",
                grounding="Aliasing",
            ),
        ),
    ),
    _style(
        "py.order_lines",
        "Put the lines of a short function in order",
        "Students arrange 4 to 6 lines into the right order and indentation.",
        QuestionType.PARSONS,
        [E, M],
        "Checks the order and indentation of the lines",
        ["functions", "loops", "conditionals", "counting", "searching"],
        (
            ExampleQuestion(
                prompt="Arrange the lines so count_vowels(s) returns how many vowels s has.",
                lines=[
                    "def count_vowels(s):",
                    "    count = 0",
                    "    for ch in s:",
                    "        if ch in 'aeiou':",
                    "            count = count + 1",
                    "    return count",
                ],
                grounding="Looping and counting",
            ),
            ExampleQuestion(
                prompt=(
                    "Arrange the lines so is_sorted(t) returns True when t is in ascending order."
                ),
                lines=[
                    "def is_sorted(t):",
                    "    for i in range(len(t) - 1):",
                    "        if t[i] > t[i + 1]:",
                    "            return False",
                    "    return True",
                ],
                grounding="Traversing a list",
            ),
        ),
    ),
    _style(
        "py.fix_one_bug",
        "Fix one bug in a short function",
        "The function is almost right. Students find the one wrong line and fix it.",
        QuestionType.DEBUGGING,
        [M],
        _RUNS_TESTS + " (cannot read or write files)",
        ["loops", "accumulators", "conditionals", "functions", "lists"],
        (
            ExampleQuestion(
                prompt=(
                    "average(t) should return the mean of a non-empty list, but average([2, 3]) "
                    "returns 1.5. Fix it."
                ),
                code=(
                    "def average(t):\n    total = 0\n    for x in t:\n        total = x\n"
                    "    return total / len(t)"
                ),
                answer="Line 4 should add to the running total: total = total + x",
                tests=4,
                grounding="Map, filter and reduce",
            ),
            ExampleQuestion(
                prompt="countdown(n) should print n down to 1, but it never stops. Fix it.",
                code="def countdown(n):\n    while n > 0:\n        print(n)\n    n = n - 1",
                answer="Indent n = n - 1 so it runs inside the loop",
                tests=3,
                grounding="The while statement",
            ),
        ),
    ),
    _style(
        "py.fill_missing_line",
        "Fill in the missing line",
        "A working function with the one line that carries the logic blanked out.",
        QuestionType.CODE_COMPLETION,
        [M, H],
        _RUNS_TESTS + " (cannot read or write files)",
        ["loops", "dictionaries", "recursion", "conditionals", "list building"],
        (
            ExampleQuestion(
                prompt=(
                    "Complete the function so it returns the largest value in t, "
                    "without using max()."
                ),
                code=(
                    "def largest(t):\n    best = t[0]\n    for x in t:\n        ________\n"
                    "    return best"
                ),
                answer="if x > best: best = x",
                tests=5,
                grounding="Map, filter and reduce",
            ),
            ExampleQuestion(
                prompt="Complete power(b, n) so it returns b to the power n for n >= 0.",
                code="def power(b, n):\n    if n == 0:\n        return 1\n    ________",
                answer="return b * power(b, n - 1)",
                tests=5,
                grounding="More recursion",
            ),
        ),
    ),
    _style(
        "py.write_function",
        "Write a complete function from a short spec",
        "Students write the whole function. Hidden tests give partial credit.",
        QuestionType.CODING,
        [M, H],
        _RUNS_TESTS + "; the score is tests passed out of total (cannot read or write files)",
        ["functions", "lists", "dictionaries", "strings", "recursion", "loops"],
        (
            ExampleQuestion(
                prompt=(
                    "Write has_duplicates(t) that returns True if any element appears more than "
                    "once in t. Do not change t."
                ),
                answer=(
                    "Reference: return len(set(t)) < len(t), or a loop with a dict of seen items"
                ),
                tests=6,
                grounding="Dictionary as a collection of counters",
            ),
            ExampleQuestion(
                prompt=(
                    "Write is_palindrome(word) using recursion: a word is a palindrome if its "
                    "first and last letters match and the middle is a palindrome."
                ),
                answer=(
                    "Reference: base case len(word) <= 1; else compare the ends and recurse "
                    "on word[1:-1]"
                ),
                tests=7,
                grounding="More recursion",
            ),
        ),
    ),
    _style(
        "py.subtle_output",
        "Predict output where one subtle rule decides it",
        "Scope, aliasing or mutation decides the answer. Separates tracing from guessing.",
        QuestionType.OUTPUT_PREDICTION,
        [H],
        _RUNS_OUTPUT,
        ["variable scope", "parameters", "aliasing", "mutability", "list arguments"],
        (
            ExampleQuestion(
                prompt="What does this code print?",
                code=(
                    "x = 10\n\ndef bump(x):\n    x = x + 1\n    return x\n\ny = bump(x)\n"
                    "print(x, y)"
                ),
                answer="10 11",
                grounding="Variables and parameters are local",
            ),
            ExampleQuestion(
                prompt="What does this code print?",
                code=(
                    "def chop(t):\n    t = t[1:]\n\ndef pop_first(t):\n    del t[0]\n\n"
                    "a = [1, 2, 3]\nchop(a)\npop_first(a)\nprint(a)"
                ),
                answer="[2, 3]",
                grounding="List arguments",
            ),
        ),
    ),
    _style(
        "py.edge_case_bug",
        "Find a bug that only shows on some inputs",
        "The code passes the obvious case. Students find the input that breaks it and fix it.",
        QuestionType.DEBUGGING,
        [H],
        _RUNS_TESTS + " (cannot read or write files)",
        ["searching", "base cases", "recursion", "loop bounds", "input validation"],
        (
            ExampleQuestion(
                prompt=(
                    "find_index(t, target) should return the index of target, or -1 if it is "
                    "missing. It fails one of the tests. Fix it."
                ),
                code=(
                    "def find_index(t, target):\n    for i in range(len(t)):\n"
                    "        if t[i] == target:\n            return i\n        else:\n"
                    "            return -1"
                ),
                answer="Move return -1 after the loop; it currently gives up after the first item",
                tests=6,
                grounding="Searching",
            ),
            ExampleQuestion(
                prompt=(
                    "fact(n) should return n! for every n >= 0, but it crashes for one valid "
                    "input. Fix it."
                ),
                code="def fact(n):\n    if n == 1:\n        return 1\n    return n * fact(n - 1)",
                answer=(
                    "The base case should be n == 0: fact(0) recurses until it overflows the stack"
                ),
                tests=5,
                grounding="More recursion",
            ),
        ),
    ),
]
