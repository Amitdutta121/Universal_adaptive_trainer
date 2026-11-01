# Learning from reviews: generator, then judges — final milestones

Drive with `start mN` / `verify mN`. One milestone per session; commit before the next.
Part A (m1–m7) changes the generator (ADR-063). Part B (m8–m11) changes the judges (ADR-064).
m12 is the end-to-end acceptance run.

## Why

Measured on copies of the dev database (2026-10-07/08; the scripts are ported into `scripts/`
by the milestones below):

- A reject blocks the review screen: `create_review` runs the generator and judge relearn
  (1 to ~35 LLM calls) before it responds (`app/web/routes/api/feedback.py`).
- One adversarial comment ("correct answer must always be option A") became a learned rule
  from a single review; every later question obeyed it (16/16).
- `accepted_examples` finds no example for 90% of targets and does not filter by question
  type (73% of the examples it returns are another type).
- `dedup._embed_text` ignores `content["code"]`; at 0.85 the check catches 2/14 professor
  "too similar" rejects. Dedup does not run on rounds.
- Retry reasons are used once and discarded.
- Judges: of 222 routed reviews, 67 false alarms (judge objected, professor accepted) vs 27
  misses. In rounds a judge-failed draft is retried or dropped and never reviewed, so the most
  common judge mistake is invisible. Judge learning starts only after 5 disagreements and a
  ~16-call held-out gate; in an 18-review simulation no judge learned anything.

## Final architecture (one paragraph)

