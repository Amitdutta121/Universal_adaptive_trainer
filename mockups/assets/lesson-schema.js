/*
 * Lesson block contract shared by the lesson editor (lesson.html) and the student lesson player.
 * A lesson is a Plate value: an array of block nodes, each { type, ...fields, children: [{ text }] }.
 * Text blocks keep their text in children; the rest are void blocks with their data in fields.
 *
 *   h2        title (text)
 *   explain   explanation (text)
 *   mistake   the common mistake (text)
 *   example   { code, output, source }                       runnable worked example
 *   predict   { code, question, answer }                     student guesses the output first
 *   check     { question, options, answer, question_id }      MC question from the approved bank
 * New, richer blocks:
 *   trace     { code, steps: [{ line, names, heap, out }], caption }
 *             line = the line about to run (null = finished); names: { name: {value} | {ref: "o1"} };
 *             heap: { o1: { type, value } }; out = printed so far. Recorded by running the code.
 *   memory    { code, names, heap, caption }                  names-to-objects diagram (one snapshot)
 *   branch    { question, options, answer, remediation: { "<wrong option index>": { text, show? } }, misconception }
 *             a question whose wrong answers each get targeted feedback; show = "memory" | "explore" | "trace"
 *   fill      { code (with ____), answers: [accepted], hint }  fill in the blank, checked by matching
 *   parsons   { prompt, lines: [in order], distractors: [lines], output }   put the lines in order
 *   explore   { kind: "range", start, stop, step, caption }   explorable: sliders + number line
 *   recap     { points: [text] }                               three-line summary
 * TODO(real): the generator writes these; traces are recorded by running the code in the sandbox.
 */
