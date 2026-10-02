/**
 * GENERATED FILE. Do not edit by hand.
 *
 * Written by `record_traces.py` (next to this file), run on Python 3.12.10. Every snippet here was
 * executed: the stepped ones under `sys.settrace` (call stack, watched variables, list `id()`s),
 * the static ones plainly. To change a snippet, edit the script and run it again.
 *
 * A step describes the state AFTER its `line` ran (`line` is null at the start). `output` is what
 * `print` has written so far, `frames` is the call stack bottom first, `heap` groups the names that
 * share one list (recorded from `id()`), and `branches` / `dim` / `check` are derived from the run.
 *
 * TODO(real): these are recorded by hand-running a script. In the product the tutorial generator
 * runs each snippet when a tutorial is built from a book section, and the traces are stored with
 * the tutorial once the professor approves it.
 */

export type Frame = { label: string; vars: Record<string, string>; ret?: string };
export type BranchState = "taken" | "false" | "skipped" | "pending";
export type Step = {
  /** 1-based line that just ran; null before anything has run. */
  line: number | null;
  kind: "start" | "line" | "call" | "return" | "back" | "end" | "cap";
  /** At most 16 words: what just happened. */
  caption: string;
  /** Call stack, bottom first. `ret` is set on a frame that is returning. */
  frames: Frame[];
  /** Lines of the frames waiting for a call to come back. */
  paused: number[];
  output: string[];
  heap?: { id: number; names: string[]; items: string[] }[];
  focus?: { obj: number; index: number };
  added?: { obj: number; index: number }[];
  branches?: { label: string; state: BranchState }[];
  dim?: number[];
  check?: { expr: string; results: boolean[] };
};
export type Prediction = {
  id: string;
  /** Asked when the student presses Step to reveal step `atStep`. */
  atStep: number;
  question: string;
  choices: string[];
  /** Index into `choices`, derived from the recording. */
  answer: number;
  why: string;
};
export type Trace = {
  id: string;
  label: string;
  view: "branches" | "while" | "stack" | "memory";
  code: string;
  /** True when the snippet never finishes and the trace stops at the step cap. */
  endless: boolean;
  takeaway: string;
  /** From an independent, untraced run of the same code. */
  expectedOutput: string[];
  predictions: Prediction[];
  steps: Step[];
};
export type Example = { code: string; output: string[]; endless: boolean };
export type Faded = {
  cond: { code: string; output: string[] };
  while: { template: string; choices: { value: string; terminates: boolean; output: string[] }[] };
  fn: {
    lines: string[];
    shuffled: number[];
    output: string[];
    /** Every ordering of the lines, run for real: `ok` when it prints the expected output. */
    orders: Record<string, { ok: boolean; text: string }>;
  };
  list: { code: string; output: string[] };
  rec: { code: string; output: string[] };
};

