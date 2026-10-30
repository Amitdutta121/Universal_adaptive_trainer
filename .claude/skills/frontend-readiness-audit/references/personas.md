# Personas

Six users. Each has a goal, a context that constrains them, and a journey to run
end to end. Adopt the constraints literally — a persona on a phone does not get
to "just use a bigger screen".

If the product is not the one described in the examples, remap each persona to
the equivalent role for this product (first-timer, power user, the
lowest-context / highest-stakes end user, an accessibility user, an external
evaluator, a recovering user) and keep the same lens.

---

## P1 — First-time evaluator (low context, low patience)

**Who:** A domain expert (e.g. an instructor) trying the product for the first
time, deciding in ~10 minutes whether it is worth a second session.

**Context:** Has not read the docs. Does not know the product's vocabulary. Will
blame themselves once, then blame the product and leave.

**Journey:**
1. Land on the entry screen. Can they tell what this is and what to do first?
2. Attempt the headline task the marketing / README promises.
3. Hit the first prerequisite (setup, data, a dependency). Is it explained here?
4. Reach — or fail to reach — a first real result.

**Watch for:** unexplained empty states, jargon labels, a first screen that
assumes step 3, no sample data, silent prerequisites, no "what now" after each
step.

---

## P2 — Power user (high context, high volume, daily)

**Who:** Someone who uses this every working day and has hundreds of items.

**Context:** Knows the product. Wants throughput. Every extra click is paid many
times a day. Keyboard-first.

**Journey:**
1. Run the most frequent repeated task at volume (review many items, generate a
   batch, filter and act).
2. Try to go fast: keyboard nav, bulk select, apply-to-all, defaults, back-to-
   list without losing filters.
3. Do a multi-step task, get interrupted, come back.

**Watch for:** no accelerators, filters/scroll/selection lost after each action,
no bulk operations, mandatory confirmations on safe high-frequency actions,
spinners that block instead of backgrounding, re-entering the same value.

---

## P3 — End user on a phone (lowest context, worst conditions)

**Who:** The person at the far end of the product with the least investment —
for this app, a student joining a session from a texted link. No account.

**Context:** Small screen, one hand, mediocre connection, possibly walking,
easily distracted. Will not troubleshoot anything.

**Journey:**
1. Open the shared link cold.
2. Do the minimum to get started (enter a name, join).
3. Complete the core loop several times (answer a question, see the result,
   continue).
4. Hit a bad link / dropped connection mid-loop.

**Watch for:** horizontal scroll, tap targets too small or crowded, the primary
action or result below the fold, hover-only affordances, no feedback on submit,
heavy payloads on 3G, a broken-link state that just looks like an error, losing
progress on reload.

---

## P4 — Accessibility user (keyboard + screen reader + low vision)

**Who:** Uses the keyboard only, a screen reader some of the time, and browses
at 200% zoom with a high-contrast need.

**Context:** Cannot rely on a mouse, on color, or on small text. Needs the app
to announce what changed.

**Journey:**
1. Tab through the entire primary flow from a cold load — no mouse at all.
2. Open and dismiss every overlay (dialog, menu, sidebar) with the keyboard.
3. Submit a form with an error and recover.
4. Trigger an async action and rely on the screen reader to know it worked.
5. Zoom to 200%, then narrow to 320px.

**Watch for:** invisible focus, illogical tab order, keyboard traps, overlays
that don't take or return focus, unlabelled controls, errors not announced or
not linked to fields, async changes silent to AT, contrast failures, content
lost on zoom, anything conveyed by color alone, `prefers-reduced-motion`
ignored.

---

## P5 — Procurement / product reviewer (external, skeptical, comparative)

**Who:** Evaluating this against alternatives for a buy / adopt / fund decision.
Not the end user — a critic.

**Context:** Has seen many products in this space. Looking for the gap between
the demo and the reality: half-built screens, inconsistency, things that break
under a second look.

**Journey:**
1. Tour every screen in the nav, in order. Note anything unfinished, inconsistent,
   or placeholder.
2. Open the browser console and network panel and keep them open for the whole
   tour.
3. Deliberately misuse: submit empty forms, upload the wrong file type, hit Back
   mid-flow, deep-link into a detail page, double-click submit.
4. Check the trust signals: page titles, 404 page, favicon, error pages, no
   leaked internals.

**Watch for:** console errors/warnings, dead or "coming soon" screens presented
as done, visual drift between sections, `undefined`/`NaN`/`[object Object]`,
framework error overlays, actions offered that then fail, inconsistent
terminology, mock data.

---

## P6 — Returning user recovering from a broken state

**Who:** Comes back to a tab left open overnight, or after an action failed
halfway.

**Context:** Session may be expired. Data on screen may be stale. They half-
remember where they were.

**Journey:**
1. Reload a deep in-app URL after the session/backend has changed underneath it.
2. Act on stale data (approve an item another user already changed → expect a
   409-style conflict).
3. Lose the network mid-mutation, then restore it and retry.
4. Use Back/forward repeatedly across a flow that included a submit.

**Watch for:** expired session dumping to a blank page or a generic error rather
than a re-login with return-to, stale views never invalidated, conflicts shown
as "something went wrong", retry losing input, double-submit on Back, no
distinction between "you're offline" and "the server rejected this".
