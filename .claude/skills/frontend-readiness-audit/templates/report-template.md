# Frontend Readiness Audit — <app name>

**Date:** <YYYY-MM-DD>
**Audited build / commit:** <hash or branch>
**Access level:** live app / live via browser / screenshots + source
**Readiness bar judged against:** <internal tool | paid product | investor demo | open beta>
**Auditor:** Claude Code (`frontend-readiness-audit` skill)

---

## Verdict

> **<Ship | Ship with fixes | Not ready>**

<2–4 sentences: the headline. What works, what doesn't, and why this verdict.>

**Smallest change that upgrades the verdict:** <one sentence>

**Overall score:** <n>/100  ·  **Verified dimensions:** <x>/14  ·  **Blockers:** <n>  ·  **Majors:** <n>

---

## Scorecard

| # | Dimension | Score /4 | Verified? | One-line justification |
|---|-----------|:--------:|:---------:|-----------------------|
| 1 | Onboarding & first-run clarity | | | |
| 2 | Information architecture & navigation | | | |
| 3 | Task flow & efficiency | | | |
| 4 | Feedback & system status | | | |
| 5 | Error handling & recovery | | | |
| 6 | Forms & data entry | | | |
| 7 | Content & microcopy | | | |
| 8 | Visual design & consistency | | | |
| 9 | Accessibility (WCAG 2.2 AA) | | | |
| 10 | Responsive & cross-device | | | |
| 11 | Performance & perceived speed | | | |
| 12 | State, URLs & deep-linking | | | |
| 13 | Data safety & destructive actions | | | |
| 14 | Trust, polish & production signals | | | |

---

## Findings

Ordered by severity, then by number of personas affected. Each finding is one
root cause.

### F1 — <short title>  ·  `<Blocker | Major | Minor | Polish>`

- **Dimensions:** <e.g. 4, 5>
- **Personas hit:** <e.g. P1, P3, P6>
- **Where:** `<file_path:line>` / <screen + interaction>
- **What happens:** <the concrete failure a user experiences>
- **Why it matters:** <impact on task / trust / access>
- **Evidence:** <screenshot ref, console line, repro steps>
- **Suggested fix:** <the smallest correct change>

### F2 — …

_(repeat)_

---

## What works well

Genuine strengths — do not regress these.

- <strength> — `<file:line / screen>`
- …

---

## Persona walkthrough notes

### P1 — First-time evaluator
- **Reached first success:** yes / no — <how, or where it stalled>
- **Friction:** <bullets>

### P2 — Power user
- <bullets>

### P3 — End user on a phone
- <bullets>

### P4 — Accessibility user
- **Keyboard-only pass:** complete / blocked at <step>
- **Screen-reader pass:** <result>
- **200% zoom / 320px:** <result>
- <bullets>

### P5 — Procurement / product reviewer
- **Console during full tour:** <clean | N errors, M warnings — list>
- **Unfinished / placeholder screens:** <list>
- <bullets>

### P6 — Returning user recovering
- <bullets>

---

## Fix plan

### Before shipping (clears the verdict)
1. <finding id> — <action>
2. …

### Next (raises quality, not blocking)
- <finding id> — <action>

### Backlog / polish
- …

---

## Method & coverage

- **Routes reviewed:** <list or count>
- **Flows walked:** <list>
- **Environment:** <browser, viewport sizes, CPU/network throttle, OS>
- **Not covered / could not verify:** <list — these cap confidence>
