# Variant F: trace-lesson deck

Route `/experiments/tutorials-deck`. Five topics (conditionals, while loops, functions, lists,
recursion), five cards each: idea, idea, **simulator**, worked example, **faded check**. Each card
is one idea, a headline of at most 8 words and a body of at most 20 (asserted in the tests).

## Evidence to feature

| Evidence | Where it shows up |
|---|---|
| Step-through execution builds a correct notional machine (Guo 2013; du Boulay; Fincher) | Card 3 of every deck is a step-through of a snippet recorded under `sys.settrace`: variables, call stack, list memory, branch state, loop-test history, output. |
| Code stays the anchor; memory and metaphor only support it (arXiv 2606.19570) | The code is always on screen with the line that just ran marked. Panels sit beside it (below on a phone) and never replace it. Greyed lines (untaken branches) and dashed lines (a call still open) are drawn in the code itself. |
| PRIMM: predict and read before you run or write (Sentance 2017) | Predict comes before the first step and again at one key moment per trace. Nothing asks the student to write until card 5, and even there most checks are pick or order. |
| Worked example, then faded completion, backward fading (Renkl, van Merrienboer) | Card 4 is a complete worked example with its real output; card 5 is the same shape with the end missing (last value, last line, or the order of lines). |
| Parsons problems are as effective as writing and faster (Ericson) | Functions' check is a tap-to-order problem. All 24 orderings were run for real, so a wrong one shows Python's actual error. |
| AI traces help low and high engagement, slightly hurt mid (expertise reversal; arXiv 2606.03288) | Nothing is forced. "Just show me" turns prediction off (and it stays off across decks), "Predict first" toggles back on, "I know this, skip to the check" is on card 1, and every card is one tap away. |
| Let the learner try before the explanation (just-in-time hints) | Wrong predictions and wrong checks get a one-line reason after the attempt. A wrong Parsons order shows Python's own message. Typed answers reveal the value only after two misses. |

## Simulated per topic

Conditionals: branch panel plus greyed lines; snippet has the shadowing bug (`>= 60` before `>= 90`).
While: loop-test history; a second snippet never changes its variable and stops at a 9-step cap
("this would go on forever"). Functions: the call jumps to `def`, frame with its own locals, a
"returns 5" badge, then the value lands in `result`; second snippet returns `None`. Lists: names to
list boxes, grouped by `id()`; `b = a` shows one list with two names. Recursion: `factorial(3)`
frames stack to depth 4 and unwind, each with its own `n`.

## Not built, and what is mock

- Personalisation. A real system would choose the topic order, whether prediction starts on, and
  whether to collapse cards 1 to 2 from the student's measured mastery. Here every deck is open and
  prediction starts on, because the evidence says the scaffold should be earned, not assumed.
- All data is mock and marked `TODO(real):`. `record_traces.py` really ran every snippet (outputs,
  traces, right answers, wrong-order errors), but hand-run. In the product the validator records the
  trace when a tutorial is generated from a book section, and the professor approves it.
- Card copy, questions and "why" lines are hand-written. Which answer is right is never typed: it is
  derived from the recording, and the script asserts it is one of the choices.
- "Done" is a localStorage flag, not a mastery signal.

## Known weakness

The simulator card is dense. On a 390px phone the code, caption and controls stay together but the
panels sit below and the slide scrolls inside its own frame (the page itself never scrolls).
Functions and recursion show variables inside the call-stack frames, not in a separate panel.