export const TRACES: Record<string, Trace> = {
 "cond": {
  "id": "cond",
  "label": "mark = 95",
  "view": "branches",
  "code": "mark = 95\nif mark >= 60:\n    grade = \"pass\"\nelif mark >= 90:\n    grade = \"distinction\"\nelse:\n    grade = \"fail\"\nprint(grade)",
  "endless": false,
  "takeaway": "The first true test wins. Put the strictest test first.",
  "expectedOutput": [
   "pass"
  ],
  "predictions": [
   {
    "id": "first",
    "atStep": 1,
    "question": "Which grade will print?",
    "choices": [
     "distinction",
     "pass",
     "fail"
    ],
    "answer": 1,
    "why": "The first true test wins: 95 >= 60 is True, so the elif is never tested."
   },
   {
    "id": "key",
    "atStep": 2,
    "question": "The if test is True. Does Python test the elif next?",
    "choices": [
     "Yes, it tests every branch",
     "No, it skips it"
    ],
    "answer": 1,
    "why": "Once a branch is taken, the rest of the chain is skipped."
   }
  ],
  "steps": [
   {
    "line": null,
    "kind": "start",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "branches": [
     {
      "label": "if mark >= 60",
      "state": "pending"
     },
     {
      "label": "elif mark >= 90",
      "state": "pending"
     },
     {
      "label": "else",
      "state": "pending"
     }
    ],
    "dim": [],
    "caption": "Nothing has run yet. Press Step."
   },
   {
    "line": 1,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "mark": "95"
      }
     }
    ],
    "paused": [],
    "output": [],
    "branches": [
     {
      "label": "if mark >= 60",
      "state": "pending"
     },
     {
      "label": "elif mark >= 90",
      "state": "pending"
     },
     {
      "label": "else",
      "state": "pending"
     }
    ],
    "dim": [],
    "caption": "mark is 95."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "mark": "95"
      }
     }
    ],
    "paused": [],
    "output": [],
    "branches": [
     {
      "label": "if mark >= 60",
      "state": "taken"
     },
     {
      "label": "elif mark >= 90",
      "state": "skipped"
     },
     {
      "label": "else",
      "state": "skipped"
     }
    ],
    "dim": [
     4,
     5,
     6,
     7
    ],
    "caption": "mark >= 60 is True: take this branch and skip the rest."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "mark": "95",
       "grade": "'pass'"
      }
     }
    ],
    "paused": [],
    "output": [],
    "branches": [
     {
      "label": "if mark >= 60",
      "state": "taken"
     },
     {
      "label": "elif mark >= 90",
      "state": "skipped"
     },
     {
      "label": "else",
      "state": "skipped"
     }
    ],
    "dim": [
     4,
     5,
     6,
     7
    ],
    "caption": "grade is 'pass'. Skipped branches never ran."
   },
   {
    "line": 8,
    "kind": "end",
    "frames": [
     {
      "label": "global",
      "vars": {
       "mark": "95",
       "grade": "'pass'"
      }
     }
    ],
    "paused": [],
    "output": [
     "pass"
    ],
    "branches": [
     {
      "label": "if mark >= 60",
      "state": "taken"
     },
     {
      "label": "elif mark >= 90",
      "state": "skipped"
     },
     {
      "label": "else",
      "state": "skipped"
     }
    ],
    "dim": [
     4,
     5,
     6,
     7
    ],
    "caption": "print shows pass."
   }
  ]
 },
 "while-ends": {
  "id": "while-ends",
  "label": "Countdown",
  "view": "while",
  "code": "n = 3\nwhile n > 0:\n    print(n)\n    n = n - 1",
  "endless": false,
  "takeaway": "The test runs before every pass. When it is False, the loop ends.",
  "expectedOutput": [
   "3",
   "2",
   "1"
  ],
  "predictions": [
   {
    "id": "first",
    "atStep": 1,
    "question": "What will this print?",
    "choices": [
     "3 2 1",
     "3 2 1 0",
     "2 1 0"
    ],
    "answer": 0,
    "why": "n stops the loop at 0, and 0 > 0 is False, so 0 is never printed."
   },
   {
    "id": "key",
    "atStep": 11,
    "question": "n is 0 now. What happens at the while line?",
    "choices": [
     "The body runs once more",
     "The loop ends"
    ],
    "answer": 1,
    "why": "0 > 0 is False, so Python leaves the loop."
   }
  ],
  "steps": [
   {
    "line": null,
    "kind": "start",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "check": {
     "expr": "n > 0",
     "results": []
    },
    "caption": "Nothing has run yet. Press Step."
   },
   {
    "line": 1,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "3"
      }
     }
    ],
    "paused": [],
    "output": [],
    "check": {
     "expr": "n > 0",
     "results": []
    },
    "caption": "n is 3."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "3"
      }
     }
    ],
    "paused": [],
    "output": [],
    "check": {
     "expr": "n > 0",
     "results": [
      true
     ]
    },
    "caption": "n > 0 is True: run the body."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "3"
      }
     }
    ],
    "paused": [],
    "output": [
     "3"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true
     ]
    },
    "caption": "print shows 3."
   },
   {
    "line": 4,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "2"
      }
     }
    ],
    "paused": [],
    "output": [
     "3"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true
     ]
    },
    "caption": "n was 3, now 2."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "2"
      }
     }
    ],
    "paused": [],
    "output": [
     "3"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true,
      true
     ]
    },
    "caption": "n > 0 is True: run the body."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "2"
      }
     }
    ],
    "paused": [],
    "output": [
     "3",
     "2"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true,
      true
     ]
    },
    "caption": "print shows 2."
   },
   {
    "line": 4,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "1"
      }
     }
    ],
    "paused": [],
    "output": [
     "3",
     "2"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true,
      true
     ]
    },
    "caption": "n was 2, now 1."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "1"
      }
     }
    ],
    "paused": [],
    "output": [
     "3",
     "2"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true,
      true,
      true
     ]
    },
    "caption": "n > 0 is True: run the body."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "1"
      }
     }
    ],
    "paused": [],
    "output": [
     "3",
     "2",
     "1"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true,
      true,
      true
     ]
    },
    "caption": "print shows 1."
   },
   {
    "line": 4,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "3",
     "2",
     "1"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true,
      true,
      true
     ]
    },
    "caption": "n was 1, now 0."
   },
   {
    "line": 2,
    "kind": "end",
    "frames": [
     {
      "label": "global",
      "vars": {
       "n": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "3",
     "2",
     "1"
    ],
    "check": {
     "expr": "n > 0",
     "results": [
      true,
      true,
      true,
      false
     ]
    },
    "caption": "n > 0 is False: the loop ends."
   }
  ]
 },
 "while-stuck": {
  "id": "while-stuck",
  "label": "Stuck loop",
  "view": "while",
  "code": "count = 0\nwhile count < 3:\n    print(\"tick\")",
  "endless": true,
  "takeaway": "Nothing changes count, so the test never turns False.",
  "expectedOutput": [
   "tick",
   "tick",
   "tick",
   "tick"
  ],
  "predictions": [
   {
    "id": "first",
    "atStep": 1,
    "question": "How many times will tick print?",
    "choices": [
     "Three times",
     "Never",
     "Forever"
    ],
    "answer": 2,
    "why": "count stays 0, so count < 3 is True every time."
   },
   {
    "id": "key",
    "atStep": 4,
    "question": "The body ran once. count is still 0. Is the test True again?",
    "choices": [
     "Yes, nothing changed count",
     "No, it already ran"
    ],
    "answer": 0,
    "why": "The test only looks at count, and nothing inside the loop changes it."
   }
  ],
  "steps": [
   {
    "line": null,
    "kind": "start",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "check": {
     "expr": "count < 3",
     "results": []
    },
    "caption": "Nothing has run yet. Press Step."
   },
   {
    "line": 1,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [],
    "check": {
     "expr": "count < 3",
     "results": []
    },
    "caption": "count is 0."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [],
    "check": {
     "expr": "count < 3",
     "results": [
      true
     ]
    },
    "caption": "count < 3 is True: run the body."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "tick"
    ],
    "check": {
     "expr": "count < 3",
     "results": [
      true
     ]
    },
    "caption": "print shows tick."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "tick"
    ],
    "check": {
     "expr": "count < 3",
     "results": [
      true,
      true
     ]
    },
    "caption": "count < 3 is True: run the body."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "tick",
     "tick"
    ],
    "check": {
     "expr": "count < 3",
     "results": [
      true,
      true
     ]
    },
    "caption": "print shows tick."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "tick",
     "tick"
    ],
    "check": {
     "expr": "count < 3",
     "results": [
      true,
      true,
      true
     ]
    },
    "caption": "count < 3 is True: run the body."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "tick",
     "tick",
     "tick"
    ],
    "check": {
     "expr": "count < 3",
     "results": [
      true,
      true,
      true
     ]
    },
    "caption": "print shows tick."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "tick",
     "tick",
     "tick"
    ],
    "check": {
     "expr": "count < 3",
     "results": [
      true,
      true,
      true,
      true
     ]
    },
    "caption": "count < 3 is True: run the body."
   },
   {
    "line": 3,
    "kind": "cap",
    "frames": [
     {
      "label": "global",
      "vars": {
       "count": "0"
      }
     }
    ],
    "paused": [],
    "output": [
     "tick",
     "tick",
     "tick",
     "tick"
    ],
    "check": {
     "expr": "count < 3",
     "results": [
      true,
      true,
      true,
      true
     ]
    },
    "caption": "Stopped after 9 steps. count is still 0: this would go on forever."
   }
  ]
 },
 "fn-return": {
  "id": "fn-return",
  "label": "Returns a value",
  "view": "stack",
  "code": "def add(a, b):\n    total = a + b\n    return total\nresult = add(2, 3)\nprint(result)",
  "endless": false,
  "takeaway": "return hands the value back to the caller.",
  "expectedOutput": [
   "5"
  ],
  "predictions": [
   {
    "id": "first",
    "atStep": 1,
    "question": "What will this print?",
    "choices": [
     "5",
     "None",
     "Nothing"
    ],
    "answer": 0,
    "why": "add returns total, and result keeps it."
   },
   {
    "id": "key",
    "atStep": 4,
    "question": "What will add give back to its caller?",
    "choices": [
     "5",
     "None"
    ],
    "answer": 0,
    "why": "return total sends total's value back."
   }
  ],
  "steps": [
   {
    "line": null,
    "kind": "start",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "caption": "Nothing has run yet. Press Step."
   },
   {
    "line": 1,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "caption": "Python stores add. Nothing runs yet."
   },
   {
    "line": 1,
    "kind": "call",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "add(2, 3)",
      "vars": {
       "a": "2",
       "b": "3"
      }
     }
    ],
    "paused": [
     4
    ],
    "output": [],
    "caption": "Call: Python jumps into add. a is 2, b is 3."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "add(2, 3)",
      "vars": {
       "a": "2",
       "b": "3",
       "total": "5"
      }
     }
    ],
    "paused": [
     4
    ],
    "output": [],
    "caption": "total is 5."
   },
   {
    "line": 3,
    "kind": "return",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "add(2, 3)",
      "vars": {
       "a": "2",
       "b": "3",
       "total": "5"
      },
      "ret": "5"
     }
    ],
    "paused": [
     4
    ],
    "output": [],
    "caption": "return sends 5 back to the caller."
   },
   {
    "line": 4,
    "kind": "back",
    "frames": [
     {
      "label": "global",
      "vars": {
       "result": "5"
      }
     }
    ],
    "paused": [],
    "output": [],
    "caption": "5 comes back: result is 5."
   },
   {
    "line": 5,
    "kind": "end",
    "frames": [
     {
      "label": "global",
      "vars": {
       "result": "5"
      }
     }
    ],
    "paused": [],
    "output": [
     "5"
    ],
    "caption": "print shows 5."
   }
  ]
 },
 "fn-print": {
  "id": "fn-print",
  "label": "Only prints",
  "view": "stack",
  "code": "def add(a, b):\n    print(a + b)\nresult = add(2, 3)\nprint(result)",
  "endless": false,
  "takeaway": "print shows a value. Without return, the call gives back None.",
  "expectedOutput": [
   "5",
   "None"
  ],
  "predictions": [
   {
    "id": "first",
    "atStep": 1,
    "question": "What will the two prints show?",
    "choices": [
     "5 then 5",
     "5 then None",
     "Only 5"
    ],
    "answer": 1,
    "why": "add prints 5 but returns nothing, so result is None."
   },
   {
    "id": "key",
    "atStep": 3,
    "question": "What will add give back to its caller?",
    "choices": [
     "5",
     "None"
    ],
    "answer": 1,
    "why": "No return line means the call gives back None."
   }
  ],
  "steps": [
   {
    "line": null,
    "kind": "start",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "caption": "Nothing has run yet. Press Step."
   },
   {
    "line": 1,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "caption": "Python stores add. Nothing runs yet."
   },
   {
    "line": 1,
    "kind": "call",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "add(2, 3)",
      "vars": {
       "a": "2",
       "b": "3"
      }
     }
    ],
    "paused": [
     3
    ],
    "output": [],
    "caption": "Call: Python jumps into add. a is 2, b is 3."
   },
   {
    "line": 2,
    "kind": "return",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "add(2, 3)",
      "vars": {
       "a": "2",
       "b": "3"
      },
      "ret": "None"
     }
    ],
    "paused": [
     3
    ],
    "output": [
     "5"
    ],
    "caption": "print shows 5. add has no return, so it gives back None."
   },
   {
    "line": 3,
    "kind": "back",
    "frames": [
     {
      "label": "global",
      "vars": {
       "result": "None"
      }
     }
    ],
    "paused": [],
    "output": [
     "5"
    ],
    "caption": "None comes back: result is None."
   },
   {
    "line": 4,
    "kind": "end",
    "frames": [
     {
      "label": "global",
      "vars": {
       "result": "None"
      }
     }
    ],
    "paused": [],
    "output": [
     "5",
     "None"
    ],
    "caption": "print shows None."
   }
  ]
 },
 "list-alias": {
  "id": "list-alias",
  "label": "Two names",
  "view": "memory",
  "code": "a = [10, 20, 30]\nprint(a[0])\nprint(a[-1])\nb = a\nb.append(40)\nprint(a)",
  "endless": false,
  "takeaway": "b = a copies the name, not the list. Both names see every change.",
  "expectedOutput": [
   "10",
   "30",
   "[10, 20, 30, 40]"
  ],
  "predictions": [
   {
    "id": "first",
    "atStep": 1,
    "question": "What will print(a[-1]) show?",
    "choices": [
     "30",
     "10",
     "An error"
    ],
    "answer": 0,
    "why": "Index -1 counts from the end: the last item."
   },
   {
    "id": "key",
    "atStep": 6,
    "question": "b.append(40) has run. What will print(a) show?",
    "choices": [
     "[10, 20, 30]",
     "[10, 20, 30, 40]"
    ],
    "answer": 1,
    "why": "a and b are the same list, so a sees the 40 too."
   }
  ],
  "steps": [
   {
    "line": null,
    "kind": "start",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "heap": [],
    "added": [],
    "caption": "Nothing has run yet. Press Step."
   },
   {
    "line": 1,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "a": "[10, 20, 30]"
      }
     }
    ],
    "paused": [],
    "output": [],
    "heap": [
     {
      "id": 1,
      "names": [
       "a"
      ],
      "items": [
       "10",
       "20",
       "30"
      ]
     }
    ],
    "added": [],
    "caption": "a points at a new list of 3 items."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "a": "[10, 20, 30]"
      }
     }
    ],
    "paused": [],
    "output": [
     "10"
    ],
    "heap": [
     {
      "id": 1,
      "names": [
       "a"
      ],
      "items": [
       "10",
       "20",
       "30"
      ]
     }
    ],
    "focus": {
     "obj": 1,
     "index": 0
    },
    "added": [],
    "caption": "a[0] counts from 0: print shows 10."
   },
   {
    "line": 3,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "a": "[10, 20, 30]"
      }
     }
    ],
    "paused": [],
    "output": [
     "10",
     "30"
    ],
    "heap": [
     {
      "id": 1,
      "names": [
       "a"
      ],
      "items": [
       "10",
       "20",
       "30"
      ]
     }
    ],
    "focus": {
     "obj": 1,
     "index": 2
    },
    "added": [],
    "caption": "a[-1] counts from the end: print shows 30."
   },
   {
    "line": 4,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "a": "[10, 20, 30]",
       "b": "[10, 20, 30]"
      }
     }
    ],
    "paused": [],
    "output": [
     "10",
     "30"
    ],
    "heap": [
     {
      "id": 1,
      "names": [
       "a",
       "b"
      ],
      "items": [
       "10",
       "20",
       "30"
      ]
     }
    ],
    "added": [],
    "caption": "b = a makes no copy. Two names, one list."
   },
   {
    "line": 5,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {
       "a": "[10, 20, 30, 40]",
       "b": "[10, 20, 30, 40]"
      }
     }
    ],
    "paused": [],
    "output": [
     "10",
     "30"
    ],
    "heap": [
     {
      "id": 1,
      "names": [
       "a",
       "b"
      ],
      "items": [
       "10",
       "20",
       "30",
       "40"
      ]
     }
    ],
    "added": [
     {
      "obj": 1,
      "index": 3
     }
    ],
    "caption": "append adds 40. a and b are one list: both grow."
   },
   {
    "line": 6,
    "kind": "end",
    "frames": [
     {
      "label": "global",
      "vars": {
       "a": "[10, 20, 30, 40]",
       "b": "[10, 20, 30, 40]"
      }
     }
    ],
    "paused": [],
    "output": [
     "10",
     "30",
     "[10, 20, 30, 40]"
    ],
    "heap": [
     {
      "id": 1,
      "names": [
       "a",
       "b"
      ],
      "items": [
       "10",
       "20",
       "30",
       "40"
      ]
     }
    ],
    "added": [],
    "caption": "print shows [10, 20, 30, 40]."
   }
  ]
 },
 "rec-fact": {
  "id": "rec-fact",
  "label": "factorial(3)",
  "view": "stack",
  "code": "def factorial(n):\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\nprint(factorial(3))",
  "endless": false,
  "takeaway": "Each call has its own n. Answers flow back as the stack unwinds.",
  "expectedOutput": [
   "6"
  ],
  "predictions": [
   {
    "id": "first",
    "atStep": 1,
    "question": "What will this print?",
    "choices": [
     "3",
     "6",
     "9"
    ],
    "answer": 1,
    "why": "3 * 2 * 1 is 6."
   },
   {
    "id": "key",
    "atStep": 9,
    "question": "factorial(1) gave back 1. What does factorial(2) give back?",
    "choices": [
     "1",
     "2",
     "3"
    ],
    "answer": 1,
    "why": "factorial(2) is 2 * factorial(1), which is 2 * 1."
   }
  ],
  "steps": [
   {
    "line": null,
    "kind": "start",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "caption": "Nothing has run yet. Press Step."
   },
   {
    "line": 1,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [],
    "caption": "Python stores factorial. Nothing runs yet."
   },
   {
    "line": 1,
    "kind": "call",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     }
    ],
    "paused": [
     5
    ],
    "output": [],
    "caption": "Call: Python jumps into factorial. n is 3."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     }
    ],
    "paused": [
     5
    ],
    "output": [],
    "caption": "n is 3. n == 1 is False. Keep going."
   },
   {
    "line": 1,
    "kind": "call",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     },
     {
      "label": "factorial(2)",
      "vars": {
       "n": "2"
      }
     }
    ],
    "paused": [
     5,
     4
    ],
    "output": [],
    "caption": "factorial(3) calls factorial(2). New frame: n is 2."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     },
     {
      "label": "factorial(2)",
      "vars": {
       "n": "2"
      }
     }
    ],
    "paused": [
     5,
     4
    ],
    "output": [],
    "caption": "n is 2. n == 1 is False. Keep going."
   },
   {
    "line": 1,
    "kind": "call",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     },
     {
      "label": "factorial(2)",
      "vars": {
       "n": "2"
      }
     },
     {
      "label": "factorial(1)",
      "vars": {
       "n": "1"
      }
     }
    ],
    "paused": [
     5,
     4,
     4
    ],
    "output": [],
    "caption": "factorial(2) calls factorial(1). New frame: n is 1."
   },
   {
    "line": 2,
    "kind": "line",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     },
     {
      "label": "factorial(2)",
      "vars": {
       "n": "2"
      }
     },
     {
      "label": "factorial(1)",
      "vars": {
       "n": "1"
      }
     }
    ],
    "paused": [
     5,
     4,
     4
    ],
    "output": [],
    "caption": "n is 1. n == 1 is True. Base case."
   },
   {
    "line": 3,
    "kind": "return",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     },
     {
      "label": "factorial(2)",
      "vars": {
       "n": "2"
      }
     },
     {
      "label": "factorial(1)",
      "vars": {
       "n": "1"
      },
      "ret": "1"
     }
    ],
    "paused": [
     5,
     4,
     4
    ],
    "output": [],
    "caption": "Base case: factorial(1) returns 1."
   },
   {
    "line": 4,
    "kind": "return",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      }
     },
     {
      "label": "factorial(2)",
      "vars": {
       "n": "2"
      },
      "ret": "2"
     }
    ],
    "paused": [
     5,
     4
    ],
    "output": [],
    "caption": "1 came back. 2 * 1 = 2, so factorial(2) returns 2."
   },
   {
    "line": 4,
    "kind": "return",
    "frames": [
     {
      "label": "global",
      "vars": {}
     },
     {
      "label": "factorial(3)",
      "vars": {
       "n": "3"
      },
      "ret": "6"
     }
    ],
    "paused": [
     5
    ],
    "output": [],
    "caption": "2 came back. 3 * 2 = 6, so factorial(3) returns 6."
   },
   {
    "line": 5,
    "kind": "end",
    "frames": [
     {
      "label": "global",
      "vars": {}
     }
    ],
    "paused": [],
    "output": [
     "6"
    ],
    "caption": "6 comes back, and print shows 6."
   }
  ]
 }
};

