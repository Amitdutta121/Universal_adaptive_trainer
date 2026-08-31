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
