# Watcher report

_Updated: 2026-08-31 07:52 — tick 8_

## Status: needs-review — 3 workstreams moving, no conflict, a few nits

| Check | Result |
|---|---|
| Conflict markers | none |
| `dev` vs `origin/dev` | ahead 10, behind 0 — pull cannot conflict |
| Working diff | changed — judge re-learn queue landed since tick 7 |

## What moved

- NEW: judge re-learn queue (ADR-039) — new file
  `app/evaluation/judge_relearn_worker.py`; new `JudgeRelearnJobRow` +
  `JudgeRelearnJobRepository`; new enum `JudgeRelearnJobStatus`; background
  worker started/stopped in `app/main.py` lifespan (`relearn_worker_enabled`
  setting, orphan reconcile on boot); `judge_prompts.py` +183 lines
  (`/refresh/preview|score|apply`, `relearn-jobs` CRUD); `schemas.py` +155.
  Contract checked: every imported symbol (`propose_judge_prompt`,
  `score_judge_candidate`, `apply_judge_proposal`, `GateVerdict`,
  `JudgeProposal`, `list_held_out`, `humanize_judge_error_detail`, config
  fields) exists and signatures match.
- Question regeneration w/ instructor feedback — `regenerate_from_question`
  in generation service; `instructor_feedback` threaded through
  `generation/{base,prompts}.py`; `POST /questions/{id}/regenerate`; new
  `Question`/`QuestionRow` cols; FE hook `useRegenerateWithFeedback` +
  `question-review.tsx` / `questions-browser.tsx` modal. FE/BE contract aligns.
- Coverage screen — new untracked `coverage/components/*`,
  `coverage-display.ts` + test; self-contained.

## Notes

- ruff: 3 style-only issues — `judge_relearn_worker.py:165` SIM105,
  `main.py:44` E501, `schemas.py:1439` E501. No bugs.
- `judge_prompts.py` imports `ReviewOutcomeRepository` but never uses it (dead import).
- New cols `questions.regenerated_from_question_id` / `regeneration_feedback`
  and table `judge_relearn_jobs`; no migration tool (ADR-008) -> existing
  `data/adaptive_trainer.db` will raise `SchemaOutOfDateError` on next start;
  DB file must be recreated. Do not commit the db file.
- `schemas.py` still spans two workstreams (regen ~L729-888, judge ~L1323-1477),
  non-overlapping — no textual conflict; stage by hunk at commit time.
- Files were being edited mid-tick (worker file, `question-review.tsx`) —
  active parallel work, expected.

## Nothing to act on — advisory only.