export const EXAMPLES: Record<string, Example> = {
 "if-basic": {
  "code": "mark = 72\nif mark >= 60:\n    print(\"pass\")\nelse:\n    print(\"fail\")",
  "output": [
   "pass"
  ],
  "endless": false
 },
 "elif-chain": {
  "code": "mark = 72\nif mark >= 90:\n    grade = \"A\"\nelif mark >= 60:\n    grade = \"B\"\nelse:\n    grade = \"C\"\nprint(grade)",
  "output": [
   "B"
  ],
  "endless": false
 },
 "elif-fixed": {
  "code": "mark = 95\nif mark >= 90:\n    grade = \"distinction\"\nelif mark >= 60:\n    grade = \"pass\"\nelse:\n    grade = \"fail\"\nprint(grade)",
  "output": [
   "distinction"
  ],
  "endless": false
 },
 "while-countdown": {
  "code": "n = 3\nwhile n > 0:\n    print(n)\n    n = n - 1",
  "output": [
   "3",
   "2",
   "1"
  ],
  "endless": false
 },
 "while-stuck": {
  "code": "count = 0\nwhile count < 3:\n    print(\"tick\")",
  "output": [
   "tick",
   "tick",
   "tick"
  ],
  "endless": true
 },
 "while-fixed": {
  "code": "count = 0\nwhile count < 3:\n    print(\"tick\")\n    count = count + 1",
  "output": [
   "tick",
   "tick",
   "tick"
  ],
  "endless": false
 },
 "fn-greet": {
  "code": "def greet(name):\n    return \"Hi \" + name\nprint(greet(\"Ada\"))",
  "output": [
   "Hi Ada"
  ],
  "endless": false
 },
 "fn-square": {
  "code": "def square(x):\n    return x * x\ny = square(4)\nprint(y)",
  "output": [
   "16"
  ],
  "endless": false
 },
 "fn-worked": {
  "code": "def total_price(price, qty):\n    return price * qty\ncost = total_price(4, 3)\nprint(cost)",
  "output": [
   "12"
  ],
  "endless": false
 },
 "list-index": {
  "code": "a = [10, 20, 30]\nprint(a[0])\nprint(a[-1])",
  "output": [
   "10",
   "30"
  ],
  "endless": false
 },
 "list-append": {
  "code": "a = [10, 20, 30]\na.append(40)\nprint(a)\nprint(len(a))",
  "output": [
   "[10, 20, 30, 40]",
   "4"
  ],
  "endless": false
 },
 "list-copy": {
  "code": "a = [10, 20, 30]\nb = a.copy()\nb.append(40)\nprint(a)",
  "output": [
   "[10, 20, 30]"
  ],
  "endless": false
 },
 "rec-countdown": {
  "code": "def countdown(n):\n    if n == 0:\n        return\n    print(n)\n    countdown(n - 1)\ncountdown(2)",
  "output": [
   "2",
   "1"
  ],
  "endless": false
 },
 "rec-unwind": {
  "code": "def factorial(n):\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\nprint(factorial(1))\nprint(factorial(2))\nprint(factorial(3))",
  "output": [
   "1",
   "2",
   "6"
  ],
  "endless": false
 }
};

