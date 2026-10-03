# Question setup, rounds and simplified review — implementation plan

## Target workflow (agreed)

1. **Questions page → "Set up questions" button** opens a modal.
2. Modal: AI suggests **question styles from the library** for each subtopic of the approved
   taxonomy, and the **target count per subtopic × difficulty** (AI decides; professor does not edit counts).
   Professor approves or skips styles, then clicks **Approve**.
3. Approve saves the setup, starts **round 1 (10 questions)** in the background, and navigates to
   `/courses/[courseId]/review`.
4. Each question: generate for a target (subtopic, difficulty, style) → answer check (existing
   deterministic validator) → difficulty judge → topic judge → custom rule judges. Any failure →
   regenerate with the failure reason; max 3 tries; then **drop** (not stored as a question).
5. Review queue: per question the professor (a) confirms/corrects difficulty, (b) confirms/corrects
   subtopics, (c) accepts/rejects. The judge rail shows only: answer check, difficulty, topic, custom rules.
6. After review: judge agreement is recorded from the *observed* corrections; rejected styles are
   weighted down for that cell; accepted questions become examples for that cell.
7. Review queue → **"Generate next round"** button: 10 more, only for cells still below target.

Out of this plan (later milestone): trusted-judge auto-accept + 10% audit (steps 16–18),
look-alike filter, live student refill.

## Current state (verified 2026-10-03)

- Generation targets a book **section**, model self-classifies subtopic (`app/generation/spec.py:37`,
  `prompts.py:13`). No style concept anywhere.
- Retry loop exists (`app/generation/attempts.py:178`, `MAX_GENERATION_ATTEMPTS=3`) but only on
  deterministic/claim failures; judges run after and never trigger retry; after 3 fails the question
  is stored anyway.
- Closest to cell-filling: `run_generation_for_gaps` (`app/web/routes/api/coverage.py:139`).
- Judges: 4 fixed metrics (`JudgeMetricId`, `app/domain/enums.py:265`), run in
  `PedagogicalJudge.evaluate` (`app/evaluation/service.py:167`). No custom judges.
- Answer check exists: `DeterministicQuestionValidator` (`app/validation/service.py:15`) +
  `check_gradable`.
- Review submit (`ReviewRequest`, `app/web/routes/api/schemas.py:1244`) has no difficulty/subtopic
  correction; attribution is inferred from reason codes (`app/feedback/outcomes.py:140`).
- Review UI: `frontend/src/app/courses/[courseId]/review/` — `JudgeRail` shows 4 `MetricCard`s,
  `ReviewActionBar` has 14 reason checkboxes.
- Setup prototype (all mock): `frontend/src/app/experiments/question-setup/` — `step-styles.tsx`,
  `example-question.tsx`, `badges.tsx`, `plan.ts` are reusable.
- Generation is synchronous; Next `/api/*` proxy has a timeout (see memory) → rounds must run in background.
- Migrations: Alembic `app/persistence/migrations/versions/0001–0004`.

## Decisions

- **Do not shrink `JudgeMetricId`.** Stored rows and calibration depend on it. Add a setting
  `judge_metrics_enabled` (default `difficulty,subtopic`) so ISSUES/GENERATABILITY stop running for new
  questions; calibration already skips metrics a judge didn't answer.
- Custom rule judges live in their own table and their own result field, not the enum.
- Reason checklist removed from the review bar; reject takes an optional one-line comment.
  **Edit stays** as a secondary action (existing feature, not dropped).
- Style library is curated code data (Python first), versioned in repo: `app/styles/python.py`.
  Seeded from `mock-python.ts` templates. Not mock: it is the library content.

## Phase 0 — contracts (one agent, sequential, must land first)

Everything shared, so Phase 1 agents touch disjoint files.

- `app/persistence/models.py` + migration `0005_question_setup.py`:
  - `QuestionSetupRow` (curriculum_version_id, approved style ids per subtopic JSON, cell targets JSON, created_at)
  - `GenerationRoundRow` (id, setup_id, number, status `queued|running|done|failed`, requested, produced, dropped, error)
  - `CustomJudgeRow` (curriculum_version_id, rule_text, kind `llm|pattern`, pattern?, enabled)
  - `QuestionRow`: `style_id`, `round_id`, `target_subtopic_id` (nullable)
  - `ProfessorReviewRow`: `corrected_difficulty`, `corrected_subtopic_ids` (nullable)
  - `QuestionEvaluationRow` (or JSON on it): `custom_results`
