# Frontend Readiness Audit — Student experience prototype (`/experiments/student`)

**Date:** 2026-08-27
**Audited build / commit:** branch `dev`, uncommitted (new route `src/app/experiments/student/**`)
**Access level:** source + SSR HTML + executed jsdom flow test — **no live browser** (the `claude-in-chrome` extension was not connected this session)
**Readiness bar judged against:** internal **design prototype** — a mock-data reference of the student flow, meant to be reviewed and later ported into the console. Not a paid product, not a public demo.
**Auditor:** Claude Code (`frontend-readiness-audit` skill)

---

## Verdict

> **Ship with fixes**

The prototype does the job it was built for. From a cold load a first-time learner sees, within a few seconds, what it is (a "Prototype" banner states the mock-data honestly), how it adapts, three practice sets, and a one-click path to the first question. The full loop — welcome → loading → question → result → summary — works, with four honest async states, a distinct loading skeleton, specific result copy ("scored 80 of 100 — partly correct"), a visible mastery shift, a polite live region, and a simulated connection-drop that recovers without losing the answer. Every input is labelled, destructive actions are confirmed with the count and an "it can't be undone" line, and a full run logs **zero console errors** (verified). The reason this is not a clean "Ship" is that the dimensions that *require* a real browser — full WCAG keyboard/screen-reader/zoom/contrast, responsive behaviour at real viewports, paint performance — could only be read from source this session, and the skill does not let Accessibility score above 2 without a live pass.

**Smallest change that upgrades the verdict:** run the live keyboard + screen-reader + 200%/400%-zoom + contrast pass in a browser and fix anything it surfaces — that moves Accessibility (9) from 2/estimated to ≥3/verified and clears the only Major.

**Overall score:** 85/100  ·  **Verified dimensions:** 10/14 (dims 8–11 estimated — no live browser)  ·  **Blockers:** 0  ·  **Majors:** 1

_Update (same day): F3 and F5 from the first pass were fixed before this report was finalised — `phase` was removed from the URL, and the focus-target wrappers now paint a `focus-visible` ring. The scorecard and findings below reflect the fixed state._

---

## Scorecard

| # | Dimension | Score /4 | Verified? | One-line justification |
|---|-----------|:--------:|:---------:|-----------------------|
| 1 | Onboarding & first-run clarity | 4 | verified* | Purpose, mock-data disclosure, "how it adapts" and a first question are all reachable with no docs. |
| 2 | Information architecture & navigation | 3 | verified | One route, phase-driven; clear "Console" exit and End-session; browser Back exits the prototype (one history entry, by design — Resume is the recovery path). |
| 3 | Task flow & efficiency | 3 | verified | One question at a time, Ctrl/⌘+Enter submit, remembered name, Resume; no bulk/skip (not needed here). |
| 4 | Feedback & system status | 4 | verified | Distinct loading skeleton vs empty, "Scoring…" + disabled button, specific result text, mastery delta, `role="status"` live region. |
| 5 | Error handling & recovery | 3 | verified | Simulated drop shows an in-place `role="alert"`, keeps the answer, offers Retry; only one error class exists (by design — no real network). |
| 6 | Forms & data entry | 4 | verified | Every field has a real `<label>` / `<fieldset><legend>`; native radios; Enter starts; submit copy explains the lock-in. |
| 7 | Content & microcopy | 3 | verified | Human voice, enum values mapped to prose ("Predict the output"), consistent `n / 100`; one "favour"/"favor" spelling drift. |
| 8 | Visual design & consistency | 3 | estimated | Uses the shared tokens + `Card`/`Button`/`Badge`; skeleton matches content shape — not viewed rendered. |
| 9 | Accessibility (WCAG 2.2 AA) | 2 | estimated | Landmarks, heading order, labelled controls, live regions, `prefers-reduced-motion`, colour never the sole signal are all wired — but keyboard/SR/zoom/contrast were not exercised live, and the scale caps this at 2. |
| 10 | Responsive & cross-device | 3 | estimated | `min-w-0`, `overflow-x-auto` on code, wrapping badge rows, single-column below `lg`, full-width mobile buttons — not measured at 320/375/768. |
| 11 | Performance & perceived speed | 4 | estimated | No data fetching, no heavy deps on this route (no dnd-kit / codemirror / charts), deterministic sync logic; delays are intentional UX. |
| 12 | State, URLs & deep-linking | 4 | verified | `set` mirrored to the URL and honoured as the welcome default; full session in `localStorage`, reload → Resume with a summary line; `phase` intentionally kept out of the URL since it can't be reconstructed cold. |
| 13 | Data safety & destructive actions | 4 | verified | Reset is behind a confirm naming the count + "can't be undone", destructive-variant button, not default focus; End-session confirm is correctly framed as non-destructive. |
| 14 | Trust, polish & production signals | 4 | verified | Zero console errors across a full run; mock data labelled honestly; real per-route `<title>`; clamps guard against `NaN`/`undefined`; empty set degrades to an honest summary. |

