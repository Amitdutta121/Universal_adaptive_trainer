/**
 * The Intro Python style library, generated from `styles/intro_python/*.yaml` in
 * `order.txt` order. Regenerate rather than edit by hand.
 */

import type { LibraryStyle } from "./setup-model";

export const PYTHON_LIBRARY: readonly LibraryStyle[] = [
  {
    id: "py.concept_check",
    name: "Check one concept on a tiny snippet",
    summary: "Students read one or two lines and pick what is true about them.",
    questionType: "multiple_choice",
    difficulties: ["easy", "medium"],
    checkedBy: "One correct option out of four",
    appliesTo: [
      "data types",
      "operators",
      "expressions",
      "strings",
      "lists",
      "dictionaries",
      "tuples",
    ],
    examples: [
      {
        prompt: "After this line runs, what is the type of x?",
        code: "x = 7 / 2",
        options: [
          {
            text: "int",
          },
          {
            text: "float",
            correct: true,
          },
          {
            text: "str",
          },
          {
            text: "It raises an error",
          },
        ],
        answer: "float",
        grounding: "Expressions and statements",
      },
      {
        prompt: "What does this expression evaluate to?",
        code: "'abc' * 2",
        options: [
          {
            text: "'abcabc'",
            correct: true,
          },
          {
            text: "'aabbcc'",
          },
          {
            text: "'abc2'",
          },
          {
            text: "TypeError",
          },
        ],
        answer: "'abcabc'",
        grounding: "String operations",
      },
    ],
  },
  {
    id: "py.predict_output",
    name: "Predict the output of a short snippet",
    summary: "Students read up to five lines and type exactly what is printed.",
    questionType: "output_prediction",
    difficulties: ["easy"],
    checkedBy: "Runs the code when the question is made and compares the exact output",
    appliesTo: ["print", "strings", "slicing", "indexing", "for loops", "arithmetic"],
    examples: [
      {
        prompt: "What does this code print?",
        code: 'word = "banana"\nprint(word[1:4])',
        answer: "ana",
        grounding: "String slices",
      },
      {
        prompt: "What does this code print?",
        code: "total = 0\nfor n in [3, 1, 4]:\n    total = total + n\nprint(total)",
        answer: "8",
        grounding: "Traversing a list",
      },
    ],
  },
  {
    id: "py.misconception",
    name: "Catch a common misconception",
    summary: "One true-or-false statement built around a mistake beginners often make.",
    questionType: "true_false",
    difficulties: ["easy"],
    checkedBy: "True or false",
    appliesTo: ["boolean expressions", "return values", "variables", "mutability", "comparison"],
    examples: [
      {
        prompt: "True or false: = and == do the same thing in an if statement.",
        options: [
          {
            text: "True",
          },
          {
            text: "False",
            correct: true,
          },
        ],
        answer: "False",
        grounding: "Boolean expressions",
      },
      {
        prompt: "True or false: a function with no return statement returns None.",
        options: [
          {
            text: "True",
            correct: true,
          },
          {
            text: "False",
          },
        ],
        answer: "True",
        grounding: "Return values",
      },
    ],
  },
  {
    id: "py.trace_steps",
    name: "Trace a loop or call over several steps",
    summary: "Students follow the values through a loop or a few calls, then give the output.",
    questionType: "output_prediction",
    difficulties: ["medium", "hard"],
    checkedBy: "Runs the code when the question is made and compares the exact output",
    appliesTo: [
      "while loops",
      "for loops",
      "accumulators",
      "function calls",
      "aliasing",
      "recursion",
    ],
    examples: [
      {
        prompt: "What does this code print?",
        code: "def f(n):\n    result = 1\n    while n > 1:\n        result = result * n\n        n = n - 2\n    return result\n\nprint(f(7))",
        answer: "105",
        grounding: "The while statement",
      },
      {
        prompt: "What does this code print?",
        code: "t = [1, 2, 3]\nu = t\nu.append(4)\nprint(len(t), t[-1])",
        answer: "4 4",
        grounding: "Aliasing",
      },
    ],
  },
  {
    id: "py.order_lines",
    name: "Put the lines of a short function in order",
    summary: "Students arrange 4 to 6 lines into the right order and indentation.",
    questionType: "parsons",
    difficulties: ["easy", "medium"],
    checkedBy: "Checks the order and indentation of the lines",
    appliesTo: ["functions", "loops", "conditionals", "counting", "searching"],
    examples: [
      {
        prompt: "Arrange the lines so count_vowels(s) returns how many vowels s has.",
        lines: [
          "def count_vowels(s):",
          "    count = 0",
          "    for ch in s:",
          "        if ch in 'aeiou':",
          "            count = count + 1",
          "    return count",
        ],
        grounding: "Looping and counting",
      },
      {
        prompt: "Arrange the lines so is_sorted(t) returns True when t is in ascending order.",
        lines: [
          "def is_sorted(t):",
          "    for i in range(len(t) - 1):",
          "        if t[i] > t[i + 1]:",
          "            return False",
          "    return True",
        ],
        grounding: "Traversing a list",
      },
    ],
  },
  {
    id: "py.fix_one_bug",
    name: "Fix one bug in a short function",
    summary: "The function is almost right. Students find the one wrong line and fix it.",
    questionType: "debugging",
    difficulties: ["medium"],
    checkedBy: "Runs hidden tests on the student's code (cannot read or write files)",
    appliesTo: ["loops", "accumulators", "conditionals", "functions", "lists"],
    examples: [
      {
        prompt:
          "average(t) should return the mean of a non-empty list, but average([2, 3]) returns 1.5. Fix it.",
        code: "def average(t):\n    total = 0\n    for x in t:\n        total = x\n    return total / len(t)",
        answer: "Line 4 should add to the running total: total = total + x",
        tests: 4,
        grounding: "Map, filter and reduce",
      },
      {
        prompt: "countdown(n) should print n down to 1, but it never stops. Fix it.",
        code: "def countdown(n):\n    while n > 0:\n        print(n)\n    n = n - 1",
        answer: "Indent n = n - 1 so it runs inside the loop",
        tests: 3,
        grounding: "The while statement",
      },
    ],
  },
  {
    id: "py.fill_missing_line",
    name: "Fill in the missing line",
    summary: "A working function with the one line that carries the logic blanked out.",
    questionType: "code_completion",
    difficulties: ["medium", "hard"],
    checkedBy: "Runs hidden tests on the student's code (cannot read or write files)",
    appliesTo: ["loops", "dictionaries", "recursion", "conditionals", "list building"],
    examples: [
      {
        prompt: "Complete the function so it returns the largest value in t, without using max().",
        code: "def largest(t):\n    best = t[0]\n    for x in t:\n        ________\n    return best",
        answer: "if x > best: best = x",
        tests: 5,
        grounding: "Map, filter and reduce",
      },
      {
        prompt: "Complete power(b, n) so it returns b to the power n for n >= 0.",
        code: "def power(b, n):\n    if n == 0:\n        return 1\n    ________",
        answer: "return b * power(b, n - 1)",
        tests: 5,
        grounding: "More recursion",
      },
    ],
  },
  {
    id: "py.write_function",
    name: "Write a complete function from a short spec",
    summary: "Students write the whole function. Hidden tests give partial credit.",
    questionType: "coding",
    difficulties: ["medium", "hard"],
    checkedBy:
      "Runs hidden tests on the student's code; the score is tests passed out of total (cannot read or write files)",
    appliesTo: ["functions", "lists", "dictionaries", "strings", "recursion", "loops"],
    examples: [
      {
        prompt:
          "Write has_duplicates(t) that returns True if any element appears more than once in t. Do not change t.",
        answer: "Reference: return len(set(t)) < len(t), or a loop with a dict of seen items",
        tests: 6,
        grounding: "Dictionary as a collection of counters",
      },
      {
        prompt:
          "Write is_palindrome(word) using recursion: a word is a palindrome if its first and last letters match and the middle is a palindrome.",
        answer:
          "Reference: base case len(word) <= 1; else compare the ends and recurse on word[1:-1]",
        tests: 7,
        grounding: "More recursion",
      },
    ],
  },
  {
    id: "py.subtle_output",
    name: "Predict output where one subtle rule decides it",
    summary: "Scope, aliasing or mutation decides the answer. Separates tracing from guessing.",
    questionType: "output_prediction",
    difficulties: ["hard"],
    checkedBy: "Runs the code when the question is made and compares the exact output",
    appliesTo: ["variable scope", "parameters", "aliasing", "mutability", "list arguments"],
    examples: [
      {
        prompt: "What does this code print?",
        code: "x = 10\n\ndef bump(x):\n    x = x + 1\n    return x\n\ny = bump(x)\nprint(x, y)",
        answer: "10 11",
        grounding: "Variables and parameters are local",
      },
      {
        prompt: "What does this code print?",
        code: "def chop(t):\n    t = t[1:]\n\ndef pop_first(t):\n    del t[0]\n\na = [1, 2, 3]\nchop(a)\npop_first(a)\nprint(a)",
        answer: "[2, 3]",
        grounding: "List arguments",
      },
    ],
  },
  {
    id: "py.edge_case_bug",
    name: "Find a bug that only shows on some inputs",
    summary: "The code passes the obvious case. Students find the input that breaks it and fix it.",
    questionType: "debugging",
    difficulties: ["hard"],
    checkedBy: "Runs hidden tests on the student's code (cannot read or write files)",
    appliesTo: ["searching", "base cases", "recursion", "loop bounds", "input validation"],
    examples: [
      {
        prompt:
          "find_index(t, target) should return the index of target, or -1 if it is missing. It fails one of the tests. Fix it.",
        code: "def find_index(t, target):\n    for i in range(len(t)):\n        if t[i] == target:\n            return i\n        else:\n            return -1",
        answer: "Move return -1 after the loop; it currently gives up after the first item",
        tests: 6,
        grounding: "Searching",
      },
      {
        prompt:
          "fact(n) should return n! for every n >= 0, but it crashes for one valid input. Fix it.",
        code: "def fact(n):\n    if n == 1:\n        return 1\n    return n * fact(n - 1)",
        answer: "The base case should be n == 0: fact(0) recurses until it overflows the stack",
        tests: 5,
        grounding: "More recursion",
      },
    ],
  },
];