- `app/web/routes/api/schemas.py`: request/response models for all endpoints below.
- Endpoint stubs (raise 501) registered in `app/web/routes/api/__init__.py` (`_professor_only`):
  - `GET  /api/styles?subject=` — library
  - `POST /api/setup/suggest` — `{curriculum_version_id}` → per subtopic: suggested style ids + reason, cell targets
  - `POST /api/setup` — save approved setup, create + start round 1 → `{setup_id, round_id}`
  - `GET  /api/setup?curriculum_version_id=` — current setup
  - `POST /api/rounds` — next round for current setup → `{round_id}`
  - `GET  /api/rounds/{id}` — status/progress
  - `GET/POST/PATCH /api/custom-judges`
  - `ReviewRequest` gains `corrected_difficulty`, `corrected_subtopic_ids`
- `frontend/src/lib/api/` types + hooks for all of the above (`queries.ts`, `qk` keys).
- Gate: `pytest`, frontend typecheck + `biome lint` + vitest pass; migration upgrades the existing DB.

## Phase 1 — five parallel agents (worktree each, disjoint files)

**A. Style library + suggestion (backend)** — `app/styles/` (new), setup routes
- `app/styles/schema.py` `QuestionStyle` (id, subject, name, summary, question_type, difficulty_range,
  checked_by, applies_to hints, two example questions); `app/styles/python.py` ~10 styles.
- `suggest_setup(curriculum)`: one structured LLM call over subtopics × library → style ids per subtopic
  with reason; cell targets bounded 1–6 (default `MIN_QUESTIONS_PER_CELL`). Validate ids against library.
- `POST /api/setup` persists and calls B's `start_round(setup_id)`.
- Tests with `tests/llm_fakes.py`.

**B. Round generation pipeline (backend)** — `app/generation/rounds.py` (new), `attempts.py`, `spec.py`, `prompts.py`
- `QuestionSpec` gains `target_subtopic_id`, `style_id`; prompt states the target subtopic and the style;
  section chosen by embedding retrieval like `run_generation_for_gaps`.
- Retry loop: after deterministic checks pass, run enabled judges + custom judges (from C's
  `run_custom_judges`); failure reason → `build_correction`; max 3; on final failure **drop** and count.
- `start_round` / `next_round`: pick 10 targets from cells below target (approved count + pending),
  choose style per cell by weight (each reject of that style in that cell ×0.5, floor excluded at 2 rejects),
  add up to 2 accepted questions of that cell as examples. Run in background (FastAPI `BackgroundTasks`
  or thread), update `GenerationRoundRow` progress.
- Tests: retry-on-judge-fail, drop after 3, cell selection, style weighting.

**C. Review backend + judges** — `app/feedback/`, `app/evaluation/service.py`, `app/evaluation/custom.py` (new), custom-judge routes
- Store corrections; attribution becomes **observed**: difficulty judge at fault iff its value ≠
  `corrected_difficulty`; subtopic judge at fault iff its set ≠ `corrected_subtopic_ids`. Fall back to
  reason inference when corrections absent (old rows).
- `judge_metrics_enabled` setting honoured in `PedagogicalJudge.evaluate`.
- `run_custom_judges(question, rules)`: `pattern` rules = regex/AST check on code; `llm` rules = one yes/no
  call per rule.
- Custom judges CRUD routes.
- Tests: observed attribution, enabled-metrics filter, custom judges.

**D. Setup modal (frontend)** — `frontend/src/app/courses/[courseId]/questions/setup/` (new), header button in `questions-browser.tsx`
- Header button "Set up questions" (disabled with hint when no approved taxonomy).
- Dialog (taxonomy-builder size, mounted conditionally): loading → per topic/subtopic suggested styles
  (reuse `step-styles`, `example-question`, `badges` moved out of experiments) with approve/skip →
  read-only target summary → Approve → `POST /api/setup` → `router.push(toCourse("/review"))`.
- Vitest for the modal flow with mocked hooks.

**E. Review queue (frontend)** — `frontend/src/app/courses/[courseId]/review/`
- Judge rail: answer check, difficulty, topic, custom rules only.
- Difficulty: segmented Easy/Medium/Hard preset to the judge's value. Subtopics: multi-select from
  the approved taxonomy preset to the judge's set. Accept / Reject (+ optional comment). Edit stays secondary.
- Header: "Generate next round" button → `POST /api/rounds`; round progress strip polling
  `GET /api/rounds/{id}` while running; queue refetches when done.
- Vitest for corrections payload and button.

Dependencies: B calls C's `run_custom_judges` and A calls B's `start_round` — both fixed signatures in
Phase 0 stubs, so agents code against the stub.

## Phase 2 — integrate + verify (one agent)

Merge worktrees; run `pytest`, typecheck, `biome lint`, vitest; end-to-end in Chrome on Python sample:
setup → round 1 lands in queue → correct one difficulty, reject one → next round → confirm rejected style
weighted down and attribution rows observed. Record in `docs/` + commit.