\* Onboarding structure and copy are verified from SSR + tests; the *visual* first impression is estimated.

---

## Findings

Ordered by severity, then by number of personas affected.

### F1 — Accessibility is wired but unverified: keyboard, screen reader, zoom, contrast · `Major`

- **Dimensions:** 9
- **Personas hit:** P4, P5
- **Where:** whole route; focus wrappers `student-experience.tsx:493` and `result-panel.tsx:66`; live region `student-experience.tsx:413`
- **What happens:** The code does the right things — semantic `main`/`complementary`/`header`, `h1→h2→h3` order, `<label>`/`<fieldset><legend>` on every control (asserted in the flow test), a `role="status"` polite region, `role="alert"` errors, `prefers-reduced-motion` gating, native keyboard-operable radios/checkbox, and every result state carrying an icon **and** text (never colour alone). What is **not** verified: that a screen reader actually announces the phase changes; that the focus ring is visible on the `tabIndex={-1}` panel wrappers focus is moved to; that text/UI contrast hits 4.5:1 / 3:1 (the amber "Prototype" and streak text on tinted backgrounds are the risk spots); that nothing is lost at 200%/400% zoom or 320px.
- **Why it matters:** For P4 this is the whole experience; the scale (and this skill) will not credit accessibility above 2 without a live pass, so it also blocks a "Ship" verdict.
- **Evidence:** `student-experience.test.tsx` asserts labels/roles/landmarks/live-region/confirmed-reset and **0 console errors**; SSR HTML carries the skip link, `role="status"`, and `<title>`. No browser was available to drive keys / AT / zoom.
- **Suggested fix:** One browser pass: Tab through welcome→question→result→summary with no mouse; open/close both dialogs with keyboard; submit the forced-fail flow and confirm the error is announced and focus is sane; run axe or a contrast checker on the amber and badge text; zoom to 200% and 400% and narrow to 320px. Give the focus-target wrappers a visible ring (`focus-visible:ring-2`) instead of `outline-none`.

### F2 — Browser Back leaves the prototype instead of stepping back a phase · `Polish` (accepted)

- **Dimensions:** 2, 12
- **Personas hit:** P3, P6
- **Where:** `student-experience.tsx` — `window.history.replaceState` on every state change
- **What happens:** The prototype keeps a single history entry, so browser Back from a question navigates out of the app rather than to the previous phase. Reload is handled well (welcome screen offers Resume with a "N answered · <set>" line), so no progress is lost.
- **Decision:** Accepted for a prototype. Phase history is intentionally flat; `localStorage` + Resume is the one recovery path, and it's now documented in the code comment at the persistence effect. Revisit if this design ships — then push a history entry per phase and handle `popstate`.

### F3 — `phase` was written to the URL but couldn't be reconstructed cold · `Fixed`

- **Dimensions:** 12
- **Was:** the URL advertised `?phase=…` that a cold load could not honour.
- **Fix applied:** `phase` removed from the URL entirely; only `set` is written, and `set` *is* honoured as the welcome-screen default. `student-experience.tsx` persistence effect.

### F4 — One spelling inconsistency in user copy · `Fixed`

- **Dimensions:** 7
- **Was:** "Questions favour…" on the welcome screen, US spelling everywhere else.
- **Fix applied:** "favour" → "favor" in `welcome-panel.tsx`.

### F5 — Result / question focus target had no visible focus indicator · `Fixed`

- **Dimensions:** 9
- **Was:** focus was moved to `tabIndex={-1}` wrappers styled `outline-none`, so a keyboard user saw nothing (the SR announcement still fired).
- **Fix applied:** both wrappers now carry `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`. `student-experience.tsx`, `result-panel.tsx`. Still needs the F1 live pass to confirm it renders as intended.

---

## What works well

Genuine strengths — do not regress these.

- **Honest mock-data disclosure.** The persistent "Prototype" banner (`student-experience.tsx:450`) means the mock data is *labelled*, which is exactly what dimension 14 asks for — it never reads as real.
- **Four real async states.** Loading skeleton (shape-matched, `aria-hidden`), populated question, scored result, and an honest "answered everything" summary — plus the simulated error — are all distinct. `student-experience.tsx:479`.
- **Specific feedback.** Result copy is "Correct / Partly correct / Not quite" + `score / 100` + a mastery delta with a signed number and a progress bar, not "Success". `result-panel.tsx`.
- **Confirmed, well-framed destructive action.** Reset names the exact count and "can't be undone", uses the destructive button variant, and is not the default focus; End-session is correctly *not* framed as destructive because progress is kept. `student-experience.tsx:571`, `:594`.
- **Recovery keeps the user's work.** The simulated connection drop re-renders as an in-place alert with the answer still populated and a Retry that re-scores. Verified in `student-experience.test.tsx`.
- **Clean console.** A full welcome→result run logs zero `console.error` (verified test).
- **Portable structure.** `mock-data.ts` is the single seam; the components take plain props. Swapping in the real query layer is a contained change.