export const FADED: Faded = {
 "cond": {
  "code": "mark = 65\nif mark >= 90:\n    grade = \"distinction\"\nelif mark >= 60:\n    grade = \"pass\"\nelse:\n    grade = \"fail\"\nprint(grade)",
  "output": [
   "pass"
  ]
 },
 "while": {
  "template": "total = 0\ni = 1\nwhile i <= 3:\n    total = total + i\n    ____\nprint(total)",
  "choices": [
   {
    "value": "i = i + 1",
    "terminates": true,
    "output": [
     "6"
    ]
   },
   {
    "value": "i = 1",
    "terminates": false,
    "output": []
   },
   {
    "value": "total = 0",
    "terminates": false,
    "output": []
   }
  ]
 },
 "fn": {
  "lines": [
   "def area(w, h):",
   "    return w * h",
   "a = area(3, 5)",
   "print(a)"
  ],
  "shuffled": [
   2,
   3,
   1,
   0
  ],
  "output": [
   "15"
  ],
  "orders": {
   "0,1,2,3": {
    "ok": true,
    "text": "Prints 15."
   },
   "0,1,3,2": {
    "ok": false,
    "text": "NameError: name 'a' is not defined."
   },
   "0,2,1,3": {
    "ok": false,
    "text": "IndentationError: expected an indented block after function definition on line 1."
   },
   "0,2,3,1": {
    "ok": false,
    "text": "IndentationError: expected an indented block after function definition on line 1."
   },
   "0,3,1,2": {
    "ok": false,
    "text": "IndentationError: expected an indented block after function definition on line 1."
   },
   "0,3,2,1": {
    "ok": false,
    "text": "IndentationError: expected an indented block after function definition on line 1."
   },
   "1,0,2,3": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "1,0,3,2": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "1,2,0,3": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "1,2,3,0": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "1,3,0,2": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "1,3,2,0": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "2,0,1,3": {
    "ok": false,
    "text": "NameError: name 'area' is not defined."
   },
   "2,0,3,1": {
    "ok": false,
    "text": "IndentationError: expected an indented block after function definition on line 2."
   },
   "2,1,0,3": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "2,1,3,0": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "2,3,0,1": {
    "ok": false,
    "text": "NameError: name 'area' is not defined."
   },
   "2,3,1,0": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "3,0,1,2": {
    "ok": false,
    "text": "NameError: name 'a' is not defined."
   },
   "3,0,2,1": {
    "ok": false,
    "text": "IndentationError: expected an indented block after function definition on line 2."
   },
   "3,1,0,2": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "3,1,2,0": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   },
   "3,2,0,1": {
    "ok": false,
    "text": "NameError: name 'a' is not defined."
   },
   "3,2,1,0": {
    "ok": false,
    "text": "IndentationError: unexpected indent."
   }
  }
 },
 "list": {
  "code": "a = [1, 2]\nb = a\nb.append(3)\nprint(a)",
  "output": [
   "[1, 2, 3]"
  ]
 },
 "rec": {
  "code": "def factorial(n):\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\nprint(factorial(4))",
  "output": [
   "24"
  ]
 }
};