(function () {
  const M = window.MOCK;
  M.RICH_LESSONS = {
 "Aliasing": [
  {
   "type": "h2",
   "children": [
    {
     "text": "Aliasing"
    }
   ]
  },
  {
   "type": "predict",
   "code": "groceries = ['eggs', 'milk']\nshared = groceries\nshared.append('bread')\nprint(groceries)",
   "question": "What does this print?",
   "answer": "['eggs', 'milk', 'bread']",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "explain",
   "children": [
    {
     "text": "shared = groceries gives your list a second name; there is still only one list. Change it through either name and both see it."
    }
   ]
  },
  {
   "type": "trace",
   "code": "groceries = ['eggs', 'milk']\nshared = groceries\nshared.append('bread')\ncopy = groceries[:]\ncopy.append('jam')\nprint(groceries)\nprint(copy)",
   "steps": [
    {
     "line": 1,
     "names": {},
     "heap": {},
     "out": ""
    },
    {
     "line": 2,
     "names": {
      "groceries": {
       "ref": "o1"
      }
     },
     "heap": {
      "o1": {
       "type": "list",
       "value": "['eggs', 'milk']"
      }
     },
     "out": ""
    },
    {
     "line": 3,
     "names": {
      "groceries": {
       "ref": "o1"
      },
      "shared": {
       "ref": "o1"
      }
     },
     "heap": {
      "o1": {
       "type": "list",
       "value": "['eggs', 'milk']"
      }
     },
     "out": ""
    },
    {
     "line": 4,
     "names": {
      "groceries": {
       "ref": "o1"
      },
      "shared": {
       "ref": "o1"
      }
     },
     "heap": {
      "o1": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread']"
      }
     },
     "out": ""
    },
    {
     "line": 5,
     "names": {
      "groceries": {
       "ref": "o1"
      },
      "shared": {
       "ref": "o1"
      },
      "copy": {
       "ref": "o2"
      }
     },
     "heap": {
      "o1": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread']"
      },
      "o2": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread']"
      }
     },
     "out": ""
    },
    {
     "line": 6,
     "names": {
      "groceries": {
       "ref": "o1"
      },
      "shared": {
       "ref": "o1"
      },
      "copy": {
       "ref": "o2"
      }
     },
     "heap": {
      "o1": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread']"
      },
      "o2": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread', 'jam']"
      }
     },
     "out": ""
    },
    {
     "line": 7,
     "names": {
      "groceries": {
       "ref": "o1"
      },
      "shared": {
       "ref": "o1"
      },
      "copy": {
       "ref": "o2"
      }
     },
     "heap": {
      "o1": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread']"
      },
      "o2": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread', 'jam']"
      }
     },
     "out": "['eggs', 'milk', 'bread']\n"
    },
    {
     "line": null,
     "names": {
      "groceries": {
       "ref": "o1"
      },
      "shared": {
       "ref": "o1"
      },
      "copy": {
       "ref": "o2"
      }
     },
     "heap": {
      "o1": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread']"
      },
      "o2": {
       "type": "list",
       "value": "['eggs', 'milk', 'bread', 'jam']"
      }
     },
     "out": "['eggs', 'milk', 'bread']\n['eggs', 'milk', 'bread', 'jam']\n"
    }
   ],
   "caption": "Step through it. Watch both names point at the same box.",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "branch",
   "question": "After shared.append('bread'), what is groceries?",
   "options": [
    "['eggs', 'milk']",
    "['eggs', 'milk', 'bread']",
    "An error"
   ],
   "answer": 1,
   "remediation": {
    "0": {
     "text": "That would be true if shared were a copy. It isn't: shared and groceries are two names for one list, so appending through shared changes the list groceries names too.",
     "show": "memory"
    },
    "2": {
     "text": "Appending through a second name is allowed; lists can change. Nothing here raises an error."
    }
   },
   "misconception": "Treats b = a as a copy",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "memory",
   "code": "groceries = ['eggs', 'milk']\nshared = groceries\nshared.append('bread')\ncopy = groceries[:]\ncopy.append('jam')\nprint(groceries)\nprint(copy)",
   "names": {
    "groceries": {
     "ref": "o1"
    },
    "shared": {
     "ref": "o1"
    },
    "copy": {
     "ref": "o2"
    }
   },
   "heap": {
    "o1": {
     "type": "list",
     "value": "['eggs', 'milk', 'bread']"
    },
    "o2": {
     "type": "list",
     "value": "['eggs', 'milk', 'bread', 'jam']"
    }
   },
   "caption": "At the end: two names on one list, and a separate copy.",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "fill",
   "code": "groceries = ['eggs', 'milk']\ncopy = ____\ncopy.append('jam')\nprint(groceries)  # should still be ['eggs', 'milk']",
   "answers": [
    "groceries[:]",
    "groceries.copy()",
    "list(groceries)"
   ],
   "hint": "Make a new list with the same items.",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "parsons",
   "prompt": "Put the lines in order so the original list is not changed.",
   "lines": [
    "groceries = ['eggs', 'milk']",
    "copy = groceries[:]",
    "copy.append('jam')",
    "print(groceries)"
   ],
   "distractors": [
    "copy = groceries"
   ],
   "output": "['eggs', 'milk']",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "mistake",
   "children": [
    {
     "text": "Thinking b = a makes a copy. It doesn't: both names point at the same list. Copy with a[:] or list(a)."
    }
   ]
  },
  {
   "type": "check",
   "question": "After `x = [1, 2]; y = x; y += [3]`, what is `x`?",
   "options": [
    "[1, 2]",
    "[1, 2, 3]",
    "[3]",
    "[1, 2, [3]]"
   ],
   "answer": 1,
   "question_id": 1036,
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "recap",
   "points": [
    "b = a: one list, two names.",
    "Changes through either name show through both.",
    "Want a separate list? a[:], a.copy() or list(a)."
   ],
   "children": [
    {
     "text": ""
    }
   ]
  }
 ],
 "range() and counted loops": [
  {
   "type": "h2",
   "children": [
    {
     "text": "range() and counted loops"
    }
   ]
  },
  {
   "type": "predict",
   "code": "for i in range(3):\n    print(i * 2, end=' ')",
   "question": "What does this print?",
   "answer": "0 2 4",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "explain",
   "children": [
    {
     "text": "range(start, stop, step) counts from start and stops before stop. Think of stop as a fence you don't cross."
    }
   ]
  },
  {
   "type": "explore",
   "kind": "range",
   "start": 2,
   "stop": 8,
   "step": 2,
   "caption": "Drag the sliders. The fence at stop is never included.",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "trace",
   "code": "total = 0\nfor price in range(2, 8, 2):\n    total += price\nprint(total)",
   "steps": [
    {
     "line": 1,
     "names": {},
     "heap": {},
     "out": ""
    },
    {
     "line": 2,
     "names": {
      "total": {
       "value": "0"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": 3,
     "names": {
      "total": {
       "value": "0"
      },
      "price": {
       "value": "2"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": 2,
     "names": {
      "total": {
       "value": "2"
      },
      "price": {
       "value": "2"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": 3,
     "names": {
      "total": {
       "value": "2"
      },
      "price": {
       "value": "4"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": 2,
     "names": {
      "total": {
       "value": "6"
      },
      "price": {
       "value": "4"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": 3,
     "names": {
      "total": {
       "value": "6"
      },
      "price": {
       "value": "6"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": 2,
     "names": {
      "total": {
       "value": "12"
      },
      "price": {
       "value": "6"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": 4,
     "names": {
      "total": {
       "value": "12"
      },
      "price": {
       "value": "6"
      }
     },
     "heap": {},
     "out": ""
    },
    {
     "line": null,
     "names": {
      "total": {
       "value": "12"
      },
      "price": {
       "value": "6"
      }
     },
     "heap": {},
     "out": "12\n"
    }
   ],
   "caption": "Step through the loop and watch total grow.",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "branch",
   "question": "What is the last value range(2, 8) gives?",
   "options": [
    "7",
    "8"
   ],
   "answer": 0,
   "remediation": {
    "1": {
     "text": "8 is the stop value, and range stops before it. Try it on the number line above: the last dot is 7.",
     "show": "explore"
    }
   },
   "misconception": "Includes the stop value",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "fill",
   "code": "for i in range(____):\n    print(i, end=' ')  # prints 1 3 5 7 9",
   "answers": [
    "1, 10, 2",
    "1, 11, 2",
    "1,10,2",
    "1,11,2"
   ],
   "hint": "Start at 1, step by 2, and put the fence just past 9.",
   "children": [
    {
     "text": ""
    }
   ]
  },
  {
   "type": "mistake",
   "children": [
    {
     "text": "Expecting the stop value to be included. range(2, 8) stops at 7."
    }
   ]
  },
  {
   "type": "recap",
   "points": [
    "range(start, stop, step)",
    "stop is never included",
    "range(n) is 0 up to n − 1"
   ],
   "children": [
    {
     "text": ""
    }
   ]
  }
 ]
};
  M.BLOCK_TYPES = {
    h2: "Title", explain: "Explanation", mistake: "Common mistake", example: "Worked example", predict: "Predict the output",
    check: "Check question", trace: "Step-through", memory: "Memory diagram", branch: "Misconception check",
    fill: "Fill the blank", parsons: "Order the lines", explore: "Explorable", recap: "Recap",
  };
})();