---

## Persona walkthrough notes

### P1 — First-time evaluator
- **Reached first success:** yes — welcome screen → pick a set → "Start practising" → ~0.5s skeleton → first question → submit → scored result with explanation. No docs needed.
- **Friction:** none blocking. The "how it adapts" three-up is good context. Estimated: the visual hierarchy of the welcome screen was not seen rendered.

### P2 — Power user
- Ctrl/⌘+Enter submits text answers; name is remembered across sessions; Resume restarts an interrupted run. No skip-question or keyboard-only option-select accelerators — acceptable for a per-question practice loop, and out of scope for a prototype.

### P3 — End user on a phone
- Source looks phone-safe: single column below `lg`, full-width primary buttons, `overflow-x-auto` on code, wrapping badge rows, `min-w-0` on the main column. **Not measured at 320/375px** (F1/dimension 10, estimated). Back-button behaviour (F2) would bite this persona.

### P4 — Accessibility user
- **Keyboard-only pass:** not run (no browser). Code supports it: native controls, focusable dialogs (Radix), skip link, focus moved to new panels.
- **Screen-reader pass:** not run. `role="status"` polite region carries phase/score/mastery announcements; `role="alert"` on errors; `aria-hidden` on the skeleton and decorative icons.
- **200% zoom / 320px:** not run.
- Colour is never the only signal — every result state has an icon + text label. Focus lands on wrappers with no visible ring (F5).

### P5 — Procurement / product reviewer
- **Console during the run:** clean — 0 errors (verified).
- **Unfinished / placeholder screens:** none presented as real; the whole page is labelled a prototype.
- Deliberate misuse handled: empty answer keeps submit disabled with copy explaining the lock-in; the forced-fail path recovers; reset/end are confirmed. Trust signals: real per-route `<title>`, no leaked `_next`/internal ids, no `NaN`/`[object Object]`. Spelling drift (F4).

### P6 — Returning user recovering
- Reload mid-run → welcome screen offers "Resume" with a "N answered · <set>" summary; state comes back from `localStorage`. Good.
- Back button → leaves the app (F2, accepted for a prototype). Shared URL carries only `?set=`, which is honoured (F3 fixed).
- An unsubmitted in-progress answer is *not* persisted (it's component state) — a reload loses whatever was typed but not yet submitted. Same as the real session screen; acceptable for a prototype, worth knowing.

---

## Fix plan

### Before "Ship" (clears the verdict)
1. **F1** — one live browser pass: keyboard-only walkthrough welcome→summary, screen-reader announcement check on every phase change, both dialogs opened/closed by keyboard, the forced-fail path, 200%/400% zoom + 320px, contrast check on the amber banner / streak / badge text. Fix what it finds, and confirm the F5 focus rings render. This is the only thing between "Ship with fixes" and "Ship".

### Done this pass
- **F3** — `phase` removed from the URL.
- **F4** — "favour" → "favor".
- **F5** — `focus-visible` rings added to the focus-target wrappers (needs F1 to confirm visually).

### Backlog / polish
- **F2** — if this design ships, replace the flat history with per-phase `pushState` + `popstate` handling.
- Consider auto-focusing the name field on the welcome screen (dimension 6 nicety; debatable since it steals focus from the top of the page).

---

## Method & coverage

- **Routes reviewed:** `/experiments/student` (the only route in this prototype). `src/components/app-chrome.tsx` change reviewed (adds `/experiments` to the chrome/auth bypass, mirroring `/login`).
- **Flows walked:** welcome → loading → question (multiple-choice, true/false, short-answer, output-prediction, order-the-steps) → result → next → summary; forced-fail → retry → result; End-session confirm → summary; Reset confirm → welcome. Walked via `src/app/experiments/student/student-experience.test.tsx` (5 cases, all passing) and source reading.
- **Environment:** Next 16.3.1 dev server, SSR HTML fetched over curl (`200`, correct `<title>`, welcome content present); Vitest + @testing-library/react (jsdom) for the interactive flow; `pnpm typecheck` clean; `biome check` clean on the new files; full suite 60/60.
- **Not covered / could not verify (caps confidence):** anything needing a real browser — live keyboard traversal, screen-reader output, focus-ring visibility, colour contrast ratios, responsive layout at 320/375/768/1024/1440, paint/interaction timing, `prefers-reduced-motion` actually taking effect, browser Back/forward. Dimensions 8–11 are `estimated`; dimension 9 is capped at 2 by the scale as a result.
