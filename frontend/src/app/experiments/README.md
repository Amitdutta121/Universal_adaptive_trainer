# `/experiments` — standalone design prototypes

Self-contained UI prototypes that are **not** part of the Instructor Studio and
**never** call the API or an LLM. `AppChrome` (`src/components/app-chrome.tsx`)
skips any path under `/experiments`, so each one renders with its own full-page
shell and no auth gate.

Use these to review and iterate on a design in isolation, then port the pieces
into the real app.

## Running one

The prototypes are plain routes in the existing app — no separate server.

```bash
cd frontend
pnpm dev
```

Then open the route directly. No login, no backend needed.

| Route | What it is |
| --- | --- |
| [`/experiments/student`](http://localhost:3000/experiments/student) | The student-facing adaptive practice flow: welcome → question → result → summary, with a progress panel. All questions, scoring and mastery numbers are mock data generated in the browser. |
| [`/experiments/tutorials`](http://localhost:3000/experiments/tutorials) | The student-facing tutorial reader: course outline, a tutorial with runnable-looking code, callouts, self-checks and source notes. Content, outputs and book pages are hand-written mock data. |
| [`/experiments/tutorials-cards`](http://localhost:3000/experiments/tutorials-cards) | Tutorial variant A: one idea per card, about 8 cards, keyboard paging, a one-question check at the end. |
| [`/experiments/tutorials-trace`](http://localhost:3000/experiments/tutorials-trace) | Tutorial variant B: step through a loop line by line with live variables, then predict a result. |
| [`/experiments/tutorials-inline`](http://localhost:3000/experiments/tutorials-inline) | Tutorial variant C: no tutorial page; a wrong answer opens a short refresher drawer aimed at the misconception picked. |
| [`/experiments/tutorials-sheet`](http://localhost:3000/experiments/tutorials-sheet) | Tutorial variant D: a one-screen cheat sheet with an interactive number line for `range()`. |
| [`/experiments/tutorials-predict`](http://localhost:3000/experiments/tutorials-predict) | Tutorial variant E: predict what the code prints, see the real result, one line of insight. |
| [`/experiments/tutorials-deck`](http://localhost:3000/experiments/tutorials-deck) | Final variant F: short decks for five topics (conditionals, while, functions, lists, recursion), each with a step-through simulator recorded from real Python, predict-first, and a faded completion. |
| [`/experiments/course-capabilities`](http://localhost:3000/experiments/course-capabilities) | The professor's course capabilities setup: pick a subject preset, enable grading capabilities, see which question types they allow. Four versions behind a switcher (`?v=a` guided setup, `?v=b` live matrix, `?v=c` settings table, `?v=d` pick question types). Registry and course state are mock data in `mock-capabilities.ts`. |
| [`/experiments/tutorials-practice`](http://localhost:3000/experiments/tutorials-practice) | Final variant G: practice-first across the same five topics; a wrong answer climbs a help ladder ending in an editable simulator backed by a small TypeScript Python interpreter checked against CPython. |

## `/experiments/student` layout

```
student/
  page.tsx                server component: route + <title> metadata
  student-experience.tsx  client orchestrator: state machine, persistence, focus
  session-types.ts        the in-memory session shape
  mock-data.ts            stand-in question bank + selection / scoring / mastery
  components/
    welcome-panel.tsx     entry screen: name, practice-set picker, resume
    question-panel.tsx    the current question + answer widgets (per type)
    result-panel.tsx      score, feedback, mastery shift, answer key
    answer-review.tsx     "what was correct" for each question type
    progress-aside.tsx    topic mastery + focus areas
    summary-panel.tsx     end-of-session recap
```

### What is faked, and where the seam is

`mock-data.ts` is the only place with fake data. It provides deterministic
stand-ins for four things the real app gets from the API
(`src/app/students/join/session/[training_session_id]/student-session-screen.tsx`):

- `selectNextQuestion` — the weakness-weighted "what to serve next" pick.
- `scoreAnswer` — answer scoring, including partial credit.
- `applyOutcome` — the mastery / weakness shift each answer causes.
- `initialProgress` — a believable starting profile per practice set.

A seeded PRNG stands in for the randomness in the real selection roulette, so a
given session seed always produces the same run. To port the design, replace
`mock-data.ts` with the typed query layer and keep the components.

### State & persistence

The whole session lives in one reducer in `student-experience.tsx` and is
persisted to `localStorage` (`adaptive-trainer:experiment:student`) on every
change, so a reload resumes. The active set and phase are also mirrored into the
URL query string. "Reset prototype" (in the Prototype controls block, or "Start
over" on the summary) clears it, behind a confirm dialog.

### Prototype controls

At the bottom of the page: a checkbox to make the next answer submit fail once
(to preview the connection-drop recovery flow) and a reset button.
