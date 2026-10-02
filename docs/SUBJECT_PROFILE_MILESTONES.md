> **Superseded** by `docs/GENERIC_ASSESSMENT_MILESTONES.md`: the subject is now a property of the course
> (ADR-051/054), not one per database. Kept for its inventory of Python-specific code.

# Subject profile — making the trainer generic beyond Python

Goal: one deployment can run for any subject taught from a textbook (statistics,
biology, law...), not only introductory Python. **Scope of "generic" here: the
subject, not the programming language.** Code-executing question types stay Python-only.

`docs/MILESTONES.md` still holds the unfinished coverage plan (its m5), so these
milestones are prefixed `g` to avoid two different `m1`s. `start g1` / `verify g1`.

## What is actually Python-specific (inventory, with evidence)

| Layer | Where | Verdict |
|---|---|---|
| Generator system prompt | `app/generation/principles.py:5-7` ("introductory-Python", "untaught Python feature") | text |
| Judge system prompts | `app/evaluation/prompts.py:55,68,89,112` (module-level f-strings) | text |
| Code-shaped wording with **no** "Python" in it | `app/evaluation/prompts.py:57,61` (`incorrect_tests`/`poor_tests` in the issue guide and `JUDGE_ISSUE_CODES`), `:71-72` ("its code runs and its tests execute"), `:116` ("professional programmer"), `:127` ("amount of code shown"), `:147` (generatability: "a section with no executable code") | text, but needs **conditional fragments**, not a name swap |
| Judge-learning prompt | `app/evaluation/judge_learning.py:57` | text |
| Authoring prompts | `app/curriculum/authoring.py:148,225-228`, `app/ingestion/authoring.py:118-120,203-206` | text |
| App description, book docstring | `app/main.py:55`, `app/domain/books.py:272` | text |
| Frontend strings | `lib/navigation.ts:55,69`, `questions-browser.tsx:610`, `student-session-screen.tsx:939` ("Your Python") | text |
| `multiple_choice`, `true_false` validators | `app/validation/type_checks.py:47,80` — already `del runner` | **already generic** |
| Code-based types | `output_prediction`, `code_completion`, `debugging`, `parsons`, `coding` | Python-only, gate them |
| Code execution | `validation/runner.py:79-100` (`sys.executable -I`), `type_checks.py:36,216` (`ast.parse`/`compile`), `adaptive/scoring.py:204` (runs the *student's* code) | Python-only, **out of scope** |
| PDF/JSON ingestion, retrieval, taxonomy, BKT, coverage, review queue | no `python` mention in `app/ingestion/pdf`, `app/adaptive`, `app/retrieval`, `app/coverage` | **already generic** |
| Coverage bulk generation | `app/web/routes/api/coverage.py:170` uses `MULTIPLE_CHOICE` only | already generic |
| `@codemirror/lang-python` | in `package.json`, imported nowhere under `src/` | dead dependency, no work |

## Shared design decisions (apply to every milestone)

- **One subject per database, chosen by config.** `SUBJECT_PROFILE=python` (default).
  Not stored per curriculum version. Reasons, all verified: `type_instructions` has a
  unique row per question type (`persistence/models.py:761`), `judge_prompts` a unique
  row per metric (`:864`), and ADR-008 forbids altering existing tables, so scoping
  those per subject would need sibling tables plus a rewrite of the personalization and
  judge-learning paths. A second subject = a second database. Multi-subject-per-database
  is Deferred, with its cost.
- **A profile is a data file, not code.** `app/subjects/profiles/<id>.json`, validated by
  a frozen pydantic `SubjectProfile`. Adding a subject = adding one file. Fields carry
  the exact phrases the shipped prompts use (e.g. `course_adjective: "introductory-Python"`),
  so Python's values reproduce today's text.
- **The Python profile must reproduce current output byte for byte.** The first act of g1
  is to snapshot today's prompts into a golden file *before* refactoring; the refactor is
  correct only if that file still matches. This also keeps `effective_rubric_version`
  unchanged for Python, so stored evaluations stay valid.
- **Existing rows are never migrated.** Professor-edited judge prompts and learned type
  instructions live in the database and keep overriding the shipped text. They are
  subject-specific by nature, which is why the guard below exists.
- **Guard against mixing.** A new `app_meta` table (new tables are free) records the
  profile id on first start. Starting with a different `SUBJECT_PROFILE` against that
  database fails fast with "use a new DATABASE_URL". **Legacy databases have no row:** if
  the database already holds books, questions, `judge_prompts` or `type_instructions`,
  the missing row means `python`, never "adopt whatever is configured", or the guard
  protects nothing on the one database that matters. *Decision, default fail-fast; a
  warning-only variant is a one-line change.*
- **The profile owns the list of enabled question types (data, in g1); g2 only enforces
  it.** There is no separate `executor` field: "executes code" is derived from whether any
  enabled type is code-based. The judge and generator prompts switch their code-shaped
  fragments on that derived flag.

## Preconditions before `start g1`

- **Clean tree.** `main-2` currently holds another session's uncommitted work (staged
  deletion of `frontend/src/app/instructions/` and `docs/images/instructions.png`, edits
  to `frontend/src/lib/api/types.ts`, `curriculum/new/`). Land or park it first, or g3's
  `api:types` regeneration will clobber it.
