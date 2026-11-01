/* Wrong-rules examples for knowledge.html. Every output was computed by running the rule
 * (tools/wrong_rules.py); biology uses a book quote instead. TODO(real): written by the generator
 * with each question, and checked the same way. */
window.MOCK.wrong_rules = [
 {
  "id": "aliasing",
  "course": "python",
  "sub": "Aliasing",
  "kind": "model",
  "checker": "run",
  "qid": 1036,
  "question": "After `x = [1, 2]; y = x; y += [3]`, what is `x`?",
  "right": {
   "rule": "y = x gives the same list a second name; += changes that one list.",
   "code": "x = [1, 2]\ny = x\ny += [3]\nprint(x)",
   "output": "[1, 2, 3]"
  },
  "wrong": [
   {
    "rule": "Thinks y = x makes a copy",
    "code": "x = [1, 2]\ny = x[:]   # as if it were a copy\ny += [3]\nprint(x)",
    "feedback": "y = x doesn't copy. Both names point at one list, so changing it through y changes x too.",
    "output": "[1, 2]"
   },
   {
    "rule": "Thinks += adds the list as one item",
    "code": "x = [1, 2]\ny = x\ny.append([3])   # as if += appended\nprint(x)",
    "feedback": "+= on a list adds each item of the right-hand list, like extend, not the list itself.",
    "output": "[1, 2, [3]]"
   },
   {
    "rule": "Thinks += makes y a brand-new list",
    "code": "x = [1, 2]\ny = x\ny = [3]   # as if += replaced y\nprint(y)",
    "feedback": "+= changes the list in place. y still names the same list as x.",
    "output": "[3]"
   }
  ],
  "checks": {
   "right_unique": true,
   "wrong_distinct": true
  }
 },
 {
  "id": "range",
  "course": "python",
  "sub": "range() and counted loops",
  "kind": "procedure",
  "checker": "run",
  "qid": 1025,
  "question": "What is printed?\n\nfor i in range(3):\n    print(i * 2, end=' ')",
  "right": {
   "rule": "range(3) counts 0, 1, 2: it starts at 0 and stops before 3.",
   "code": "for i in range(3):\n    print(i * 2, end=' ')",
   "output": "0 2 4 "
  },
  "wrong": [
   {
    "rule": "Thinks range starts at 1",
    "code": "for i in range(1, 4):   # as if it started at 1\n    print(i * 2, end=' ')",
    "feedback": "With one number, range starts at 0, not 1.",
    "output": "2 4 6 "
   },
   {
    "rule": "Thinks the stop value is included",
    "code": "for i in range(4):   # as if 3 were included\n    print(i * 2, end=' ')",
    "feedback": "range stops before the stop value: range(3) never gives 3.",
    "output": "0 2 4 6 "
   }
  ],
  "checks": {
   "right_unique": true,
   "wrong_distinct": true
  }
 },
 {
  "id": "return",
  "course": "python",
  "sub": "Return values",
  "kind": "model",
  "checker": "run",
  "qid": 1021,
  "question": "What does `print(f(3))` show?\n\ndef f(x):\n    x * 2",
  "right": {
   "rule": "A function with no return gives back None.",
   "code": "def f(x):\n    x * 2\nprint(f(3))",
   "output": "None"
  },
  "wrong": [
   {
    "rule": "Thinks the last expression is returned",
    "code": "def f(x):\n    return x * 2   # as if the last line came back\nprint(f(3))",
    "feedback": "Python only returns what you return. Computing x * 2 and not returning it throws it away.",
    "output": "6"
   },
   {
    "rule": "Thinks a missing return gives 0",
    "code": "def f(x):\n    x * 2\n    return 0   # as if the default were 0\nprint(f(3))",
    "feedback": "The default return value is None, not 0.",
    "output": "0"
   }
  ],
  "checks": {
   "right_unique": true,
   "wrong_distinct": true
  }
 },
 {
  "id": "moe",
  "course": "statistics",
  "sub": "Interval for a mean",
  "kind": "procedure",
  "checker": "run",
  "qid": null,
  "question": "A sample has n = 36, x̄ = 50 and s = 12. What is the margin of error of a 95% confidence interval for the mean? Round to 2 decimals.",
  "right": {
   "rule": "t* with n − 1 = 35 degrees of freedom, times s / √n.",
   "code": "t_star = T.ppf(0.975, df=35)\nprint(round(t_star * 12 / math.sqrt(36), 2))",
   "output": "4.06"
  },
  "wrong": [
   {
    "rule": "Uses z = 1.96 instead of t",
    "code": "print(round(1.96 * 12 / math.sqrt(36), 2))   # z, as if σ were known",
    "feedback": "s comes from the sample, so the multiplier is t with 35 degrees of freedom, not z.",
    "output": "3.92"
   },
   {
    "rule": "Forgets to divide by √n",
    "code": "t_star = T.ppf(0.975, df=35)\nprint(round(t_star * 12, 2))   # as if SE were s",
    "feedback": "The standard error of the mean is s / √n. You used s itself.",
    "output": "24.36"
   },
   {
    "rule": "Divides by n instead of √n",
    "code": "t_star = T.ppf(0.975, df=35)\nprint(round(t_star * 12 / 36, 2))   # as if SE were s / n",
    "feedback": "The spread of the mean shrinks with √n, not n.",
    "output": "0.68"
   }
  ],
  "checks": {
   "right_unique": true,
   "wrong_distinct": true
  }
 },
 {
  "id": "glycolysis",
  "course": "biology",
  "sub": "Glycolysis",
  "kind": "fact",
  "checker": "lookup",
  "qid": 2021,
  "question": "True or false: glycolysis requires oxygen.",
  "right": {
   "rule": "Glycolysis runs without oxygen.",
   "quote": "Glycolysis does not use oxygen; it occurs in both aerobic and anaerobic conditions.",
   "section": "OpenStax Biology 2e · 7.2 Glycolysis",
   "output": "False"
  },
  "wrong": [
   {
    "rule": "Thinks every step of respiration needs oxygen",
    "output": "True",
    "feedback": "Only the electron transport chain needs oxygen. Glycolysis happens in the cytoplasm with or without it."
   }
  ],
  "checks": {
   "right_unique": true,
   "wrong_distinct": true
  }
 }
];
