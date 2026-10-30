# Dimensions

Fourteen facets of frontend quality. Score each 0–4 (`scoring.md`). Run the
checklist live where possible; each unchecked item is a gap in confidence, not a
free pass.

---

## 1. Onboarding & first-run clarity

What a brand-new user sees before they understand anything.

- Is it obvious within ~10 seconds what this app is for and what to do first?
- Is there a guided path, sample data, or empty-state guidance — or does the
  first screen assume knowledge the user doesn't have yet?
- Can the user reach a first success (their first real outcome) without reading
  external docs?
- Are prerequisites (a backend running, a file to upload, a link to receive)
  explained where the user hits them, not buried in a README?
- Does login/signup (or "no account needed") match user expectations for this
  product type?

## 2. Information architecture & navigation

- Do the nav labels map to user goals, or to internal system names?
- Is the current location always clear (active state, breadcrumbs, page title)?
- Can the user get back? Does browser Back do the sane thing everywhere?
- Is grouping logical? Would the user predict which section holds a given task?
- Are there orphan screens (reachable only by URL) or dead ends (no next step)?
- Is anything in the nav that a given user should never see (a control that
  changes global state, an admin-only action on a shared page)?

## 3. Task flow & efficiency

- For the top 3 flows: how many steps, clicks, and page loads to done? Any
  needless ones?
- Does a power user have accelerators — bulk actions, keyboard shortcuts,
  sensible defaults, "apply to all", remembered choices?
- Is repeated work actually repeated (re-typing the same value, re-filtering
  after every action, losing scroll position)?
- Are long operations (generation, upload, batch jobs) backgroundable, or do
  they hold the user hostage to a spinner?
- Does the flow preserve context on refresh (see dimension 12)?

## 4. Feedback & system status

- Does every async action show it started (button spinner/disabled, optimistic
  update) and finished (toast, state change, redirect)?
- Are there four real states for every data view: loading, empty, error,
  populated — plus "not built yet" where honest? Is the empty state distinct
  from the loading state?
- Do long waits show progress or at least elapsed reassurance, not a bare
  spinner that could be a hang?
- After a mutation, does the view reflect the new truth without a manual
  refresh?
- Are success messages specific ("Question 4 approved") not generic ("Success")?

## 5. Error handling & recovery

- Are errors shown in place, in plain language, with the cause and a next step?
- Does the app surface the real server message/code, or swallow it into
  "Something went wrong"?
- Can the user retry without losing their input?
- Network failure, 401/expired session, 404, 409 conflict, 422 validation,
  500, upstream/provider down — is each handled distinctly, or all the same?
- Does a failure in one widget take down the whole page (no error boundary)?
- Are there unhandled promise rejections or thrown errors in the console during
  normal use?

## 6. Forms & data entry

- Is every field labelled (visible `<label>`, not just placeholder)?
- Is validation inline, on blur or submit, tied to the field, and phrased as
  how to fix it?
- Are destructive or costly submits guarded (confirm, type-to-confirm, undo)?
- Is unsaved work protected on navigate-away / accidental close?
- Are disabled submit buttons explained (why can't I continue)?
- Sensible input types, autocomplete, focus on first field, Enter submits,
  paste works?

## 7. Content & microcopy

- Is the voice consistent and human? Any raw enum values, `snake_case`, stack
  traces, or placeholder lorem leaking to the user?
- Do button labels name the action's outcome ("Generate 12 questions") not a
  generic verb ("Submit")?
- Are numbers, dates, and counts formatted one consistent way?
- Is jargon defined or avoided for the persona who'll read it?
- Tone appropriate for the moment — errors not jokey, deletions not cheerful?

## 8. Visual design & consistency

- One spacing scale, type scale, color system — or drift between screens?
- Consistent components (buttons, cards, tables, dialogs look/behave the same
  everywhere)?
- Visual hierarchy: does the eye land on the primary action first?
- Alignment, density, and whitespace deliberate, not accidental?
- Dark mode / theme (if offered) complete, with no unstyled or low-contrast
  patches?
- Loading skeletons match the shape of the content they replace?

## 9. Accessibility (WCAG 2.2 AA)

Never scored above 2 without a live keyboard + screen-reader pass. Floor
severity for failures here is Major.

- Keyboard: every interactive element reachable and operable, visible focus
  ring, logical order, no trap, skip-to-content, Escape closes overlays.
- Screen reader: landmarks, headings in order, labelled controls, `alt` text,
  live regions announce async changes, dialogs announced and focus-managed.
- Contrast: text ≥ 4.5:1 (large ≥ 3:1), focus and UI states ≥ 3:1.
- Zoom to 200% and 400% / 320px width: no loss of content or function.
- Motion respects `prefers-reduced-motion`; nothing conveyed by color alone.
- Forms: errors linked with `aria-describedby`, `aria-invalid` set.
- Target size ≥ 24px; hit areas not cramped.

## 10. Responsive & cross-device

- Test at 320, 375, 768, 1024, 1440 widths.
- No horizontal page scroll; wide content (tables, code, diagrams) scrolls in
  its own container.
- Touch targets and spacing usable on a phone; no hover-only affordances.
- The mobile-critical flows (e.g. anything a student does) are genuinely usable
  one-handed, not just non-broken.
- Modals, sidebars, and toolbars adapt rather than overflow.

## 11. Performance & perceived speed

- Cold load: time to first meaningful paint and to interactive on a mid-tier
  profile (throttle CPU 4×, Fast 3G in devtools).
- Bundle weight and obvious offenders (unsplit routes, huge deps, unoptimized
  images).
- Interaction latency: typing, filtering, opening dialogs feel instant (< 100ms)
  or show feedback.
- No layout shift as data loads (CLS); skeletons reserve space.
- Lists/tables with many rows stay responsive (virtualization or pagination).
- Console clean of performance warnings; no request storms / refetch loops in
  the network panel.

## 12. State, URLs & deep-linking

- Do filters, tabs, pagination, and selected items live in the URL so a view can
  be shared and reloaded?
- Reload mid-task: is the user where they were, or dumped to the top?
- Back/forward move through app state predictably, no double-submit.
- Stale data after another action, or after leaving and returning — refetched or
  invalidated?
- Deep link straight to a detail page: does it load standalone, or assume you
  arrived from the list?

## 13. Data safety & destructive actions

Floor severity for failures here is Major.

- Every delete / overwrite / irreversible action confirmed, with the target
  named in the confirm ("Delete *Chapter 3 questions*?").
- Distinguish reversible from irreversible in the confirm copy.
- Undo or a grace window where feasible.
- No accidental-trigger risk: destructive buttons not adjacent to common ones,
  not the default focus, not fired by Enter.
- Bulk destructive actions state the count and are harder to trigger than single
  ones.
- The UI does not offer an action the backend will refuse — or if it does, it
  explains the refusal from the real error, not a guessed rule.

## 14. Trust, polish & production-readiness signals

The "would I pay for this / demo this" layer.

- Console during a full walkthrough: zero errors, zero warnings from app code.
- No broken links, 404s, missing images, or `undefined` / `NaN` / `[object
  Object]` on screen.
- No TODO / FIXME / "coming soon" / mock-data placeholders in a user-facing
  path (unless honestly labelled as not built).
- Favicon, page `<title>` per route, meta, and 404 page all real.
- Consistent loading behavior — no flash of unstyled content, no content
  jumping.
- Nothing that leaks the implementation: framework error overlays, `_next` paths
  in UI, internal IDs where a name belongs.
- The app degrades honestly: a missing measurement shows as absent, never faked.