- **Re-verify the type-instruction premise.** That session is removing the Instructions
  page; the backend (`app/personalization/instructions.py`, `routes/api/instructions.py`)
  still exists. If it is removed too, the "unique row per type" argument weakens (the
  `judge_prompts` argument still holds) and the plan should be re-read, not assumed.
- **Client config stays in `GET /api/config`.** `ConfigResponse.question_types` already
  exists for "forms without hard-coding enums" (`schemas.py:119-134`); gating filters that
  list and adds `subject`. No new endpoint.
- **Live LLM runs spend API budget.** Nothing here requires one except the optional live
  check at the end of g4; stop and check in before it.

---

## g1 — Subject profile drives every prompt (Python unchanged)

**Deliverable.** `SUBJECT_PROFILE` selects a profile; the generator, the four judges, the
judge-learning prompt and both authoring prompts render from it. Two profiles ship:
`python` (identical to today) and `statistics` (proves the parametrization).

**Acceptance criteria.**
- `tests/golden/python_prompts.json` is captured from the **unmodified** code first and
  holds every system prompt (generator, four judges, judge-learning, both authoring
  prompts, the document-guide example) plus one rendered generator user prompt from a
  fixed fixture. With `SUBJECT_PROFILE=python` all of it matches exactly.
- With `SUBJECT_PROFILE=statistics` no prompt contains "Python", each names the subject,
  **and none mentions code, tests, programs or programmers**; the issue guide and
  `JUDGE_ISSUE_CODES` omit `incorrect_tests` / `poor_tests`. (A "no Python" check alone
  would pass while the judges still talk about code, which is the failure that matters.)
- A profile file with an unknown question-type id, no enabled type, or a missing field
  fails at startup with the file name and field, not at first request.
- `.env.example` documents `SUBJECT_PROFILE`, and `docker-compose.yml` passes it through.
- `effective_rubric_version` is unchanged for `python` and different for `statistics`.
- Editing a judge prompt (`JudgePromptRow`) still overrides the shipped text under both.
- `app_meta` records the profile on first start; starting with a different one fails with
  a message naming both ids.
- `GET /api/config` returns `subject: {id, label}`; `GET /api/health` returns
  `subject_label` (the landing page needs it unauthenticated in g3).
- ADR-050 added to `docs/DECISIONS.md` recording "one subject per database" and why.

**Validation.**
```
.\.venv\Scripts\python.exe -m pytest tests/test_subject_profile.py tests/test_evaluation_service.py tests/test_generation_base.py -q
$env:SUBJECT_PROFILE="statistics"; .\.venv\Scripts\python.exe -m scripts.show_prompts   # no "Python" in output
```

**Touches.** new `app/subjects/`, `app/config.py`, `app/generation/principles.py`,
`app/generation/prompts.py`, `app/evaluation/prompts.py` (constants become functions of a
profile), `app/evaluation/judge_prompts.py`, `app/evaluation/judge_learning.py`,
`app/curriculum/authoring.py`, `app/ingestion/authoring.py`, `app/persistence/models.py`
(new `AppMetaRow`), `app/web/routes/api/system.py`, `.../schemas.py`, `docs/DECISIONS.md`,
new `tests/test_subject_profile.py`, `tests/golden/`, `scripts/show_prompts.py`.

**Not in this milestone.** No question-type gating. No frontend change. No new question
types. No per-curriculum-version profile.

---

## g2 — Question types follow the profile

**Deliverable.** A profile lists its enabled question types and an optional executor.
Under `statistics` the Generate screens offer only multiple choice and true/false; the
API refuses the rest.

**Acceptance criteria.**
- `python` enables all seven types (unchanged). `statistics` enables `multiple_choice`
  and `true_false` only (the field itself is defined in g1; this milestone enforces it).
- A generation request for a disabled type returns 422 naming the type and the profile.
- `GET /api/config.question_types` lists only enabled types; the single-question, bulk
  and spec-sheet screens and the Questions filter show only those.
- Existing questions of a now-disabled type stay visible and reviewable; nothing is deleted.
- `LocalCodeRunner` is not needed on any request path when `executor` is null.

**Validation.**
```
.\.venv\Scripts\python.exe -m pytest tests/test_subject_profile.py tests/test_generation_batch.py tests/test_api.py -q
cd frontend; pnpm exec vitest run src/app/questions; pnpm exec biome lint src/app/questions
# then: SUBJECT_PROFILE=statistics, open /questions/generate, confirm two formats offered
```

**Touches.** `app/subjects/profile.py`, `app/generation/spec.py`, `app/generation/batch.py`,
`app/web/routes/api/schemas.py` (`ConfigResponse` and the request validators near `:2100`),
`frontend/src/app/questions/generate/components/{format-picker,spec-sheet-row,generate-controls}.tsx`,
`frontend/src/app/questions/questions-browser.tsx`, `frontend/src/lib/api/types.ts`
(regenerate with `pnpm run api:types`).

