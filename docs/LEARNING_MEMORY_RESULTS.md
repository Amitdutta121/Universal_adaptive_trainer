# Learning-memory acceptance results

The numbers below are filled from two paid runs on a **copy** of
`data/adaptive_trainer.db`, never the live file. Until those runs happen, every
cell is **pending**.

Commands (from the `learning-memory` worktree, after `cp` of the database and
`alembic upgrade head` on the copy):

```
python -m scripts.simulate_review_loop <db copy> out.json
python -m scripts.learning_curve <db copy>
```

`--live` on `replay_judges.py` and `learning_curve.py` spends API; the default
paths score stored verdicts only.

## 1. Closed-loop simulation (`simulate_review_loop.py`, 6 rounds)

Hidden standard: G1 = fenced code in the stem; G2 = stem does not say "Which of
the following". Adversarial reviews include the option-A injection. Audit drafts
are answered agree/disagree by the same standard.

| Round | produced (n) | option-A (n / produced) | G1+G2 both (n) | first-attempt passes (n) | judge drops (n) | issues miss / FA (n) | difficulty miss / FA (n) | subtopic miss / FA (n) |
|------:|-------------:|------------------------:|---------------:|-------------------------:|----------------:|---------------------:|-------------------------:|-----------------------:|
| 1 | pending | pending | pending | pending | pending | pending | pending | pending |
| 2 | pending | pending | pending | pending | pending | pending | pending | pending |
| 3 | pending | pending | pending | pending | pending | pending | pending | pending |
| 4 | pending | pending | pending | pending | pending | pending | pending | pending |
| 5 | pending | pending | pending | pending | pending | pending | pending | pending |
| 6 | pending | pending | pending | pending | pending | pending | pending | pending |

Acceptance (m12): option-A rate ≤ 40% after the injection; G1+G2 compliance ≥ 90%
by round 3; first-attempt passes rise from round 1 to round 6; judge-caused drops
fall; misses and false alarms per judge both fall. Report counts, not only rates.

## 2. Learning curve (`learning_curve.py`)

Memory built from the first 10 / 20 / 40 / 80 / 160 real reviews, scored on the
latest 60. Flatten = first prefix where agreement gains < 1 percentage point per
10 reviews.

| prefix (n) | issues agree / n | difficulty agree / n | subtopic agree / n |
|-----------:|-----------------:|---------------------:|-------------------:|
| 10 | pending | pending | pending |
| 20 | pending | pending | pending |
| 40 | pending | pending | pending |
| 80 | pending | pending | pending |
| 160 | pending | pending | pending |

Flatten at (reviews): issues pending; difficulty pending; subtopic pending.

## 3. Other paid scripts still pending

See the final list in the m12 report. All run on a copy.
