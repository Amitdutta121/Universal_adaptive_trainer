---
name: frontend-readiness-audit
description: >-
  Evaluate a web frontend for user-friendliness and product-readiness across
  multiple UX dimensions and user personas, then produce a severity-ranked
  findings report and an explicit go / no-go verdict. Use when someone asks
  whether the frontend / UI / app is user-friendly, intuitive, polished,
  ship-ready, product-ready, "good enough to demo", or asks for a UX audit,
  heuristic evaluation, usability review, or persona walkthrough of a web app.
---

# Frontend Readiness Audit

A self-contained evaluation you can run against any web frontend to answer one
question: **is this user-friendly and product-ready, or not — and if not, what
exactly stands in the way?**

The audit crosses two axes:

- **Dimensions** — 14 facets of UX quality (navigation, feedback, accessibility,
  data safety, polish, …). See `references/dimensions.md`.
- **Personas** — 6 distinct users who each stress the product differently (a
  first-time instructor, a power user, a student on a phone, an accessibility
  user, a procurement reviewer, a returning user recovering from an error). See
  `references/personas.md`.

Every finding is scored for severity and tied to a concrete failure a real user
would hit. The output is a written report plus a verdict, never a vague "looks
nice".

## Output

Produce two things:

1. **`frontend-audit-<YYYY-MM-DD>.md`** in the repo (or a location the user
   names) — the full report, following `templates/report-template.md`.
2. A **short spoken summary** in the reply: the verdict, the top 3 blockers, and
   the single highest-leverage fix.

Offer to also publish the report as an HTML artifact if the user wants something
shareable. Do not publish proactively.

## Workflow

### Phase 0 — Scope and access

1. Confirm what "the frontend" is (path, dev command, URL) and what
   product-readiness means for this user: internal tool, paid product, investor
   demo, open beta. The bar differs — record which bar you are judging against.
2. Establish the best available level of access, in this order of preference:
   - **Live app** — get it running (check the project README / a `run` skill /
     `package.json` scripts). If it needs a backend, start that too. A live app
     is required for the accessibility, performance, and state dimensions to be
     scored rather than estimated.
   - **Live app via `claude-in-chrome`** — drive real flows in the browser,
     capture screenshots, read the console and network panels. Strongly
     preferred; load those tools if available.
   - **Screenshots + source only** — if the app cannot run, review committed
     screenshots and read the component source. Mark every dimension you could
     not verify live as `estimated` in the report and lower confidence
     accordingly.
3. Inventory the surface: list every route/screen, every primary user flow, and
   every async state the code claims to handle (loading / empty / error /
   success / not-built). Grep for the shared state components and the API client
   to find these fast.

### Phase 1 — Persona walkthroughs

For **each** persona in `references/personas.md`:

1. Adopt that persona's goal, context, and constraints literally.
2. Walk their primary journey end to end — clicking through the live app when
   possible. Narrate friction the moment it occurs: hesitation, backtracking, a
   dead end, an unreadable label, a missing confirmation, a spinner with no
   timeout.
3. Log each friction point as a raw finding: what the persona was trying to do,
   what happened, why it hurts, and where in the UI/code it lives
   (`file_path:line`).
4. Note wins too — things that genuinely work well are part of an honest verdict
   and tell the user what not to break.

Keep persona notes concrete. "A student on a phone can't tell the answer was
submitted because the button gives no feedback and the result appears below the
fold" — not "feedback could be improved".

### Phase 2 — Dimension scoring

Go through all 14 dimensions in `references/dimensions.md`. For each:

1. Run its checklist against the app.
2. Pull in the relevant persona findings from Phase 1.
3. Assign a score 0–4 using the scale in `references/scoring.md`, with a
   one-line justification and the evidence (screenshot, `file:line`, console
   output).
4. Record whether the score is `verified` (checked live) or `estimated`.

### Phase 3 — Synthesis and verdict

1. Deduplicate findings across personas and dimensions; a single root cause that
   surfaced for three personas is one finding with three symptoms.
2. Assign each finding a severity: **Blocker / Major / Minor / Polish** (defined
   in `references/scoring.md`).
3. Build the scorecard: the 14 dimension scores, a weighted overall score, and
   the verified/estimated split.
4. Reach a verdict using the rules in `references/scoring.md`:
   **Ship** / **Ship with fixes** / **Not ready**. The verdict must be forced by
   the findings — if there is one Blocker, it cannot be "Ship".
5. Write the report from `templates/report-template.md`. Order findings by
   severity, then by number of personas affected.
6. Produce a prioritized fix list: what to do before shipping, what can follow.

## Rules

- **No invented praise or invented problems.** Every finding cites a real screen,
  interaction, or line of code. If you could not test something, say so — do not
  guess a score and present it as measured.
- **Severity reflects user impact, not effort.** A one-line CSS fix that blocks
  checkout is still a Blocker.
- **Judge against the stated bar** from Phase 0. An internal admin tool and a
  public product do not get the same verdict for the same polish gap.
- **The verdict is not negotiable down.** If the findings say "Not ready", the
  report says "Not ready", with the specific blockers that would change it.
- **Distinguish frontend faults from backend faults.** If the UI faithfully
  surfaces a backend error, that is a point in the frontend's favor; note the
  backend issue separately.
- **Accessibility and data-loss findings are never "Polish".** The floor for a
  keyboard trap, a missing form label on a primary flow, or an unconfirmed
  destructive action is Major.

## References

- `references/dimensions.md` — the 14 dimensions, each with a concrete checklist.
- `references/personas.md` — the 6 personas, with goals, context, and the
  journey each one runs.
- `references/scoring.md` — the 0–4 dimension scale, the severity ladder, the
  weighting, and the verdict decision rules.
- `templates/report-template.md` — the report structure to fill in.