**Not in this milestone.** No new question type. No other-language executor.

---

## g3 — Frontend and landing page stop saying "Python"

**Deliverable.** No hardcoded subject in the UI. Static nav summaries are neutral; the
student answer label and the questions page read the subject; the landing page shows
the running subject profile in its status box.

**Acceptance criteria.**
- `lib/navigation.ts` summaries and `questions-browser.tsx:610` contain no subject word.
- `student-session-screen.tsx:939` uses the profile (label for code types only).
- Landing hero and Limits are subject-neutral; a "Subject" row in the status box shows
  `subject_label` from `/api/health` (idle while unreachable).
- The landing page's "Limits" bullets stay true under both profiles (the sandbox and
  OpenRouter bullets apply to both; the "introductory Python" bullet is removed).
- `grep -ri python frontend/src` returns only fixtures, tests and the experiments prototypes.

**Validation.**
```
cd frontend; pnpm exec tsc --noEmit; pnpm exec biome lint src; pnpm exec vitest run
Get-ChildItem -Recurse src -Include *.ts,*.tsx | Select-String -Pattern python -CaseSensitive:$false
```
plus a Chrome look at `/`, `/questions`, and a student session under each profile.

**Touches.** `frontend/src/lib/navigation.ts`, `.../questions/questions-browser.tsx`,
`.../students/join/session/[training_session_id]/student-session-screen.tsx`,
`frontend/src/app/page.tsx`, `frontend/src/components/landing/setup-status.tsx` (+ its test).

**Not in this milestone.** No layout redesign. No theming per subject.

---

## g4 — Prove it end to end on a second subject

**Deliverable.** A non-programming sample (statistics) goes through the whole pipeline in
one automated test, and the repo ships sample files anyone can import.

**Acceptance criteria.**
- `docs/book_document_statistics_example.json` and `docs/taxonomy_statistics_example.json`
  exist, marked as **sample content** (`TODO(real):` replace with a genuine textbook).
- One test, fake LLM, `SUBJECT_PROFILE=statistics`: import book, approve curriculum, generate
  MC and TF, deterministic checks pass, judges run with statistics prompts, freeze a set,
  student answers, BKT mastery moves.
- The same test file runs the Python path and both stay green.
- README gains a short "Using it for another subject" section (copy a profile file, set
  `SUBJECT_PROFILE`, start with a fresh database).
- **Optional, needs your go:** one live run with the real LLM on the statistics sample
  (spends API budget) to eyeball generation and judge quality.
- **What this proves, and what it does not.** The automated test (built on the existing
  `tests/llm_fakes.py`) proves the plumbing is subject-independent. It says nothing
  about whether generated statistics questions or judge verdicts are *good*; only the live
  run and a professor's labelled reviews can. Do not call it "generic" beyond that.

**Validation.**
```
.\.venv\Scripts\python.exe -m pytest tests/test_subject_end_to_end.py -q
.\.venv\Scripts\python.exe -m pytest -q          # whole suite
```

**Touches.** `tests/test_subject_end_to_end.py`, `docs/*_statistics_example.json`, `README.md`,
`docs/LOCAL_DEVELOPMENT.md`, `docs/PROJECT_NOTES.md` (also fix its stale "no PDF parser" line).

**Not in this milestone.** No judge re-calibration for the new subject (see Deferred).

---

## g5 (optional, decide after g4) — One deterministic non-code question type

MC and TF alone make thin practice for maths and science. Recommend **`numeric_answer`**
(answer plus tolerance): discrete scoring, deterministic validation, no LLM grader.
Adds a `QuestionType` value (stored as a string via `StrEnumType`, so no schema change),
a draft schema and instruction in `generation/`, a validator in `type_checks.py`, a scorer
in `adaptive/scoring.py`, and render/answer UI. Deliberately **not** short free-text
answers: those need an LLM grader, whose reliability and cost are a separate decision.

---

## Sequence

`g1 → g2 → g3 → g4 → (g5)` — strict; g2 needs g1's profile, g3 needs g1's `/api/health`
and g2's config, g4 needs all three.

**Active: none.** Run `start g1` to implement, `verify g1` to check it. One milestone per
session; commit before the next.

### Deferred (not milestones)

- **Several subjects in one database.** Needs sibling tables for learned type instructions
  and judge prompts, and profile scoping through calibration, personalization and
  judge-learning. Large; only if you truly need one instance to serve several courses.
- **Other programming languages.** An executor interface plus per-language runners, and a
  real sandbox first: today's runner is explicitly not safe for untrusted code
  (`DECISIONS.md`, near line 636) and student code is executed at scoring time. Self-hosted
  Judge0 or Piston are candidates to evaluate first (not yet checked).
- **Judge re-calibration per subject.** Alignment was measured on Python
  (`JUDGE_ALIGNMENT_EXPERIMENTS.md`); it does not transfer. Needs labelled reviews from a
  professor in the new subject, through the existing `calibration/` module.
- **LLM-graded short answers.**