A review only records (review, outcome, episode) and returns at once. Once per round, before
generating, a background **lesson run** updates memory: **judges first, then the generator**,
and both stay frozen for the round. Memory follows MemAlign: **guidelines** (semantic, edited
not rewritten, active only with ≥ 2 supporting reviews or professor confirmation, comments
treated as evidence, output-contract rules refused) and **episodes** (episodic, reviewed
questions with the professor's verdict, retrieved by type → cell → topic → similarity). The
generator also learns from approved retry fixes, avoids duplicates (code-aware embeddings,
≥ 0.90 retry) and gets one facet per target. Judges get feedback on both sides — reviews plus
an **audit sample** of drafts they rejected — learn difficulty and subtopic from every review,
fail softly when a failure is borderline, and are versioned by memory snapshot.

## Conventions for every milestone

- Tests use injected fake LLM clients / embedders (existing pattern); no API spend in CI.
- Backend gate: `.venv/Scripts/python -m pytest -q` (full suite) plus the milestone's tests.
- Frontend gate (only when frontend changes): `pnpm exec biome lint`, `pnpm exec tsc --noEmit`,
  `pnpm exec vitest run` (repo-wide `pnpm run lint` fails on this checkout).
- Scripts run on a **copy** of `data/adaptive_trainer.db`, never the live file.
- Any step marked **[spends API]** stops and asks before running.

---

# Part A — Generator

## m1 — Reviews return at once; a lesson run starts each round

**Deliverable.** Accept / Reject / Edit make no LLM call; the next question appears at once.
Reviews since the last lesson run are learned at the start of the next round's job, before it
generates; the round strip shows "Applied lessons from N reviews" or the error. Learning logic
is unchanged here (existing `refresh_type_instruction` / `refresh_judge_prompt`), but called
once per affected type / judge per round. This milestone builds the lesson-run slot that
m5, m6 and m11 fill.

**Acceptance criteria**
- `POST /questions/{id}/review` with `reject` makes zero LLM calls (fake client asserts).
- Outcome rows get `lessons_round_id` (NULL = pending).
- Three rejects of one type, then `run_round` → `refresh_type_instruction` called once; all
  three rows marked.
- A failing refresh does not fail the round; the error is on the outcome rows and the round.
- Skip stays enabled while a review saves; the toast no longer promises an immediate refresh.
- ADR-063 status → accepted for this step.

**Validation**
- `pytest tests/test_lessons.py tests/test_review_outcomes.py tests/test_rounds.py -q`
- `pnpm exec vitest run src/app/courses/\[courseId\]/review`
- Manual: reject in the review queue → next question in < 1 s.

**Touches.** `app/web/routes/api/feedback.py`, new `app/feedback/lessons.py`,
`app/generation/rounds.py` (`run_round`), migration `0013_lessons_round.py`,
`ReviewOutcomeRow`, `GenerationRoundRow`, `review-screen.tsx`, `review-verdict-bar.tsx`,
`round-progress.tsx`, `docs/DECISIONS.md`.

**Not in this milestone.** No change to what is learned; no memory tables. Generation outside
rounds uses the rules as of the last round.

---

## m2 — Code-aware duplicate check inside rounds

**Deliverable.** Question embeddings are stored once (`question_embeddings`). The round retry
loop gets a duplicate check: exact normalised match or cosine ≥ 0.90 fails the attempt with
"too similar to: <question>"; 0.75–0.90 keeps it with the existing soft flag; on the last
attempt a duplicate is kept with the flag, not dropped.

**Acceptance criteria**
- `_embed_text` includes `content["code"]`; same stem + different code is not flagged (test).
- Exact duplicate → retry quoting the duplicate (test).
- Fake embedder 0.93 → retry; 0.80 → kept with `QuestionSimilarityRow` (tests).
- Final attempt still ≥ 0.90 → stored with flag (test).
- `scripts/calibrate_dedup.py` prints the threshold table; ≥ 9/14 "too similar" caught at 0.75.
  **[spends API: embeddings, cents]**

**Validation**
- `pytest tests/test_dedup.py tests/test_round_review_safety.py tests/test_rounds.py -q`
- `python scripts/calibrate_dedup.py <db copy>`

**Touches.** `app/web/routes/api/dedup.py` (core moves to `app/retrieval/duplicates.py`),
`app/generation/review.py` (`RoundReview` gets an injected checker — `app.generation` must not
import `app.retrieval`), `app/generation/service.py`, migration `0014_question_embeddings.py`,
`scripts/calibrate_dedup.py`.

**Not in this milestone.** LLM "same concept?" check, facets, cleaning the existing bank.

---

## m3 — Examples of the right type, similarity fallback, "don't repeat" negatives

**Deliverable.** Round examples always match the question type; empty cells fall back to same
topic, then embedding similarity; no near-identical pair; cross-subtopic examples labelled
"style only"; the three nearest existing questions in the cell shown as "already in the bank".

**Acceptance criteria**
- `accepted_examples` filters by question type (regression test).
- Empty cell → two same-type examples (test, fake embedder); no pair > 0.92 (test).
- Target block renders negatives and the cross-subtopic label (prompt snapshot test).
- `scripts/replay_retrieval.py`: coverage ≥ 80%, same type 100%. **[spends API: embeddings]**

**Validation**
- `pytest tests/test_rounds.py -q` plus the prompt test file
- `python scripts/replay_retrieval.py <db copy>`

**Touches.** `app/generation/rounds.py`, `app/generation/prompts.py` (`render_round_target`),
`scripts/replay_retrieval.py`.

**Not in this milestone.** Professor verdicts/comments on examples (m4).

---

## m4 — Episodic memory (shared by generator and judges)

**Deliverable.** `memory_episodes`: one row per review with subject key, question type,
topic/subtopic, the frozen text reviewed, verdict, reasons, comment, corrected difficulty and
subtopics, and **each judge's verdict on that question** (so m11 can reuse the same rows).
Written when the review is saved (no LLM). Generator retrieval reads episodes: approved as
examples (with comment), at most one nearest rejected as "rejected because …". Deleting a
review deletes its episode. Existing reviews are back-filled by the migration.

**Acceptance criteria**
- One episode per saved review; an edit stores the professor's version (tests).
- Retrieval: approved examples + ≤ 1 rejected with reason (test).
- Deleted review → episode gone, never retrieved (test).
- Subject-key scoping: another course's episodes never retrieved (test).
- Back-fill creates one episode per existing review (migration test).

**Validation**
- `pytest tests/test_memory_episodes.py tests/test_rounds.py tests/test_feedback_service.py -q`

**Touches.** New `app/memory/` (`episodes.py`, repository), migration `0015_memory_episodes.py`,
`app/feedback/service.py`, `app/generation/rounds.py`.

**Not in this milestone.** Judges do not read episodes yet (m11).

---

## m5 — Generator guidelines: edited, two reviews, injection-proof, drift check

**Deliverable.** `memory_guidelines` (target = `generator:<type>` now, `judge:<metric>` in m11)
replaces the rewritten rule list. The lesson run asks for edit operations (add, merge, support,
retire) citing review ids. Active only with ≥ 2 distinct supporting reviews or professor
confirmation; pending ones are not sent. Comments are quoted evidence; a deterministic filter
refuses output-contract guidelines (answer position, option count, fields). A per-round drift
check (answer-position spread, option count, stem length) warns on the round strip. The
instructions page lists pending/active guidelines with confirm / delete.

**Acceptance criteria**
- One review cannot activate a guideline; a second agreeing one does (tests).
- "Always option A" and variants are refused (tests).
- Migration: existing rules with ≥ 2 review ids → active, else pending.
- 5/5 answers at one index → drift warning (test).
- `scripts/simulate_review_loop.py` (adversarial): option-A rate ≤ 40% in rounds 2–4 (today
  100%); compliance with the scripted standard ≥ today's. **[spends API: ~$1–2]**

**Validation**
- `pytest tests/test_memory_guidelines.py tests/test_lessons.py tests/test_subject_personalization.py -q`
- `python scripts/simulate_review_loop.py <db copy> out.json`
- Manual: instructions page shows pending vs active; confirm activates.

**Touches.** `app/memory/guidelines.py`, migration `0016_memory_guidelines.py`,
`app/personalization/instructions.py` (replaced by the distiller), `app/generation/base.py`
(`_type_instruction`), `app/feedback/lessons.py`, instructions page, `round-progress.tsx`,
`scripts/simulate_review_loop.py`.

**Not in this milestone.** Judge guidelines (m11).

---

## m6 — Approved retry fixes become generator lessons

**Deliverable.** For a round question the professor **approved**, each failed attempt and its
reason (already on `generation_attempts`) become a retry episode ("avoid: …, because …"),
retrieved for the same type and subtopic. Rejected questions contribute nothing. The round
strip shows first-attempt pass rate.

**Acceptance criteria**
- Approved with a failed attempt → one retry episode; rejected → none (tests).
- Retry episodes retrieved for same type/subtopic (test).
- First-attempt pass rate in the rounds API and on the strip (tests).
- Simulation: first-attempt pass rate round 4 ≥ round 1. **[spends API]**

**Validation**
- `pytest tests/test_memory_episodes.py tests/test_lessons.py tests/test_rounds.py -q`

**Touches.** `app/memory/episodes.py`, `app/feedback/lessons.py`, `app/generation/rounds.py`,
rounds API schema, `round-progress.tsx`.

**Not in this milestone.** Facets.

---

## m7 — Facets per subtopic

**Deliverable.** One cached LLM call per subtopic lists 4–8 facets. Round planning gives each
target a facet its cell has not covered (counted from approved questions); a fully covered cell
is reported as saturated instead of generated again. The facet appears in the target block.

**Acceptance criteria**
- Facets generated once per subtopic and reused (test).
- Two targets of one cell in a round never share a facet (test).
- Saturated cell → no target, reported on the round (test).
- Simulation: soft duplicate flags per round fall versus m6's run. **[spends API]**

**Validation**
- `pytest tests/test_rounds.py tests/test_facets.py -q`

**Touches.** `app/generation/rounds.py` (`plan_targets`), new `app/generation/facets.py`,
migration `0017_subtopic_facets.py`, `app/generation/prompts.py`, round strip.

**Not in this milestone.** Cleaning duplicates already in the bank.

---

# Part B — Judges

## m8 — Judge scorecard: see how each judge is doing

**Deliverable.** A per-judge scorecard (issues, difficulty, subtopic) on the Judges page and in
`GET /api/judges/scorecard`: agreement with the professor on the latest reviews with a 95%
range, Cohen's κ, misses, false alarms, flag rate, and — from rounds — how many retries and
dropped drafts each judge caused. Difficulty and subtopic agreement use the professor's
confirmed values on **every** review, not only disagreements. No learning changes; this is the
measuring stick for m9–m12.

**Acceptance criteria**
- Agreement, κ and Wilson 95% range computed per judge (unit tests on fixed data).
- Difficulty/subtopic scored against `corrected_difficulty` / `corrected_subtopic_ids` (test).
- Retries and drops attributed to the judge whose check failed (test from `generation_attempts`).
- Scorecard on the dev DB shows false alarms per judge (manual check; no API).

**Validation**
- `pytest tests/test_judge_scorecard.py tests/test_coverage.py -q`
- Manual: Judges page → scorecard table with ranges.

**Touches.** New `app/calibration/scorecard.py` (reuses `app/calibration` agreement code),
`app/web/routes/api/` judges route + schema, Judges page component.

**Not in this milestone.** Any change to how judges decide or learn.

---

## m9 — Audit sample: the professor sees some drafts the judges rejected

**Deliverable.** Each round keeps up to 2 drafts that a judge failed (the final failed attempt
of a dropped target, or a failed attempt of a kept one) and puts them in the review queue
marked "A judge rejected this — do you agree?". The professor answers agree / disagree (and
may comment). The answer is stored as a feedback record for that judge (false alarm or
confirmed), and as an episode. Audit drafts never become usable questions unless the professor
approves them.

**Acceptance criteria**
- A round with a dropped target stores ≤ 2 audit drafts, with the failing judge and its reason
  (test).
- Audit items appear in the queue, clearly marked, separate from normal items (API + UI test).
- "Disagree" records a false alarm for that judge; "agree" a confirmed objection (test).
- Audit verdicts show on the m8 scorecard (test).
- Audit items are excluded from the bank unless approved (test).

**Validation**
- `pytest tests/test_audit_sample.py tests/test_review_queue.py tests/test_rounds.py -q`
- `pnpm exec vitest run src/app/courses/\[courseId\]/review`
- Manual: generate a round with a drop → audit card in the queue.

**Touches.** `app/generation/service.py` (keep audit drafts), `app/generation/rounds.py`,
`QuestionRow` status / flag for audit drafts (migration `0018_audit_drafts.py`),
`app/feedback/service.py`, `app/feedback/outcomes.py`, review queue API, review screen.

**Not in this milestone.** Soft-fail; judge memory.

---

## m10 — Soft-fail when a judge failure is borderline

**Deliverable.** Inside the round retry loop, only a **clear** judge failure causes a retry.
Borderline failures keep the question and send it to the queue with the judge's note
("difficulty judge thinks this may be medium"). Deterministic rules, no schema change:
- difficulty: off by one band = borderline, two bands = clear;
- subtopic: proposed set overlaps the target = borderline, no overlap = clear;
- issues: blocking codes (incorrect answer / tests, technically incorrect) = clear, advisory
  codes (wording, ambiguity) = borderline.

**Acceptance criteria**
- Each rule above has a test (clear → retry, borderline → kept with note).
- The note is shown on the review card (UI test).
- The professor's verdict on a borderline item is a feedback record for that judge (test).
- m8 scorecard: retries and drops caused by judges fall on the simulation versus m9.
  **[spends API]**

**Validation**
- `pytest tests/test_round_review_safety.py tests/test_rounds.py -q`

**Touches.** `app/generation/review.py` (`RoundReview`), `app/evaluation/` issue-code
severity table, review card component.

**Not in this milestone.** Judge memory.

---

## m11 — Judges get MemAlign memory, frozen per round

**Deliverable.** Each judge's prompt = shipped prompt + its active guidelines
(`judge:<metric>` in `memory_guidelines`) + the k (~4) most similar episodes for that judge
(what it said, what the professor decided), from m4 episodes and m9/m10 audit and borderline
verdicts. The lesson run updates **judges first** (one distillation call per judge, edit
operations, ≥ 2 supporting reviews), then the generator. The round records the judge memory
snapshot; every judge call in the round uses it. A snapshot is promoted only if, on held-out
reviews, agreement does not drop and the known-bad pass rate does not rise; otherwise the
previous snapshot stays. Panel versioning (trust counters, calibration) keys on the snapshot
id. `refresh_judge_prompt`'s rewrite and its 5-disagreement threshold are retired.

**Acceptance criteria**
- Judge prompt contains guidelines and retrieved episodes (prompt test).
- Difficulty/subtopic episodes come from every review; issues episodes from rejects with an
  issue reason, approvals, and audit/borderline verdicts (test).
- Judges in a round ignore memory written during it (test).
- A snapshot that lowers held-out agreement is not promoted (test, fake scorer).
- Trust counters continue across rounds with an unchanged snapshot (test).
- `scripts/replay_judges.py`: memory judge κ ≥ current learned judge − 0.02 per judge, flag
  rate not lower, known-bad pass rate not higher. **[spends API: ~$2–3]**

**Validation**
- `pytest tests/test_judge_memory.py tests/test_judge_learning.py tests/test_review_outcomes.py -q`
- `python scripts/replay_judges.py <db copy>`

**Touches.** `app/evaluation/judge_prompts.py`, `app/evaluation/prompts.py`,
`app/evaluation/judge_learning.py`, `app/evaluation/trust*.py`, `app/memory/`,
`app/feedback/lessons.py`, `app/generation/rounds.py` (snapshot on round), migration
`0019_judge_snapshots.py`, `scripts/replay_judges.py`, ADR-064 status → accepted.

**Not in this milestone.** New judges or changed verdict schemas.

---

## m12 — End-to-end acceptance and learning curve

**Deliverable.** One report (`docs/LEARNING_MEMORY_RESULTS.md`) from two runs on a DB copy:
1. `simulate_review_loop.py` — 6 rounds, scripted professor with a hidden standard,
   adversarial reviews, audit answers.
2. `scripts/learning_curve.py` — judges and generator memory built from the first
   10 / 20 / 40 / 80 / 160 real reviews, scored on the latest 60.

**Acceptance criteria**
- Option-A rate ≤ 40% after the injection; compliance with the hidden standard ≥ 90% by round 3.
- First-attempt pass rate rises from round 1 to round 6; judge-caused drops fall.
- Misses and false alarms per judge both fall across rounds (m8 scorecard).
- Learning curve printed per judge with the review count where gains flatten (< 1 point per
  10 reviews) — the "how many reviews are needed" answer for this professor.
- Each result reports counts, not only percentages.

**Validation**
- `python scripts/simulate_review_loop.py <db copy> out.json` **[spends API: ~$3–5]**
- `python scripts/learning_curve.py <db copy>` **[spends API: ~$3]**

**Touches.** `scripts/`, `docs/LEARNING_MEMORY_RESULTS.md`.

**Not in this milestone.** Code changes beyond fixes the runs expose (those become follow-ups).

---

**Sequence:** m1 → m2 → m3 → m4 → m5 → m6 → m7 (generator) → m8 → m9 → m10 → m11 (judges) → m12.
m1, m4 and m8 need no API spend; m2, m3 use embeddings only; m5–m7 and m9–m12 end with a paid
simulation or replay (asked first).
**Active milestone:** none. Waiting for `start m1`.
