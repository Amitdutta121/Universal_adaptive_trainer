# Conventions for building mockup pages

Read `PLAN.md` first (what each page is for), then `course.html` (the reference page:
copy its `<head>` and script order exactly) and `_template.html`.

## Files

- One page = one `.html` file in this folder, named exactly as in the table below. Links
  between pages use these names; a missing or renamed file is a broken link.
- **Do not edit** `assets/theme.css`, `assets/layout.js`, `assets/mock-data.js`,
  `course.html`, `index.html` or another group's pages. If you need more mock data, create
  `assets/data-<your-group>.js` that *adds* fields to `window.MOCK` (loaded right after
  `mock-data.js`), and mark every invented value `TODO(real)` in a comment.
- Page-specific CSS goes in a `<style>` block in the page, and only when Tailwind utilities
  can't do it.

| Group | File → page |
|---|---|
| A public | `landing.html` A1, `signup.html` A2, `login.html` A3, `reset-password.html` A4, `accept-invite.html` A5, `verify-email.html` A6 |
| B workspace | `courses.html` B1, `new-course.html` B2, `jobs.html` B3, `usage.html` B4, `account.html` B5 |
| C course | `course.html` C1 (done), `materials.html` C2, `book.html` C3, `section.html` C4, `taxonomy.html` C5, `taxonomy-builder.html` C6, `taxonomy-draft.html` C7, `coverage.html` C8, `generate.html` C9, `questions.html` C10, `question.html` C11, `review.html` C12, `alignment.html` C13 |
| D teach | `question-sets.html` D1, `classes.html` D2, `students.html` D3, `student.html` D4 |
| E | `settings.html` E1 |
| F student | `student-join.html` F1s, `student-home.html` F2s, `student-practice.html` F3s, `student-summary.html` F4s |
| G run (Phase 2) | `schedule.html` G1, `assignments.html` G2, `assignment.html` G3, `gradebook.html` G4, `insights.html` G5, `import-questions.html` G6, `reports.html` G7, `exam-export.html` G8, `copy-course.html` G9, `term-report.html` G10, `email-digest.html` G11 |

Phase 2 pages read the shared term data in `assets/data-g.js` (schedule, assignments,
per-student results, extensions, reports, insights, exam holds; loaded on every page right
after `mock-data.js`). Don't redefine those; add page-only extras in `assets/data-g-<name>.js`.
New nav keys: `schedule assignments insights gradebook reports term-report import exams`.
`assignment.html` → `assignments`, `copy-course.html` → `settings`, `email-digest.html` is
workspace scope with key `account`.

Detail pages take an id in the query: `book.html?book=b1`, `section.html?book=b1&section=b1-9-5`,
`question.html?id=1004`, `student.html?id=s5`, `taxonomy-builder.html?version=v3`.
Read them with `Mock.param("id")`.

## Page shell (done for you by `assets/layout.js`)

- `<body data-scope="public|workspace|course|student" data-nav="<key>" data-title="...">`
  with a single `<main x-data="page()" x-cloak>`. Sidebar nav keys are `course materials
  taxonomy coverage generate questions review alignment question-sets classes students
  settings` (course scope) and `courses jobs usage account` (workspace scope). Detail pages use
  their parent's key (`book.html` → `materials`).
- Course pages read the course from `?course=python|statistics` (default python). **Every
  link to a course page must be built with `Mock.link("file.html", {extra: "params"})`** so the
  course carries over. In Alpine: `:href="Mock.link('questions.html')"`.
- Helpers: `Mock.course`, `Mock.courseId`, `Mock.param(name)`, `Mock.pct(x)`, `Mock.usd(x)`,
  `Mock.toast("Saved")`, `Mock.tone(status)` → a `tone-*` class, `Mock.label(status)` → the
  human label. Data is in `MOCK` (see `assets/mock-data.js`; read it before designing).

## Components: Basecoat v1 (shadcn/ui in plain HTML)

- Buttons: `class="btn"` + `data-variant="secondary|outline|ghost|link|destructive"` +
  `data-size="sm|lg|icon|icon-sm"`. **Not** `btn-outline` / `btn-sm` (that's v0; it renders unstyled).
- Card: `<div class="card"><header><h2>…</h2><p>…</p></header><section>…</section><footer>…</footer></div>`.
- Before using any other component (table, tabs, dialog, input/field, select, switch, checkbox,
  badge, alert, progress, tooltip, dropdown), fetch `https://basecoatui.com/components/<name>/`
  and copy its v1 markup. Don't guess class names.
- Status pills: `<span class="pill tone-ok">Approved</span>`; tones: `tone-ok tone-warn
  tone-critical tone-accent tone-muted`. Colors come only from theme tokens
  (`var(--primary)`, `var(--muted)`, `var(--border)`…), never hex values or Tailwind palette
  colors like `bg-blue-500`.
- **Never combine a static `style="…"` with a string `:style="`…`"` on one element**: Alpine's
  string binding replaces the whole attribute, so the static part (usually a background) vanishes.
  Use the object form for everything: `:style="{ background: 'var(--primary)', width: `${p}%` }"`.
- Icons: `<i data-lucide="name"></i>` (lucide.dev names). Never put Alpine bindings on the
  `<i>`; wrap it in a `<span>` and bind that.

## Interactivity: Alpine.js

- State lives in `page()`, seeded from `MOCK`. Clicks change it: approving a question moves it
  out of the queue, a wizard advances, a filter filters. Actions that would hit the backend
  show `Mock.toast("…")` and update local state. Reload resets everything, which is expected.
- Long AI actions (generate, draft taxonomy, import, re-run judges) show a short fake
  progress state, then the result, and mention the job appears in Jobs.

## Quality bar

- **Must not look AI-generated.** Match `course.html` and the real app's pages
  (`frontend/src/app/<route>/` is the current implementation of most C/D pages; read it and
  keep its information, columns and wording). No decorative gradients, no emoji, no hero
  illustrations on work pages, no marketing copy inside the app. Dense, tool-like layouts.
- Realistic content from `MOCK`: use real subtopic names, real question text, real numbers.
  Include empty, loading or error states where a real user would hit them (for example the
  statistics course has no questions yet).
- Copy is plain and specific ("14 questions awaiting review"), not "Unlock insights".
- Width: works from 1024 px up for professor pages; the student pages (F) must work at 390 px.

## Verify before reporting

Run `tools/check.sh <scratch_dir> <each page with realistic query params>` from this folder.
Every page must print `OK`; open the PNGs it writes (Read tool) and fix anything broken
or ugly. Also check both courses (`?course=statistics`) on course pages. Report the files you
created, the check output, and anything you deliberately left out.
