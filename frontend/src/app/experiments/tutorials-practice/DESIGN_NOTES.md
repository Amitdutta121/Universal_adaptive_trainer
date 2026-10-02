# G. Practice first, simulator on demand

Route `/experiments/tutorials-practice`. There is no tutorial page: the practice screen is the tutorial. Help is a ladder that opens only when the student misses or asks, and never forces a reading. Ten mixed questions, five topics (conditionals, while, functions, lists, recursion), two Parsons problems (conditionals, functions).

## Evidence to feature

| Evidence | Feature |
|---|---|
| Step-through traces build a correct notional machine (Guo 2013, Python Tutor / CodeLens) | Rung 2: line-by-line simulator of the question's own code, variables, call-stack frames, output, list identity (`b = a` shows "same list #1") |
| Multi-view study (arXiv 2606.19570): learners keep returning to the code | Code is the largest element of the sheet; variables, output and caption only support it; current line marked |
| PRIMM (Sentance 2017): predict, run, investigate, modify | Predict = the answer itself, so the simulator has no predict-first gate. Modify = "Try it yourself": edit the snippet, Run, step through the new version |
| Worked, then faded examples (Renkl and Atkinson; van Merrienboer) | Rung 3: 2 to 3 line worked example, then the same idea with the LAST line blank; the student's line is run and passes if the output matches (so any correct line passes) |
| Parsons problems as effective as writing, about 23% faster (Ericson et al.) | Two ordering questions, move up/down buttons (keyboard and phone friendly); an order passes if it runs and prints the goal |
| Expertise reversal in AI-generated animated traces (arXiv 2606.03288): helps low and high engagement, slightly hurts the middle; no long-term exam effect | Nothing forced or auto-played; rung 2 is a click, rung 3 a click after that; "Try another" is never gated. TODO(real): a real system would personalise from measured mastery, not from this session |
| Self-remediation before tutor remediation | Rung 1 is one line naming the misconception, not the answer, and gives ONE more attempt before the simulator is pushed |

## The ladder as built

1. Wrong answer: "Not quite", one hint line (mock, `TODO(real)` tagged distractor), one more attempt. "Show me what happens" is offered quietly.
2. Second miss: correct answer marked, "Show me what happens" becomes primary. The sheet (bottom sheet on phones, side panel from 768px) pins the student's answer next to the real output, with a match/mismatch mark.
3. "Explain it like a worked example" (in the sheet footer, and on the page once the sheet was opened) then "Try another".

Adaptivity stub (mock, `TODO(real)`): per-topic confidence and a miss streak; two misses on a topic bring the next question from that topic. A quiet strip shows one dot per question and topic (filled = right first try, outline = second try, red = missed).

## Mini-python (prototype stand-in)

`mini-python/`: lexer, parser, evaluator/tracer, each small; no eval, no `Function`, no dependencies. Supported: int (bigint), float, str, bool, None, list and range values; `+ - * / // % **`, unary `- + not`, comparisons (chained, `in`, `not in`, `is`), `and`/`or`; assignment (chained, `x[i] = v`, augmented, list `+=` in place); `if/elif/else`, `while`, `for` over list, range or string, `break`, `continue`, `pass`; `def` (positional params) with `return`, recursion, local versus global scope; `print len range str int float bool abs sum min max list`; `append pop extend insert copy`; indexing incl. negative. Caps: 300 steps ("Stopped after 300 steps. This loop may never end."), 20 nested calls (RecursionError), 10,000-item values. Unsupported syntax (f-strings, dicts, tuples, slicing, comprehensions, lambda, classes, imports, keyword/default args, nested `def`, one-line bodies, `.sort()` and other methods) gives "This mini-runner doesn't support X yet". Errors carry Python's class and CPython's message plus one plain-words line. The real system would run code in a sandbox (Pyodide or a server) and record traces from CPython.

## CPython table test

`mini-python/record_expected.py` runs 94 snippets under `sys.settrace` on CPython 3.12.10 and writes `expected.generated.ts`. `cpython-table.test.ts` asserts, for each: identical stdout, identical sequence of executed line numbers (every 'line' event of the snippet's own frames, module level and inside functions), same ending (ok, cap, or the same exception class AND message). Covers all five topics, loops, operators, and NameError, IndexError, ZeroDivisionError, TypeError, UnboundLocalError, AttributeError, ValueError, RecursionError. The bank's own code is asserted to be in the table (`mock-data.test.ts`).

Normalisation and known differences:
- Only 'line' events are compared, not call/return/exception events, and the line of an error is not compared.
- The two capped behaviours are recorded with the same caps (the recorder raises from its trace function at the 301st line event and at the 21st nested frame), so those rows prove "identical up to the cap", not "identical to an uncapped run". CPython's own limit is about 1000 frames.
- Not covered, and different by design: a statement spread over several physical lines (CPython may report inner lines; this reports the first), float overflow and complex results of `**`, and `is` on equal ints or strings (compared by value here).
- Checked against CPython and found different, then fixed: the message for `x % 0.0` is "float modulo".

## Not done (deliberately)

No persistence, no real mastery model, no LLM. Distractors, hints, worked and faded examples are hand-written (`TODO(real)`): the real pipeline would generate them with the question, validate them by running CPython, and route them through professor review. Question options are 3 per question to keep the mock small.
