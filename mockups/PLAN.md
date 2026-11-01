# Clickable product mockup — plan

A clickable mockup of the whole product (docs/PRODUCT_ROADMAP.md, F1–F11) in plain HTML
with mock data. It needs no backend, no build and no server: double-click `index.html`.
It's the agreed picture of the product; the Next.js app (`frontend/`) and the backend
are implemented against it later.

## Tooling (no build step)

| Piece | Choice | Why |
|---|---|---|
| Components | [Basecoat](https://basecoatui.com) 1.0.2 via CDN | shadcn/ui components as plain HTML classes (`btn`, `card`, `table`, sidebar, tabs, dialog, toast…). The real app is built on shadcn, so mockup and app share the same components. |
| Theme | `assets/theme.css`, copied from `frontend/src/app/globals.css` | Basecoat reads the same `--background`/`--primary`/`--sidebar-*` variables. The mockup looks like the real app, not a generic template. |
| Layout utilities | Tailwind v4 browser CDN (`@tailwindcss/browser`) | Spacing and grids without writing CSS. |
| Interactivity | [Alpine.js](https://alpinejs.dev) via CDN | Tabs, filters, wizard steps, "approve" buttons changing state. No framework code. |
| Mock data | `assets/mock-data.js` (`window.MOCK = {...}`) | A `.js` file, not `.json`: `fetch()` of local JSON fails on `file://`, while a script tag works. Every value is invented and marked `TODO(real)`. |
| Shared chrome | `assets/layout.js` | Injects the sidebar and top bar from one nav list, so pages don't copy the sidebar. |

Considered and not chosen: Figma/Penpot (not clickable with real-looking data, and the team
can't reuse it as code), Pines/Pinemix (Tailwind+Alpine, but not shadcn-shaped, so the
look would diverge from the app), and a second Next.js app (needs a build, which is what
we're avoiding).

## Mock world (one consistent story across all pages)

- Professor **Dr. Maya Chen**, plus a co-instructor, for collaborator screens. TODO(real)
- Course A: **Intro to Python (CS 135)**, fully set up: 2 books, 12 topics / 48 subtopics,
  ~60 questions in mixed states, 1 frozen set, 2 class sections, 28 students.
- Course B: **Intro Statistics (STAT 152)**, halfway through setup (shows the checklist
  and the non-Python subject, F3): 1 book uploaded, AI-drafted taxonomy waiting for approval.
- A running generation job and one failed job (F4), and the month's LLM spend near its cap (F8).

## Pages — 33 in total (6 + 5 + 13 + 4 + 1 + 4)

`Now` = the equivalent route in `frontend/` today (the mockup page reuses its layout);
`new` = doesn't exist yet.

### A. Public and account (6)

| # | Page | Feature | Now |
|---|---|---|---|
| A1 | Landing | F10 | `/` (uncommitted landing work) |
| A2 | Sign up | F2 | new |
| A3 | Log in | F2 | `/login` |
| A4 | Forgot / reset password | F2 | new |
| A5 | Accept invite (co-instructor) | F2 | new |
| A6 | Verify email / check your inbox | F2 | new |

### B. Professor workspace, outside a course (5)

| # | Page | Feature | Now |
|---|---|---|---|
| B1 | My courses (home) | F2, F5 | `/dashboard` (single-course today) |
| B2 | New course: name, code, subject, question types | F3, F5 | new |
| B3 | Jobs (running / done / failed AI work, retry) | F4 | new |
| B4 | Usage and limits (LLM spend per course, monthly cap) | F8 | new |
| B5 | Account settings (profile, password, team) | F2 | new |

### C. Inside a course: setup and content (13)

Course-scoped sidebar. The order of the items *is* the F5 guided flow: each item shows a
done/next badge, and the overview is the checklist.

| # | Page | Feature | Now |
|---|---|---|---|
| C1 | Course overview: setup checklist + key numbers | F5 | new (parts of `/dashboard`) |
| C2 | Materials: books list, upload PDF/JSON, import status | F4, F5 | `/books` |
| C3 | Book detail: chapters, sections, structure confidence | — | `/books/[id]` |
| C4 | Section reader | — | `/books/[id]/sections/[id]` |
| C5 | Taxonomy: versions, active version, "Draft with AI" / import / build | F6 | `/curriculum` |
| C6 | Taxonomy builder / editor | — | `/curriculum/versions/[id]` |
| C7 | AI-drafted taxonomy review: accept / edit / discard rows, approve | F6 | new |
| C8 | Coverage: subtopic × difficulty grid, "Generate for gaps" | F4 | `/coverage` |
| C9 | Generate: single and bulk spec sheet | F3 | `/questions/generate`, `/single` |
| C10 | Question bank: filters, states, duplicate flags | — | `/questions` |
| C11 | Question detail: surface, checks, judges, history | — | `/questions/[id]` |
| C12 | Review queue: approve / reject / edit with judge verdicts | — | `/review` |
| C13 | Alignment: judge-vs-professor agreement, judge prompts, learned rules | F9 | `/judges` |

### D. Inside a course: teaching (4)

| # | Page | Feature | Now |
|---|---|---|---|
| D1 | Question sets: freeze, compare coverage, publish | — | `/students` (freeze part) |
| D2 | Classes: sections, join code/link, roster restriction | F7 | `/students` |
| D3 | Students: roster, mastery per topic, export CSV, reset/remove | F7 | `/students/roster` |
| D4 | Student detail: mastery over time, attempts, weak subtopics | F7 | new |

### E. Course settings (1 page, tabs)

| # | Page | Feature | Now |
|---|---|---|---|
| E1 | Settings: General · Subject & question types · Collaborators · LMS (LTI) · Danger zone | F3, F2, F11 | new |

### F. Student app (4, separate minimal chrome, phone-first)

| # | Page | Feature | Now |
|---|---|---|---|
| F1s | Join: code or link, name/email | F7 | `/students/join` |
| F2s | My courses and progress | F7 | new |
| F3s | Practice session: question, submit, feedback, mastery update | — | `/students/join/session/[id]` |
| F4s | Session summary: what improved, what's next | — | new |

Not mockup pages: F1 (migrations) has no UI. Platform-admin screens are deferred until
there's more than one institution.

## Build order (one step per session, review between)

| Step | Pages | Done when |
|---|---|---|
| mk1 | Shell: theme, mock data, layout.js, `index.html` page index + A1–A6 | Opens from `file://` with no console errors; looks like the real app's theme |
| mk2 | B1–B5, C1, E1 | Can create "a new course" (mock) and land on its checklist |
| mk3 | C2–C8 | Stats course: upload → AI draft → approve taxonomy → coverage gaps |
| mk4 | C9–C13 | Generate → bank → review → alignment, with state changing on click |
| mk5 | D1–D4, F1s–F4s | Freeze → share code → student practises → professor sees mastery |
| mk6 | Walkthrough | One guided click-path through the whole story; 3 people try it cold |

## Not doing

- No backend calls and no persistence beyond the open tab (Alpine state resets on reload).
- No pixel polish past what Basecoat + the app theme give; the goal is flow and content.
- No mobile layout for professor pages beyond "doesn't break"; the student app is phone-first.
- No changes to `frontend/`.

---

# Phase 2 — pages a professor needs to run a semester

Phase 1 covers building a question bank. It doesn't cover running a course with it: nothing
ties practice to the syllabus, nothing counts toward a grade, and nothing tells the professor
what to do in Monday's lecture. The pages below come from walking one professor (Maya Chen,
CS 135, 2 sections, 1 TA) through a whole term.

## The term, from the professor's side

| When | What she does | How often | Page |
|---|---|---|---|
| August, deciding | Looks at a finished course before uploading anything | once | G0 sample course |
| August, setup | Brings in last year's Canvas quiz questions | once | G6 import |
| August, setup | Maps topics to the weeks of her syllabus | once, then small edits | G1 schedule |
| August, setup | Creates the weekly practice assignments that count for 5% of the grade | once per term | G2, G3 |
| Weekly, Monday, 10 min | Reads what the class got wrong and decides what to reteach | every week | G5 insights, G11 digest |
| Weekly | Handles "this question is wrong" reports from students | 2–3 a week | G7 reports |
| Weekly | Checks who is behind on the assignment; grants an extension | every week | G4 gradebook |
| Before each exam | Builds a review set; exports exam questions, which students must not see in practice | 3 times a term | G8 exam export |
| December | Pushes final practice grades to Canvas; keeps a report for her teaching portfolio | once | G4, G10 |
| Next August | Copies the course into Fall 2027 without starting over | once a year | G9 copy term |

## New pages (G), in priority order

| # | Page | File | What's on it | Why a professor needs it |
|---|---|---|---|---|
| G1 | Schedule | `schedule.html` | Weeks 1–15 as rows, the syllabus dates, and the topics each week opens. A student practises only topics released so far, plus review of earlier ones. Toggle: "Release topics by schedule / all at once". | Without it, week-3 students get Classes and Exceptions, fail them, and the professor gets complaints. |
| G2 | Assignments | `assignments.html` | Table: name, scope (weeks/topics), goal, open and due dates, points, completion %, LMS sync status. | Students do what's graded. This is the adoption lever. |
| G3 | Assignment editor | `assignment.html?id=` | Scope (pick weeks or topics), goal type (reach X% mastery on each topic / answer N questions / N minutes), open, due and late policy (accept until, penalty %), points, which sections. Preview of what a typical student would face. | The goal has to be something she can defend in the syllabus: "reach 70% on Loops", not an opaque score. |
| G4 | Gradebook | `gradebook.html` | Students × assignments: done / in progress / late / not started, score. Per-student extension (accommodations). Export CSV; "Send to Canvas" with last sync time. | Weekly check of who is behind; the end-of-term grade. Extensions for accommodation letters are required, not optional. |
| G5 | Class insights | `insights.html` | "This week": weakest subtopics for the class; for each one, the most-picked wrong answer and how many students picked it ("38% chose `[1, 2, 3]` on aliasing"), one example question, and a "Show in lecture" view (full-screen question, no names). Section filter. Students who haven't started. | Turns practice data into Monday's lecture. None of today's pages answer "what should I reteach?" |
| G6 | Import questions | `import-questions.html` | Upload QTI / Canvas export / CSV → the AI suggests a subtopic for each question → fix the ones it's unsure of → run checks and judges → land in the review queue marked "Imported". | Every professor already has questions. Without import, the tool competes with her own bank instead of using it. |
| G7 | Student reports | `reports.html` | Inbox of "report this question" from students: reason, the student's answer, the question. Actions: dismiss with a reply, edit the question, void it (removes it from sets and gives the attempts back without penalty). | Wrong AI questions will reach students. This is how she keeps trust, and it feeds the generator's learned rules. |
| G8 | Exam export | `exam-export.html` | Pick approved questions by topic and difficulty (or "20 from chapters 1–6, mixed difficulty") → export QTI / Canvas / Word or PDF with answer key. Exported questions are marked "used on an exam" and held out of practice until a date she picks. | Exams are her real deliverable. The holdout keeps exam questions out of what students see in practice. |
| G9 | Copy to a new term | `copy-course.html` | Choose what carries over (taxonomy, approved questions, schedule shifted to the new dates, assignments, judge rules), and what doesn't (students, attempts). | Reused every year. Otherwise, year two means starting from scratch. |
| G10 | Term report | `term-report.html` | Printable: enrolment, practice activity by week, mastery gain vs. practice volume, topics that stayed weak, questions reviewed. | Teaching portfolio, tenure file, a department chair asking "did it help?" |
| G11 | Weekly digest (email) | `email-digest.html` | Rendered email: 3 weakest topics, who hasn't started, reports waiting, questions awaiting review, assignment due. | She won't open a dashboard every week; she will read an email. |
| G0 | Sample course | state in `courses.html` | A read-only "Sample: Intro to Python" course shown to a new account, with "Make my own course". | Deciding to try it should take 2 minutes, not an afternoon of uploading. |

## Changes to existing pages

| Page | Change |
|---|---|
| C1 Course overview | After setup is done, the checklist collapses to one line and the page becomes the in-term home: this week's insight, assignment due, reports waiting, review queue. |
| D3 Students / D4 Student | Assignment status per student; extensions; "notes" (accommodations). |
| E1 Settings · Collaborators | Roles: Co-instructor (everything), TA (review questions, see students and gradebook, handle reports; no settings, no deleting), Grader (gradebook only). |
| F2s Student home | "Due Friday: Loops to 70% — you're at 58%" at the top; practice scope follows the schedule. |
| F3s Practice | "Report this question" on every question; after a wrong answer, a short refresher (from `frontend/src/app/experiments/tutorials-inline`) before the next one. |
| C9 Generate / C10 bank | Questions held for an exam show a lock and "held until Oct 20". |

## Deliberately not planned

- Proctored or timed exams inside the product: the LMS already does this, and exports (G8) cover it.
- Student discussion or chat: Piazza/Ed/the LMS already do this.
- A department or institution admin console: wait until one campus asks.
- SSO and accessibility are required for a campus rollout, but they aren't mockup pages; track them in F2 and F10.

## Build order

| Step | Pages | Done when |
|---|---|---|
| mk7 | G1, G2, G3, F2s change | A professor maps weeks to topics, creates "Week 4: Loops to 70%", and the student home shows it as due |
| mk8 | G4, G5, G7, C1 change, F3s report button | A student reports a question, the professor voids it, and the gradebook and insights update |
| mk9 | G6, G8, G9 | Canvas quiz imported → reviewed → 20 questions exported for the midterm and held out of practice |
| mk10 | G10, G11, G0, Settings roles | Term report prints cleanly; digest email reads well in a plain email client |

---

# Phase 3 — any subject (generation and checking)

A question = stimulus + answer format + verifier. Sections are analysed once at import into
testable units (fact, quantitative relation, procedure, sequence, classification, cause and
effect, code); the unit's kind picks the formats; each format reaches a verification level:
**Proven** (a solution program computed the key) · **Cross-checked** · **Supported** (exact quote
+ blind solvers agree) · **Judged** · **Rubric**. A subject earns levels through a readiness gate
(published exercises with answer keys + mutation tests); a failed sandbox capability switches the
formats that need it off. Shared data: `assets/data-gen.js`.

| Page | Change |
|---|---|
| `subjects.html` (new, workspace) | Subjects × formats × level today; readiness numbers vs bars; sandbox self-test |
| `new-course.html`, Settings › Subject | Subject profile; answer formats with level and why-off; minimum level for graded work |
| `section.html`, `generate.html` | "What's testable in this section"; pick a unit, then a format with its level |
| `question.html`, `review.html`, `questions.html` | How the key was checked (program + output, or quote + solvers); misconception per wrong option; level filter |
| `assignment.html` | Minimum verification level for questions in a graded assignment |
| `alignment.html` | Verifier health: mutation tests caught per verifier |
| `question-types.html` | Six subjects rendered, labelled with the same five levels |

---

# Phase 4 — checking tools (decided)

A course's **checking tools** are the ways it can check answers: Book lookup, Answer matcher, Python
runner (with tests), Numeric checker, Maths engine, Rubric grader, and later SQL engine, Web runner,
Java runner, Logic checker. The generator may write any question one of the course's tools can check;
tools set the trust label (Computed / Quoted / AI-reviewed only / Rubric-graded), not the question
shape. Tools are added, paused or retired, never deleted; each question pins the tool and version that
checked it. The subject is only a label that suggests starting tools. Misconceptions are tags on wrong
options, added after a question is written. The Rubric grader drafts rubrics for the professor to
approve, grades criterion by criterion with quoted evidence, and stays practice-only until calibrated
against her grading. Shared data: `assets/data-tools.js`, `assets/data-rubrics.js`.

| Page | Change |
|---|---|
| Settings › Checking tools | The course's tools, versions, questions using each, pause / turn on, add from the catalogue; no delete |
| New course | Pick starting tools (suggested by subject); subject is a label |
| Generate | Each format shows the tool that will check it; formats without a tool point to Settings |
| Question, review queue, question bank | "Checked by <tool> <version>", pinned; filter and counts by tool |
| Rubrics (new), Alignment, student practice | Rubric drafting and approval, calibration, graded answers; rubric agreement; one written answer for students |
| Checking health (internal) | Per tool: self-test, readiness, courses and questions depending on it |
| Removed | Knowledge map (kinds and wrong-rule templates): out of navigation, files kept |
