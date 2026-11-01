# Scoring, severity, and the verdict

## Dimension scale (0–4)

Score each of the 14 dimensions:

| Score | Meaning |
|-------|---------|
| **4 — Strong** | Meets the bar and then some. A user never stumbles here; a reviewer would call it a strength. |
| **3 — Adequate** | Meets the bar. Minor rough edges, no user is blocked or confused for long. |
| **2 — Weak** | Works, but real friction. Users hesitate, backtrack, or need a workaround. Ship-relevant. |
| **1 — Failing** | Frequently breaks the user's task or trust. Would embarrass in a demo. |
| **0 — Absent / broken** | Not handled at all, or actively harmful (data loss, keyboard trap, dead flow). |

Tag every score `verified` (checked in the live app) or `estimated` (inferred
from code/screenshots only). An audit with more than ~4 `estimated` dimensions
cannot return a confident "Ship" — say so.

## Severity ladder (per finding)

| Severity | Test |
|----------|------|
| **Blocker** | A user cannot complete a core task, loses data, or the app throws in a primary flow. Or: any WCAG-A keyboard/label failure on a core flow. Ships → users bounce or complain day one. |
| **Major** | A core task is completable but painful, confusing, or unreliable; or an accessibility/data-safety issue off the critical path; or a trust hit a reviewer would flag (console errors, half-built screen shown as done). |
| **Minor** | Localized friction, cosmetic inconsistency, missing accelerator. Annoying, not blocking. |
| **Polish** | Would raise quality but no user is worse off without it. Never applies to accessibility or data-loss findings — those floor at Major. |

Severity is about **user impact, not fix effort.** A one-character CSS fix that
hides the submit button on mobile is a Blocker.

## Weighting for the overall score

Overall = weighted mean of the 14 dimension scores, ×25 for a 0–100 number.

- **Weight ×2:** Onboarding (1), Task flow (3), Feedback (4), Error handling (5),
  Accessibility (9), Data safety (13).
- **Weight ×1:** the other eight.

Report the raw overall number, but the **verdict is set by the rules below, not
by the number** — a high average with one Blocker is still "Not ready".

## Verdict rules

Pick exactly one. The first matching rule wins.

1. **Not ready** — any of:
   - ≥ 1 Blocker finding, or
   - ≥ 3 Major findings, or
   - any weighted-×2 dimension scored 0 or 1, or
   - Accessibility (9) or Data safety (13) scored ≤ 1.
2. **Ship with fixes** — no Blockers, and:
   - 1–2 Major findings, or
   - overall 60–79, or
   - ≥ 2 core dimensions at score 2.
   List the specific fixes that move it to Ship.
3. **Ship** — no Blockers, no Majors, overall ≥ 80, every weighted-×2 dimension
   ≥ 3, Accessibility and Data safety ≥ 3, and no more than ~2 `estimated`
   dimensions.

Always state, in one sentence, the smallest set of changes that would upgrade
the verdict one level.

## Calibration notes

- Judge against the **bar set in Phase 0.** An internal tool at overall 65 with
  no Blockers may be genuinely "Ship" for its context; a paid product is not.
  State the bar you used.
- A frontend that faithfully shows a backend failure is doing its job — don't
  score it down for the backend's fault; log the backend issue separately.
- Wins matter. A dimension at 4 is a real result and belongs in the report so
  the team knows what not to regress.
